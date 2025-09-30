Param(
  [switch]$Backend,
  [string]$DataBucket
)

$ErrorActionPreference = 'Stop'

$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$REPO_ROOT  = (Resolve-Path (Join-Path $SCRIPT_DIR '..')).Path
$CDK_DIR    = Join-Path $REPO_ROOT 'cdk'

if ([string]::IsNullOrWhiteSpace($env:VITE_APP_BASE_URL)) {
  $defaultBaseUrl = 'https://app.allotmint.io'
  Write-Host "VITE_APP_BASE_URL is not set. Defaulting to $defaultBaseUrl. Set VITE_APP_BASE_URL to override." -ForegroundColor Yellow
  $env:VITE_APP_BASE_URL = $defaultBaseUrl
}
$requirementsFile = Join-Path $CDK_DIR 'requirements.txt'
$requirementsSources = @()
if (Test-Path $requirementsFile) {
  $requirementsSources += @{ Description = "pip install -r $requirementsFile"; Args = @('-r', $requirementsFile) }
}
$devRequirementsFile = Join-Path $REPO_ROOT 'requirements-dev.txt'
if (Test-Path $devRequirementsFile) {
  $requirementsSources += @{ Description = "pip install -r $devRequirementsFile"; Args = @('-r', $devRequirementsFile) }
}
$requirementsSources += @{ Description = 'pip install aws-cdk-lib~=2.151.0 constructs~=10.3.0'; Args = @('aws-cdk-lib~=2.151.0', 'constructs~=10.3.0') }

# Ensure Python is available by validating the command actually executes and can import aws_cdk.
$pythonCandidates = @(
  @{ Name = 'python';   VersionArgs = @('--version');       ModuleArgs = @('-c', 'import aws_cdk');       ResolveArgs = @();                               InstallArgs = @('-m', 'pip', 'install') },
  @{ Name = 'python3';  VersionArgs = @('--version');       ModuleArgs = @('-c', 'import aws_cdk');       ResolveArgs = @();                               InstallArgs = @('-m', 'pip', 'install') },
  @{ Name = 'py';       VersionArgs = @('-3', '--version'); ModuleArgs = @('-3', '-c', 'import aws_cdk'); ResolveArgs = @('-3', '-c', 'import sys; print(sys.executable)'); InstallArgs = @('-3', '-m', 'pip', 'install') }
)

$PYTHON = $null
$selectedPythonVersion = $null
$autoInstallError = $null
$installAttempts = @{}
$missingModuleCandidates = @()

foreach ($candidate in $pythonCandidates) {
  $pythonCmd = Get-Command $candidate.Name -ErrorAction SilentlyContinue
  if (-not $pythonCmd) {
    continue
  }

  try {
    $versionOutput = & $pythonCmd.Path @($candidate.VersionArgs) 2>&1
    if ($LASTEXITCODE -ne 0) {
      continue
    }
  } catch {
    continue
  }

  $moduleExit = 0
  try {
    & $pythonCmd.Path @($candidate.ModuleArgs) 2>$null | Out-Null
    $moduleExit = $LASTEXITCODE
  } catch {
    $moduleExit = 1
  }

  if ($moduleExit -ne 0) {
    $commandKey = $pythonCmd.Path.ToLowerInvariant()
    if (-not $installAttempts.ContainsKey($commandKey)) {
      $installAttempts[$commandKey] = $true
      foreach ($source in $requirementsSources) {
        Write-Host "Installing AWS CDK Python dependencies ($($source.Description))..." -ForegroundColor Yellow
        $installArgs = $candidate.InstallArgs + $source.Args
        $pipExit = 0
        try {
          & $pythonCmd.Path @installArgs
          $pipExit = $LASTEXITCODE
        } catch {
          $pipExit = 1
          $autoInstallError = $_.Exception.Message
        }
        if ($pipExit -eq 0) {
          try {
            & $pythonCmd.Path @($candidate.ModuleArgs) 2>$null | Out-Null
            $moduleExit = $LASTEXITCODE
          } catch {
            $moduleExit = 1
            if (-not $autoInstallError) {
              $autoInstallError = $_.Exception.Message
            }
          }
          if ($moduleExit -eq 0) {
            $autoInstallError = $null
            break
          }
        } else {
          if (-not $autoInstallError) {
            $autoInstallError = "pip exited with code $pipExit"
          }
        }
      }
    }
  }

  if ($moduleExit -ne 0) {
    $missingModuleCandidates += $pythonCmd.Path
    continue
  }

  $resolvedPath = $pythonCmd.Path
  if ($candidate.ResolveArgs.Count -gt 0) {
    try {
      $resolvedOutput = & $pythonCmd.Path @($candidate.ResolveArgs)
      if ($LASTEXITCODE -eq 0 -and $resolvedOutput) {
        $resolvedCandidate = ($resolvedOutput | Select-Object -First 1).Trim()
        if ($resolvedCandidate -and (Test-Path $resolvedCandidate)) {
          $resolvedPath = $resolvedCandidate
        }
      }
    } catch {
      # Fall back to the command path when resolution fails.
    }
  }

  $PYTHON = $resolvedPath
  $selectedPythonVersion = $versionOutput
  break
}

