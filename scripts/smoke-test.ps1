Param(
  [string[]]$Urls = $env:SMOKE_TEST_URLS -split ','
)

$Urls = $Urls | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }

if (-not $Urls) {
  Write-Error "Usage: SMOKE_TEST_URLS=<url>[,<url>...] .\\smoke-test.ps1 [url ...]"
  exit 1
}

foreach ($Url in $Urls) {
  try {
    $response = Invoke-WebRequest -Uri $Url -UseBasicParsing
  } catch {
    Write-Error ("Smoke test failed for {0}: {1}" -f $Url, $_.Exception.Message)
    exit 1
  }

  if ($response.StatusCode -ne 200) {
    Write-Error ("Smoke test failed for {0} with status {1}" -f $Url, $response.StatusCode)
    exit 1
  }

  Write-Output ("Smoke test passed for {0}" -f $Url)
}
