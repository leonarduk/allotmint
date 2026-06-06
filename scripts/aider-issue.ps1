param(
    [Parameter(Mandatory)][string]$Issue
)

$owner  = "leonarduk"
$repo   = "allotmint"

# Accept either a full URL or a bare issue number
if ($Issue -match '(\d+)$') {
    $number = $Matches[1]
} else {
    Write-Error "Expected an issue number or URL, e.g. 123 or https://github.com/leonarduk/allotmint/issues/123"
    exit 1
}

# Fetch issue title + body
$issue = gh issue view $number --repo "$owner/$repo" --json title,body | ConvertFrom-Json
$title = $issue.title
$body  = $issue.body

# Create and switch to a branch named after the issue number
$branch = "issue-$number"
git checkout -b $branch
if ($LASTEXITCODE -ne 0) { exit 1 }

# Run aider with the issue as the prompt (auto-commits on test pass via .aider.conf.yml)
$prompt = "GitHub issue #${number}: $title`n`n$body"
aider --message $prompt
if ($LASTEXITCODE -ne 0) { exit 1 }

# Push the branch
git push -u origin $branch
if ($LASTEXITCODE -ne 0) { exit 1 }

# Open a draft PR (promote to ready when you've reviewed)
gh pr create `
    --title "Fix: $title" `
    --body "Closes #$number`n`nImplemented via aider." `
    --draft `
    --repo "$owner/$repo"
