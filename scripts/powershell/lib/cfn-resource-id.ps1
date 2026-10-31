# PowerShell twin of cfn_resource_id in scripts/bash/lib/cfn_resource_id.sh,
# dot-sourced by scripts/powershell/pre-deploy-check.ps1. Tested offline with a
# fake `aws` in tests/scripts/test_cfn_resource_id.py.

# Get-CfnResourceId STACK QUERY -> [pscustomobject]@{ Ok; Id; Error }
#
#   Ok=$true,  Id=<id>   -- found
#   Ok=$true,  Id=$null  -- the stack does not exist, or nothing matched
#   Ok=$false, Error=... -- the aws call failed for any other reason
#                           (throttling, expired credentials, network)
#
# Callers that fall back when nothing is found must not fall back when Ok is
# $false: a failed call says nothing about whether the resource exists (#11095).
# "Does not exist" means a ValidationError naming a missing stack; if AWS ever
# rewords that message, a missing stack fails loudly instead of being skipped.
# The query must not end in "| [0]": past 100 resources the CLI applies --query
# per page (#11091).
function Get-CfnResourceId([string]$Stack, [string]$Query) {
    # Native stderr arrives as ErrorRecords under 2>&1; Continue keeps a
    # caller's 'Stop' from turning them into a terminating error.
    $ErrorActionPreference = 'Continue'
    $output = @(& aws cloudformation list-stack-resources --stack-name $Stack --query $Query --output text 2>&1)
    $exitCode = $LASTEXITCODE
    $stderr = @($output | Where-Object { $_ -is [System.Management.Automation.ErrorRecord] } | ForEach-Object { "$_" })
    $lines = @($output | Where-Object { $_ -isnot [System.Management.Automation.ErrorRecord] } | ForEach-Object { "$_" })
    if ($exitCode -ne 0) {
        $message = (@($stderr) + @($lines)) -join "`n"
        if ($message -match 'ValidationError[\s\S]*Stack with id \S+ does not exist') {
            return [pscustomobject]@{ Ok = $true; Id = $null; Error = $null }
        }
        return [pscustomobject]@{
            Ok = $false
            Id = $null
            Error = "aws cloudformation list-stack-resources --stack-name $Stack failed (exit $exitCode):`n$message"
        }
    }
    $id = $lines | ForEach-Object { $_ -split "[`t`r`n]" } | Where-Object { $_ -and $_ -ne 'None' } | Select-Object -First 1
    return [pscustomobject]@{ Ok = $true; Id = $id; Error = $null }
}