if (-not $PYTHON) {
  if ($missingModuleCandidates.Count -gt 0) {
    Write-Host 'Python was located but aws_cdk remains unavailable.' -ForegroundColor Red
    if ($autoInstallError) {
      Write-Host "Automatic dependency installation failed: $autoInstallError" -ForegroundColor Red
    }
    if (-not (Test-Path $requirementsFile)) {
      Write-Host "No cdk/requirements.txt file was found; attempted fallback installers instead." -ForegroundColor Yellow
    }
    Write-Host 'Checked interpreters:' -ForegroundColor Yellow
    ($missingModuleCandidates | Sort-Object -Unique) | ForEach-Object { Write-Host "  $_" -ForegroundColor Yellow }
    Write-Host 'Install the dependencies manually and rerun the script.' -ForegroundColor Yellow
  } else {
    Write-Host 'Python is required but was not found. Install it from https://www.python.org/downloads/' -ForegroundColor Red
    Write-Host 'If you recently installed Python, ensure the "App execution aliases" for python.exe are disabled in Windows settings.' -ForegroundColor Yellow
  }
  exit 1
}

# Ensure downstream CDK commands pick up the detected interpreter.
$env:CDK_PYTHON = $PYTHON
if ($selectedPythonVersion) {
  $selectedPythonVersion | ForEach-Object { Write-Host $_ }
}
Write-Host "Using Python interpreter: $PYTHON" -ForegroundColor Cyan

