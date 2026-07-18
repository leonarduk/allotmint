# Unit tests for the file discovery logic in ../aider-issue.ps1
# (direct path matching + basename fallback via `git ls-files`, added by PR #4293).
#
# aider-issue.ps1 is a top-level script with real side effects (git checkout,
# git reset --hard, git push, gh pr create) and no extracted function to call
# in isolation, so these tests extract the discovery snippet verbatim from the
# source file's text and dot-source it with git/Test-Path mocked. This runs the
# exact shipped code (not a re-implementation), so a regression in the real
# script fails these tests, while `git`/the filesystem are never touched.
#
# Constraint: this file must never modify aider-issue.ps1 (tests only).

BeforeAll {
    $script:ScriptUnderTest = (Resolve-Path (Join-Path $PSScriptRoot '..' 'aider-issue.ps1')).Path
    $raw = Get-Content -LiteralPath $script:ScriptUnderTest -Raw

    # Start marker: first line of the candidate-path regex setup.
    # End marker: the line combining identifier/direct/basename matches into $referencedFiles.
    # If aider-issue.ps1 is restructured, these IndexOf calls stop finding the
    # markers and the throw below fails loudly instead of silently testing stale text.
    $startToken = '$pathPattern'
    $endToken = '$referencedFiles = @(('

    $startIndex = $raw.IndexOf($startToken)
    if ($startIndex -lt 0) {
        throw "Could not locate start marker '$startToken' in aider-issue.ps1 - the file discovery logic may have moved. Update the extraction markers in this test file."
    }

    $endAnchor = $raw.IndexOf($endToken)
    if ($endAnchor -lt 0) {
        throw "Could not locate end marker '$endToken' in aider-issue.ps1 - the file discovery logic may have moved. Update the extraction markers in this test file."
    }

    $eol = $raw.IndexOf("`n", $endAnchor)
    if ($eol -lt 0) { $eol = $raw.Length }

    $script:DiscoverySnippet = $raw.Substring($startIndex, $eol - $startIndex)
}

Describe 'aider-issue.ps1 file discovery logic' {

    BeforeEach {
        # $title/$issueBody/$repoRoot are read by the dot-sourced snippet below;
        # $candidates/$directMatches/$basenameMatches/$referencedFiles are set by it.
        # A drive-letter path (e.g. 'C:\repo') makes Join-Path throw
        # DriveNotFoundException on the Linux CI runner, so use a
        # drive-neutral root that resolves the same on Windows and Linux.
        $repoRoot = '/repo'
    }

    Context 'direct path match' {
        It 'adds a candidate that already exists verbatim relative to the repo root' {
            $title = 'Fix a bug'
            $issueBody = 'See .github/scripts/test_extract_verdict.py for details.'

            Mock -CommandName Test-Path -MockWith {
                $LiteralPath -eq (Join-Path $repoRoot '.github/scripts/test_extract_verdict.py')
            }
            Mock -CommandName git -MockWith { @() }

            . ([scriptblock]::Create($script:DiscoverySnippet))

            $referencedFiles | Should -Contain (Join-Path $repoRoot '.github/scripts/test_extract_verdict.py')
            $referencedFiles.Count | Should -Be 1
        }
    }

    Context 'basename fallback via git ls-files' {
        It 'finds a tracked file when the bare filename is not at the candidate path' {
            $title = 'Fix a bug'
            $issueBody = 'Bug in test_extract_verdict.py needs fixing'

            Mock -CommandName Test-Path -MockWith { $false }
            Mock -CommandName git -MockWith {
                if ($args -contains 'ls-files') { return @('.github/scripts/test_extract_verdict.py') }
                return @()
            }

            . ([scriptblock]::Create($script:DiscoverySnippet))

            $referencedFiles | Should -Contain (Join-Path $repoRoot '.github/scripts/test_extract_verdict.py')
            $referencedFiles.Count | Should -Be 1
        }
    }

    Context 'duplicate basenames' {
        It 'adds every tracked file sharing the basename, since the script has no disambiguation for this case' {
            # This is one of the two known gaps flagged from PR #4293: with no
            # identifier hint in the issue text, an ambiguous basename adds
            # every matching tracked file rather than erroring or picking one.
            $title = 'Fix a bug'
            $issueBody = 'helper.py needs a fix'

            Mock -CommandName Test-Path -MockWith { $false }
            Mock -CommandName git -MockWith {
                if ($args -contains 'ls-files') { return @('backend/helper.py', 'frontend/scripts/helper.py') }
                return @()
            }

            . ([scriptblock]::Create($script:DiscoverySnippet))

            $referencedFiles | Should -Contain (Join-Path $repoRoot 'backend/helper.py')
            $referencedFiles | Should -Contain (Join-Path $repoRoot 'frontend/scripts/helper.py')
            $referencedFiles.Count | Should -Be 2
        }
    }

    Context 'no match anywhere' {
        It 'adds nothing when the candidate exists neither at the path nor in git ls-files' {
            $title = 'Fix a bug'
            $issueBody = 'ghost_file.py has an issue'

            Mock -CommandName Test-Path -MockWith { $false }
            Mock -CommandName git -MockWith { @() }

            . ([scriptblock]::Create($script:DiscoverySnippet))

            $referencedFiles.Count | Should -Be 0
        }
    }

    Context 'empty repository' {
        It 'does not throw when git ls-files returns no output' {
            # The other known gap from PR #4293: trackedFiles ends up an empty
            # array (not $null) when git ls-files prints nothing, so the
            # Where-Object basename filter below it must not dereference $null.
            $title = 'Fix a bug'
            $issueBody = 'anything.py is broken'

            Mock -CommandName Test-Path -MockWith { $false }
            Mock -CommandName git -MockWith { @() }

            { . ([scriptblock]::Create($script:DiscoverySnippet)) } | Should -Not -Throw

            $referencedFiles.Count | Should -Be 0
        }
    }

    Context 'deferred git ls-files call' {
        It 'does not call git ls-files when every candidate already matched directly' {
            # Fixed in issue #4295 (follow-up from PR #4293): git ls-files
            # used to run unconditionally, even when no candidate needed the
            # basename fallback. It should now be skipped in that case.
            $title = 'Fix a bug'
            $issueBody = 'See .github/scripts/test_extract_verdict.py for details.'

            Mock -CommandName Test-Path -MockWith {
                $LiteralPath -eq (Join-Path $repoRoot '.github/scripts/test_extract_verdict.py')
            }
            Mock -CommandName git -MockWith { @() }

            . ([scriptblock]::Create($script:DiscoverySnippet))

            Should -Invoke -CommandName git -ParameterFilter { $args -contains 'ls-files' } -Times 0 -Exactly
        }

        It 'calls git ls-files when at least one candidate is unmatched' {
            $title = 'Fix a bug'
            $issueBody = 'Bug in test_extract_verdict.py needs fixing'

            Mock -CommandName Test-Path -MockWith { $false }
            Mock -CommandName git -MockWith {
                if ($args -contains 'ls-files') { return @('.github/scripts/test_extract_verdict.py') }
                return @()
            }

            . ([scriptblock]::Create($script:DiscoverySnippet))

            Should -Invoke -CommandName git -ParameterFilter { $args -contains 'ls-files' } -Times 1 -Exactly
        }
    }
}
