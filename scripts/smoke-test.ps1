Param(
  [Alias('Url')]
  [string[]]$Urls,

  [Alias('BaseUrl', 'Base')]
  [string]$SmokeUrl,

  [switch]$UrlsOnly
)

function Resolve-RepoRoot {
  param(
    [string]$ScriptRoot
  )

  $current = (Resolve-Path -Path $ScriptRoot).Path
  while ($current -and -not (Test-Path -Path (Join-Path -Path $current -ChildPath 'package.json'))) {
    $parent = Split-Path -Path $current -Parent
    if (-not $parent -or $parent -eq $current) {
      throw "Unable to locate repository root from '$ScriptRoot'."
    }
    $current = $parent
  }

  return $current
}

function Invoke-UrlChecks {
  param(
    [string[]]$Targets
  )

  foreach ($Target in $Targets) {
    try {
      $response = Invoke-WebRequest -Uri $Target -UseBasicParsing
    } catch {
      Write-Error ("Smoke test failed for {0}: {1}" -f $Target, $_.Exception.Message)
      exit 1
    }

    if ($response.StatusCode -ne 200) {
      Write-Error ("Smoke test failed for {0} with status {1}" -f $Target, $response.StatusCode)
      exit 1
    }

    Write-Output ("Smoke test passed for {0}" -f $Target)
  }
}

function Invoke-SmokeSuites {
  param(
    [string]$BaseUrl
  )

  $node = Get-Command node -ErrorAction SilentlyContinue
  if (-not $node) {
    throw 'Node.js is required to run the smoke suites. Install Node and try again.'
  }

  $repoRoot = Resolve-RepoRoot -ScriptRoot $PSScriptRoot
  $tsxCli = Join-Path -Path $repoRoot -ChildPath 'node_modules/tsx/dist/cli.mjs'
  if (-not (Test-Path -Path $tsxCli)) {
    throw "Local tsx CLI was not found. Run 'npm install' in '$repoRoot' to install Node dependencies."
  }

  $smokeScript = Join-Path -Path $repoRoot -ChildPath 'scripts/smoke-all.ts'
  if (-not (Test-Path -Path $smokeScript)) {
    throw "Expected smoke runner at '$smokeScript' but it was not found."
  }

  $previousSmokeUrl = $env:SMOKE_URL
  if ($BaseUrl) {
    $env:SMOKE_URL = $BaseUrl
  }

  Push-Location -Path $repoRoot
  try {
    & $node.Path $tsxCli $smokeScript
    $exitCode = $LASTEXITCODE
  } finally {
    Pop-Location
    if ($BaseUrl -ne $null) {
      $env:SMOKE_URL = $previousSmokeUrl
    }
  }

  if ($exitCode -ne 0) {
    exit $exitCode
  }
}

$trimmedUrls = @()
if ($Urls) {
  $trimmedUrls = $Urls | ForEach-Object { $_.Trim() } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
}

if (-not $trimmedUrls) {
  $envUrls = $env:SMOKE_TEST_URLS -split ','
  $trimmedUrls = $envUrls | ForEach-Object { $_.Trim() } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
}

if (-not $SmokeUrl) {
  $SmokeUrl = $env:SMOKE_URL
}

if ($SmokeUrl) {
  $SmokeUrl = $SmokeUrl.Trim()
  if (-not $SmokeUrl) {
    $SmokeUrl = $null
  }
}

$shouldRunSuites = -not $UrlsOnly.IsPresent

if ($trimmedUrls) {
  Invoke-UrlChecks -Targets $trimmedUrls
  if (-not $shouldRunSuites) {
    exit 0
  }
}

if ($shouldRunSuites) {
  Invoke-SmokeSuites -BaseUrl $SmokeUrl
}

exit 0
