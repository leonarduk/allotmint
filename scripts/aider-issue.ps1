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

# Fetch to ensure remote refs are current before any rev-parse.
# Warn (don't abort) on failure so offline re-runs still work, but never let a
# silent fetch failure cause a later reset to operate on a stale ref unnoticed.
git fetch origin 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Warning "git fetch origin failed; continuing with possibly stale remote refs."
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

# Create or reset the issue branch.
# If it already exists, reset it to origin/$defaultBranch so stale commits from a
# previous run are not silently included in the PR body or seen by aider.
$branch = "issue-$number"
# Reliable existence test: rev-parse sets a non-zero exit code when the ref is
# absent. (git branch --list returns whitespace-padded output whose truthiness is
# fragile across Git versions and pager configs.)
git rev-parse --verify --quiet "refs/heads/$branch" > $null 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Warning "Branch '$branch' already exists — resetting to origin/$defaultBranch to avoid stale commits."
    git checkout $branch
    if ($LASTEXITCODE -ne 0) { exit 1 }
    git reset --hard "origin/$defaultBranch"
    if ($LASTEXITCODE -ne 0) { exit 1 }
} else {
    git checkout -b $branch
    if ($LASTEXITCODE -ne 0) { exit 1 }
}

# Record the tip of the base branch so the PR body only lists commits aider adds.
# Fail fast with a clear message rather than silently passing an empty SHA to git log.
$baseSha = git rev-parse "origin/$defaultBranch" 2>$null
if (-not $baseSha) {
    Write-Error "Could not resolve origin/$defaultBranch. Run 'git fetch origin' and retry."
    exit 1
}

# Write the prompt to a temp file and pass it via aider's --message-file flag
# (aider's documented "-f / --message-file FILE" option: send one message
# non-interactively, process the reply, then exit). Routing the issue body through
# a file keeps attacker-controlled content off the command line entirely.
$promptFile = [System.IO.Path]::GetTempFileName()
Set-Content -Path $promptFile -Value "GitHub issue #${number}: $title`n`n$issueBody" -Encoding UTF8

aider --message-file $promptFile
Remove-Item $promptFile -ErrorAction SilentlyContinue
if ($LASTEXITCODE -ne 0) { exit 1 }

# Push the branch
git push -u origin $branch
if ($LASTEXITCODE -ne 0) { exit 1 }

# Build a rich PR body from the commits aider made
$commitBullets = git log "$baseSha..HEAD" --pretty=format:"- %s" 2>$null
$diffStat      = git diff "$baseSha..HEAD" --stat 2>$null

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

# Build the PR title with + to avoid re-evaluating backticks or $(...) in $title
$prTitle = "Fix: " + $title

# Open a draft PR; --head is explicit so fork contributors don't get a cross-repo mismatch
gh pr create `
    --title $prTitle `
    --body $prBody `
    --draft `
    --head $branch `
    --base $defaultBranch `
    --repo "$owner/$repo"
