param(
    [Parameter(Mandatory)][string]$Issue
)

# Pre-flight: require gh and aider on PATH
foreach ($cmd in @('gh', 'aider')) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        Write-Error "Required tool '$cmd' not found on PATH. Install it and try again."
        exit 1
    }
}

# Derive owner/repo from the local git remote so fork contributors target their own repo
$remote = git remote get-url origin 2>$null
if ($remote -match 'github\.com[:/]([^/]+)/([^/]+?)(\.git)?$') {
    $owner = $Matches[1]
    $repo  = $Matches[2]
} else {
    Write-Error "Could not parse GitHub owner/repo from git remote: $remote"
    exit 1
}

# Derive the repo default branch so --base is never hardcoded
$defaultBranch = gh repo view "$owner/$repo" --json defaultBranchRef --jq '.defaultBranchRef.name' 2>$null
if (-not $defaultBranch) { $defaultBranch = 'main' }

# Accept either a full URL or a bare issue number
if ($Issue -match '(\d+)$') {
    $number = $Matches[1]
} else {
    Write-Error "Expected an issue number or URL, e.g. 123 or https://github.com/leonarduk/allotmint/issues/123"
    exit 1
}

# Fetch issue title + body
$issueData = gh issue view $number --repo "$owner/$repo" --json title,body | ConvertFrom-Json
$title     = $issueData.title
$issueBody = if ($issueData.body) { $issueData.body } else { "" }

# Create and switch to a branch (safe to re-run if branch already exists)
$branch = "issue-$number"
git checkout $branch
if ($LASTEXITCODE -ne 0) {
    git checkout -b $branch
    if ($LASTEXITCODE -ne 0) { exit 1 }
}

# Record the tip of the base branch so we can summarise only the commits aider adds
$baseSha = git rev-parse "origin/$defaultBranch" 2>$null
if (-not $baseSha) { $baseSha = git merge-base HEAD "origin/$defaultBranch" }

# Run aider with the issue as the prompt (auto-commits on test pass via .aider.conf.yml)
$prompt = "GitHub issue #${number}: $title`n`n$issueBody"
aider --message $prompt
if ($LASTEXITCODE -ne 0) { exit 1 }

# Push the branch
git push -u origin $branch
if ($LASTEXITCODE -ne 0) { exit 1 }

# Build a rich PR body from the commits aider made
$commitBullets = git log "$baseSha..HEAD" --pretty=format:"- %s" 2>$null
$diffStat      = (git diff "$baseSha..HEAD" --stat 2>$null | Select-Object -Last 1)

$prBody = @"
## Summary

This PR resolves #${number}: $title

Closes #${number}

## What was implemented
$commitBullets

## Why this matters
$issueBody

## Changes
$diffStat

🤖 Implemented via [aider](https://aider.chat) with local Ollama model
"@

# Open a draft PR against the repo default branch (promote to ready after review)
gh pr create `
    --title "Fix: $title" `
    --body $prBody `
    --draft `
    --base $defaultBranch `
    --repo "$owner/$repo"
