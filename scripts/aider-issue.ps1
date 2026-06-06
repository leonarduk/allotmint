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

# Fetch to ensure remote refs are current before any rev-parse
git fetch origin 2>$null

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

# Create or reuse the issue branch; warn when reusing so the developer knows
$branch = "issue-$number"
$branchExists = git branch --list $branch
if ($branchExists) {
    Write-Warning "Branch '$branch' already exists locally — reusing it. Verify it is in the expected state before continuing."
    git checkout $branch
} else {
    git checkout -b $branch
}
if ($LASTEXITCODE -ne 0) { exit 1 }

# Record the tip of the base branch so the PR body only lists commits aider adds.
# Fail fast with a clear message rather than silently passing an empty SHA to git log.
$baseSha = git rev-parse "origin/$defaultBranch" 2>$null
if (-not $baseSha) {
    Write-Error "Could not resolve origin/$defaultBranch. Run 'git fetch origin' and retry."
    exit 1
}

# Write the prompt to a temp file and use --message-file so the issue body never
# touches the command line (prevents shell injection from attacker-controlled content)
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

# Open a draft PR; --head is explicit so fork contributors don't get a cross-repo mismatch
gh pr create `
    --title "Fix: $title" `
    --body $prBody `
    --draft `
    --head $branch `
    --base $defaultBranch `
    --repo "$owner/$repo"