# Provide a temporary shim so child processes can invoke `python3` on Windows.
$pythonShimDir = Join-Path ([System.IO.Path]::GetTempPath()) ("allotmint-cdk-python-" + [System.Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $pythonShimDir -Force | Out-Null
$pythonShimPath = Join-Path $pythonShimDir 'python3.cmd'
$shimScript = "@echo off`r`n""{0}"" %*`r`n" -f $PYTHON
Set-Content -Path $pythonShimPath -Value $shimScript -Encoding ASCII
$originalPath = $env:PATH
$env:PATH = "$pythonShimDir;$originalPath"

try {

# Place synthesized CDK templates outside the repository
$env:CDK_OUTDIR = Join-Path $REPO_ROOT '.cdk.out'

if (-not (Test-Path $CDK_DIR)) {
  Write-Host "CDK directory not found at $CDK_DIR" -ForegroundColor Red
  exit 1
}

$requirementsFile = Join-Path $CDK_DIR 'requirements.txt'
if (-not (Test-Path $requirementsFile)) {
  Write-Host "Expected requirements file at $requirementsFile" -ForegroundColor Red
  Write-Host 'Install the dependencies manually and rerun the script.' -ForegroundColor Yellow
  exit 1
}

Write-Host "Installing CDK dependencies from $requirementsFile..." -ForegroundColor Cyan
$pipArgs = @('-m', 'pip', 'install', '-r', $requirementsFile)
$pipProcess = Start-Process -FilePath $PYTHON -ArgumentList $pipArgs -NoNewWindow -PassThru -Wait
if ($pipProcess.ExitCode -ne 0) {
  Write-Host 'Failed to install CDK Python dependencies.' -ForegroundColor Red
  exit $pipProcess.ExitCode
}

  $frontendDir = Join-Path $REPO_ROOT 'frontend'
  if (-not (Test-Path $frontendDir)) {
    Write-Host "Frontend workspace not found at $frontendDir" -ForegroundColor Red
    exit 1
  }

  Push-Location $frontendDir
  try {
    $buildExitCode = 0
    $buildScript = Join-Path $frontendDir 'build.sh'
    if (Test-Path $buildScript) {
      $bashCmd = Get-Command bash -ErrorAction SilentlyContinue
      if (-not $bashCmd) {
        Write-Host 'bash is required to run frontend/build.sh but was not found in PATH.' -ForegroundColor Red
        throw 'bash is required to run frontend/build.sh but was not found in PATH.'
      }
      Write-Host 'Running frontend/build.sh in the frontend workspace...' -ForegroundColor Cyan
      & $bashCmd.Path $buildScript
      $buildExitCode = $LASTEXITCODE
    } else {
      $npmCmd = Get-Command npm -ErrorAction SilentlyContinue
      if (-not $npmCmd) {
        Write-Host 'npm CLI not found. Install Node.js and npm to build the frontend.' -ForegroundColor Red
        throw 'npm CLI not found. Install Node.js and npm to build the frontend.'
      }
      Write-Host 'Running `npm run build` in the frontend workspace...' -ForegroundColor Cyan
      & $npmCmd.Path 'run' 'build'
      $buildExitCode = $LASTEXITCODE
    }

    if ($buildExitCode -ne 0) {
      Write-Host "Frontend build failed with exit code $buildExitCode" -ForegroundColor Red
      throw "Frontend build failed with exit code $buildExitCode"
    }
  } finally {
    Pop-Location
  }

if ($Backend) {
  if (-not $env:DATA_BUCKET -and -not $DataBucket) {
    Write-Host 'Provide the S3 bucket for account data via -DataBucket or DATA_BUCKET environment variable.' -ForegroundColor Red
    exit 1
  }
  if ($DataBucket) {
    $env:DATA_BUCKET = $DataBucket
  }
  $dataDir = Join-Path $REPO_ROOT 'data'
  if (-not (Test-Path $dataDir) -or -not (Get-ChildItem $dataDir -ErrorAction SilentlyContinue)) {
    Write-Host 'Data directory missing; syncing...' -ForegroundColor Yellow
    $bashCmd = Get-Command bash -ErrorAction SilentlyContinue
    if (-not $bashCmd) {
      Write-Host 'bash not found; required to run sync_data.sh. Install Git Bash or WSL with bash.' -ForegroundColor Red
      exit 1
    }
    $syncScript = Join-Path $REPO_ROOT 'scripts/bash/sync_data.sh'
    if (-not (Test-Path $syncScript)) {
      Write-Host "Sync script not found at $syncScript" -ForegroundColor Red
      exit 1
    }
    Push-Location $REPO_ROOT
    try {
      & $bashCmd.Path $syncScript
    } finally {
      Pop-Location
    }
  }
  Push-Location $CDK_DIR
  try {
    Write-Host 'Deploying backend and frontend stacks to AWS...' -ForegroundColor Green
    $env:DEPLOY_BACKEND = 'true'
    $cdkCmd = Get-Command cdk -ErrorAction SilentlyContinue
    if (-not $cdkCmd) {
      Write-Host 'AWS CDK CLI not found. Install via `npm install -g aws-cdk` or use an existing installation.' -ForegroundColor Red
      exit 1
    }
    $effectiveBucket = if ($env:DATA_BUCKET) { $env:DATA_BUCKET } elseif ($DataBucket) { $DataBucket } else { $null }
    if (-not $effectiveBucket) {
      Write-Host 'DATA_BUCKET is required for backend deployment. Provide via -DataBucket or DATA_BUCKET env var.' -ForegroundColor Red
      exit 1
    }
    & $cdkCmd.Path deploy BackendLambdaStack StaticSiteStack -c "data_bucket=$effectiveBucket"
  } finally {
    Pop-Location
  }
} else {
  Push-Location $CDK_DIR
  try {
    Write-Host 'Deploying frontend stack to AWS...' -ForegroundColor Green
    $env:DEPLOY_BACKEND = 'false'
    $cdkCmd = Get-Command cdk -ErrorAction SilentlyContinue
    if (-not $cdkCmd) {
      Write-Host 'AWS CDK CLI not found. Install via `npm install -g aws-cdk` or use an existing installation.' -ForegroundColor Red
      exit 1
    }
    # Provide a context value for data_bucket so the app can instantiate BackendLambdaStack
    $effectiveBucket = if ($env:DATA_BUCKET) { $env:DATA_BUCKET } elseif ($DataBucket) { $DataBucket } else { 'placeholder-bucket' }
    & $cdkCmd.Path deploy StaticSiteStack -c "data_bucket=$effectiveBucket"
  } finally {
    Pop-Location
  }

}
} finally {
  $env:PATH = $originalPath
  if (Test-Path $pythonShimDir) {
    Remove-Item -Path $pythonShimDir -Recurse -Force -ErrorAction SilentlyContinue
  }
}
