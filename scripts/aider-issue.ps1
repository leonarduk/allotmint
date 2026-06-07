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
Write-Host "[1/6] Fetching remote refs..."
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
    Write-Error "Could not parse GitHub owner/repo from git remote: ${remote}"
    exit 1
}

# Derive the repo default branch so --base is never hardcoded
$defaultBranch = gh repo view "$owner/$repo" --json defaultBranchRef --jq '.defaultBranchRef.name' 2>$null
if (-not $defaultBranch) {
    Write-Warning "Could not detect default branch (gh API call failed); falling back to 'main'."
    $defaultBranch = 'main'
}

# Accept either a full URL or a bare issue number
if ($Issue -match '(\d+)$') {
    $number = $Matches[1]
} else {
    Write-Error "Expected an issue number or URL, e.g. 123 or https://github.com/leonarduk/allotmint/issues/123"
    exit 1
}

# Fetch issue title + body; fail fast if the API call fails so aider never
# receives an empty prompt and creates a content-free PR.
Write-Host "[2/6] Fetching issue #$number from $owner/$repo..."
$issueJson = gh issue view $number --repo "$owner/$repo" --json title,body 2>&1
if ($LASTEXITCODE -ne 0 -or -not $issueJson) {
    Write-Error "Failed to fetch issue #$number (exit $LASTEXITCODE). Check network and 'gh auth status'."
    exit 1
}
$issueData = $issueJson | ConvertFrom-Json
$title     = $issueData.title
$issueBody = if ($issueData.body) { $issueData.body } else { "" }
if (-not $title) {
    Write-Error "Issue #$number has no title or could not be parsed. Raw gh output: $issueJson"
    exit 1
}
Write-Host "    Title: $title"

# Create or reset the issue branch.
# If it already exists, reset it to origin/$defaultBranch so stale commits from a
# previous run are not silently included in the PR body or seen by aider.
$branch = "issue-$number"
Write-Host "[3/6] Preparing branch $branch..."
# Reliable existence test: rev-parse sets a non-zero exit code when the ref is
# absent. (git branch --list returns whitespace-padded output whose truthiness is
# fragile across Git versions and pager configs.)
git rev-parse --verify --quiet "refs/heads/$branch" > $null 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Warning "Branch '$branch' already exists - resetting to origin/$defaultBranch to avoid stale commits."
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

Write-Host "[4/6] Running aider on issue #$number..."
aider --yes --message-file $promptFile
Remove-Item $promptFile -ErrorAction SilentlyContinue
if ($LASTEXITCODE -ne 0) { exit 1 }

# Abort if aider made no commits - avoids pushing an empty branch and opening
# a content-free PR (e.g. when the issue fetch silently returned no data).
$newCommits = git rev-list "$baseSha..HEAD" --count 2>$null
if (-not $newCommits -or [int]$newCommits -eq 0) {
    Write-Error "Aider made no commits. Aborting push and PR creation. Check that the issue prompt was non-empty and that aider connected to the model successfully."
    exit 1
}
Write-Host "    Aider produced $newCommits commit(s)."

# Push the branch. Use --force-with-lease because the branch may have been
# reset to origin/$defaultBranch earlier in this script, making a normal push
# fail as non-fast-forward if the remote already had commits from a prior run.
Write-Host "[5/6] Pushing branch $branch..."
git push -u --force-with-lease origin $branch
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
Write-Host "[6/6] Creating draft PR..."
gh pr create `
    --title $prTitle `
    --body $prBody `
    --draft `
    --head $branch `
    --base $defaultBranch `
    --repo "$owner/$repo"
