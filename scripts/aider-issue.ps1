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

# Pre-flight: self-heal a leftover unresolved `git stash pop` conflict from a
# prior interrupted run in this (possibly shared) working tree. `git checkout
# $branch` in step [3/6] refuses to run while the index has unmerged entries,
# so without this the script fails with "you need to resolve your current
# index first" regardless of which issue is being worked.
$unmergedPaths = @(git diff --name-only --diff-filter=U 2>$null | Where-Object { $_ })
if ($unmergedPaths.Count -gt 0) {
    $gitDir = git rev-parse --git-dir
    $opInProgress = @('MERGE_HEAD', 'CHERRY_PICK_HEAD', 'rebase-merge', 'rebase-apply') |
        Where-Object { Test-Path (Join-Path $gitDir $_) }
    if ($opInProgress) {
        Write-Error "A git operation ($($opInProgress -join ', ')) is in progress with unresolved conflicts in: $($unmergedPaths -join ', '). Resolve or abort it manually before running this script."
        exit 1
    }
    # No merge/rebase/cherry-pick in progress, so this is leftover from an
    # interrupted `git stash pop`. Reset just these paths to HEAD to clear the
    # conflict. Deliberately do NOT run `git stash drop` - the corresponding
    # stash entry (if any) is left in place for manual review, since choosing
    # which side to keep is a judgment call this script shouldn't make.
    Write-Warning "Resetting leftover unresolved conflict in: $($unmergedPaths -join ', ') (likely from an interrupted 'git stash pop'). Any related stash entry is left in place for manual review."
    git checkout HEAD -- $unmergedPaths
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to reset conflicted paths to HEAD. Resolve the conflict manually before running this script."
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

# Discover files the issue references that actually exist on disk and add them
# to aider's editable context. Without explicit targets, weaker local models
# tend to reply with prose like "please add these files to the chat" and make
# no edits; because that reply is not aider's structured file-add prompt,
# yes-always cannot accept it, so the run produces zero commits and aborts at
# the guard below. The regex matches path-like tokens (optional dir segments +
# filename.ext); Test-Path then keeps only the ones that exist, so over-broad
# matches (version numbers, "e.g", URLs) are harmlessly discarded.
#
# Security: $issueBody is attacker-controllable (anyone who can open an issue),
# so reject parent-dir traversal ('..') and absolute/rooted paths before the
# existence check. Otherwise a crafted issue could reference a file outside the
# repo (e.g. ../../.aws/credentials) that exists on disk and pull it into
# aider's editable context, where it could be modified or leaked into a commit.
# With those rejected and the relative path resolved from the repo root, every
# kept match is confined to the repo subtree.
#
# Resolve candidates against the repo root, not $PWD: this script may be
# invoked from a subdirectory (e.g. scripts/), in which case Test-Path against
# $PWD would mis-resolve every relative path and either reject all real files
# or accept paths relative to the wrong directory.
$repoRoot = git rev-parse --show-toplevel 2>$null
if (-not $repoRoot) {
    Write-Error "Could not resolve repo root via 'git rev-parse --show-toplevel'."
    exit 1
}
$pathPattern = '(?:[\w.-]+[\\/])*[\w.-]+\.[A-Za-z0-9]+'
$candidates = @(
    [regex]::Matches("$title`n$issueBody", $pathPattern) |
        ForEach-Object { $_.Value } |
        Sort-Object -Unique |
        Where-Object { $_ -notmatch '\.\.' -and -not [System.IO.Path]::IsPathRooted($_) }
)

# Direct matches: candidate is already a valid path relative to the repo root.
$directMatches = @(
    $candidates |
        Where-Object { Test-Path -LiteralPath (Join-Path $repoRoot $_) -PathType Leaf } |
        ForEach-Object { Join-Path $repoRoot $_ }
)

# Basename fallback: issue text often names a bare filename (e.g.
# "test_extract_verdict.py") without its directory, but the file actually
# lives in a subdirectory (e.g. .github/scripts/test_extract_verdict.py).
# Search tracked files for a matching leaf name so those still get added to
# aider's context. Restricted to `git ls-files` output, so only files already
# tracked in the repo can match - no path traversal outside the repo.
$unmatchedCandidates = @(
    $candidates |
        Where-Object { -not (Test-Path -LiteralPath (Join-Path $repoRoot $_) -PathType Leaf) }
)
$basenameMatches = @()
if ($unmatchedCandidates.Count -gt 0) {
    # Only pay for listing every tracked file when a direct match didn't
    # already resolve every candidate (repos with thousands of files make
    # this call non-trivial, so skip it in the common all-direct-match case).
    $trackedFiles = @(git -C $repoRoot ls-files)
    $basenameMatches = @(
        $unmatchedCandidates |
            ForEach-Object {
                $leaf = Split-Path -Leaf $_
                $trackedFiles | Where-Object { (Split-Path -Leaf $_) -eq $leaf }
            } |
            Sort-Object -Unique |
            ForEach-Object { Join-Path $repoRoot $_ }
    )
}

# Identifier matches: issue text often calls out a specific function/method/
# symbol in backticks (e.g. a test method name). When multiple files share a
# basename (see above), a weak local model can't tell
# which one is relevant and may produce a no-op edit against the wrong file.
# Grepping tracked files for the exact identifier pinpoints the file that
# actually defines/uses it. `git grep -l -F` only searches tracked files, so
# results stay inside the repo. Listed first so it's the model's primary cue.
# Require an underscore so generic backtick-quoted words (e.g. `APPROVE`)
# don't turn into noisy, repo-wide grep matches - snake_case identifiers
# (function/method/variable names) are the useful signal here.
$identifierPattern = '`([A-Za-z_][A-Za-z0-9_]*_[A-Za-z0-9_]*)`'
$identifiers = @(
    [regex]::Matches("$title`n$issueBody", $identifierPattern) |
        ForEach-Object { $_.Groups[1].Value } |
        Sort-Object -Unique
)
$identifierMatches = @(
    $identifiers |
        ForEach-Object { git -C $repoRoot grep -l -F -- $_ 2>$null } |
        Sort-Object -Unique |
        ForEach-Object { Join-Path $repoRoot $_ }
)

$referencedFiles = @(($identifierMatches + $directMatches + $basenameMatches) | Select-Object -Unique)
if ($referencedFiles.Count -gt 0) {
    Write-Host "    Adding referenced files to aider context: $($referencedFiles -join ', ')"
} else {
    # Not fatal: aider can still create a new file or work from its repo-map, so
    # let the run proceed. The no-commits guard below catches a true no-op.
    Write-Warning "Issue text referenced no existing repo files; aider has no explicit edit targets and may make no changes. If the issue names files that do not exist, correct the issue text first."
}

# Pass each file via aider's repeatable --file flag. Aider also accepts bare
# positional [FILE ...], but --file is unambiguous if a name ever looks like an
# option. An empty array splats to nothing, leaving aider to work from repo-map.
$fileArgs = @($referencedFiles | ForEach-Object { '--file', $_ })

Write-Host "[4/6] Running aider on issue #$number..."
aider @fileArgs --yes-always --message-file $promptFile
Remove-Item $promptFile -ErrorAction SilentlyContinue
if ($LASTEXITCODE -ne 0) { exit 1 }

# Abort if aider made no commits - avoids pushing an empty branch and opening
# a content-free PR. The most common cause is the model replying with prose
# (for example asking for files) instead of edits, so auto-commit never fired.
$newCommits = git rev-list "$baseSha..HEAD" --count 2>$null
if (-not $newCommits -or [int]$newCommits -eq 0) {
    Write-Error "Aider made no commits, so there is nothing to push. This usually means the model replied without edits (e.g. asking for files). Review the aider output above; if the issue references files that do not exist in the repo, correct the issue text and retry."
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

# Write the PR body to a temp file and pass it via --body-file. Passing the
# multi-line body straight through --body is unreliable under Windows
# PowerShell: its native-argument quoting splits the string on the embedded
# spaces, double quotes, and backticks that issue bodies routinely contain, so
# gh sees dozens of stray tokens and aborts with "unknown arguments ...; please
# quote all values that have spaces". A file sidesteps command-line quoting
# entirely (the same approach already used for the aider prompt above).
$bodyFile = [System.IO.Path]::GetTempFileName()
# Write BOM-free UTF-8: Set-Content -Encoding UTF8 emits a BOM on Windows
# PowerShell 5.x, and [System.Text.Encoding]::UTF8 also carries a 3-byte
# preamble, either of which gh would copy verbatim into the PR body. A
# UTF8Encoding constructed with $false omits the BOM on both 5.x and 7.x.
[System.IO.File]::WriteAllText($bodyFile, $prBody, (New-Object System.Text.UTF8Encoding($false)))

# Open a draft PR; --head is explicit so fork contributors don't get a cross-repo mismatch
Write-Host "[6/6] Creating draft PR..."
gh pr create `
    --title $prTitle `
    --body-file $bodyFile `
    --draft `
    --head $branch `
    --base $defaultBranch `
    --repo "$owner/$repo"
$prExit = $LASTEXITCODE
Remove-Item $bodyFile -ErrorAction SilentlyContinue
if ($prExit -ne 0) {
    Write-Error "gh pr create failed (exit $prExit). The branch was pushed; create the PR manually or re-run after fixing the error above."
    exit 1
}
