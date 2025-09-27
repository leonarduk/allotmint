Param(
  [switch]$Backend,
  [string]$DataBucket
)

$ErrorActionPreference = 'Stop'

$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$REPO_ROOT  = (Resolve-Path (Join-Path $SCRIPT_DIR '..')).Path
$CDK_DIR    = Join-Path $REPO_ROOT 'cdk'
$requirementsFile = Join-Path $CDK_DIR 'requirements.txt'
$requirementsAvailable = Test-Path $requirementsFile

# Ensure Python is available by validating the command actually executes and can import aws_cdk.
$pythonCandidates = @(
  @{ Name = 'python';   VersionArgs = @('--version');       ModuleArgs = @('-c', 'import aws_cdk');       ResolveArgs = @();                               InstallArgs = @('-m', 'pip', 'install', '-r') },
  @{ Name = 'python3';  VersionArgs = @('--version');       ModuleArgs = @('-c', 'import aws_cdk');       ResolveArgs = @();                               InstallArgs = @('-m', 'pip', 'install', '-r') },
  @{ Name = 'py';       VersionArgs = @('-3', '--version'); ModuleArgs = @('-3', '-c', 'import aws_cdk'); ResolveArgs = @('-3', '-c', 'import sys; print(sys.executable)'); InstallArgs = @('-3', '-m', 'pip', 'install', '-r') }
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
      if ($requirementsAvailable) {
        Write-Host 'Installing AWS CDK Python dependencies (pip install -r cdk/requirements.txt)...' -ForegroundColor Yellow
        $installArgs = $candidate.InstallArgs + $requirementsFile
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
        } else {
          if (-not $autoInstallError) {
            $autoInstallError = "pip exited with code $pipExit"
          }
          $moduleExit = 1
        }
      } else {
        $autoInstallError = "Requirements file not found at $requirementsFile"
        $moduleExit = 1
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
    if (-not $requirementsAvailable) {
      Write-Host "Expected requirements file at $requirementsFile" -ForegroundColor Yellow
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
