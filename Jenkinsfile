// Jenkins pipeline mirroring the core GitHub Actions workflows so the same
// checks can run locally when GitHub Actions is unavailable.
//
// Mapping (see docs/CONTRIBUTOR_RUNBOOK.md "Jenkins mirror of GitHub Actions"):
//   ci.yml test job            -> Repo Hygiene
//   ci.yml backend-lint        -> Backend Lint
//   ci.yml lambda-compat       -> Lambda Compat
//   ci.yml validate-backend-deps -> Validate Backend Deps
//   ci.yml shell-tests         -> Shell Tests
//   ci.yml cdk-tests           -> CDK Tests
//   ci.yml python-compatibility -> Python 3.11 Compat
//   ci.yml frontend-checks     -> Frontend Checks
//   ci.yml frontend-smoke      -> Frontend Smoke (optional, parameter-gated)
//   backend-integration.yml    -> Backend Integration Tests
//   frontend-tests.yml         -> Frontend Checks (audit/coverage/sitemap steps)
//   iac-validation.yml         -> CDK Validation & Dry-Run
//   cdk-dry-run.yml            -> CDK Validation & Dry-Run
//
// Not mirrored (GitHub-only): AI PR-review bots, deploy-lambda.yml,
// GitHub housekeeping jobs, actionlint (GitHub workflow YAML linter),
// shellcheck (continue-on-error in ci.yml anyway), Codecov uploads, and the
// optional AWS/S3 data sync (already optional in the workflows).

// True when the requested STAGE matches this stage (or 'all' is requested).
// Lets one Jenkinsfile drive both the full pipeline (STAGE=all, the default)
// and single-check jobs (STAGE=backend-lint, STAGE=frontend-checks, ...).
def runStage(String name) {
    return params.STAGE == 'all' || params.STAGE == name
}

// Posts a comment to the pull request this build belongs to. Only active for
// Multibranch Pipeline PR builds (env.CHANGE_ID is set). Best-effort: never
// fails the build. Requires a 'GITHUB_TOKEN' credential with repo scope; the
// GitHub Branch Source plugin additionally publishes the commit status (the
// green/red check on the PR) automatically.
def notifyPullRequest(String state, String message) {
    if (!env.CHANGE_ID) {
        return
    }
    try {
        withCredentials([string(credentialsId: 'GITHUB_TOKEN', variable: 'GITHUB_TOKEN')]) {
            sh """
                set +e
                curl -sS -X POST \
                    -H "Authorization: token \${GITHUB_TOKEN}" \
                    -H "Accept: application/vnd.github.v3+json" \
                    "https://api.github.com/repos/leonarduk/allotmint/issues/\${CHANGE_ID}/comments" \
                    -d '{"body": "${message} — ${env.BUILD_URL}"}' \
                    && echo "PR comment posted to #\${CHANGE_ID}" \
                    || echo "WARNING: failed to post PR comment"
            """
        }
    } catch (Exception e) {
        echo "WARNING: could not post PR comment: ${e.message}"
    }
}

pipeline {
    agent any

    parameters {
        string(name: 'BRANCH', defaultValue: '*/main',
               description: 'Branch/ref to build, e.g. */main or */feature/foo')
        choice(name: 'STAGE',
               choices: ['all', 'repo-hygiene', 'backend-lint', 'backend-integration',
                         'lambda-compat', 'validate-deps', 'py311-compat',
                         'frontend-checks', 'cdk-tests', 'cdk-validation',
                         'shell-tests', 'frontend-smoke'],
               description: "Which check to run. 'all' runs the full pipeline (GitHub Actions mirror). Single-check jobs pin one value, e.g. STAGE=backend-integration.")
        booleanParam(name: 'RUN_FRONTEND_SMOKE', defaultValue: false,
                     description: 'Run Playwright frontend smoke tests (mirrors ci.yml frontend-smoke). Requires network to download browsers.')
    }

    options {
        timeout(time: 180, unit: 'MINUTES')
    }

    stages {
        stage('Checkout') {
            steps {
                script {
                    if (env.CHANGE_ID) {
                        // Multibranch Pipeline PR build: the GitHub branch source
                        // has already checked out the PR revision. Skip the explicit
                        // checkout so we build the PR's code, not the default branch.
                        echo "Building PR #${env.CHANGE_ID} from branch-source checkout (${env.BRANCH_NAME})"
                    } else {
                        checkout([
                            $class: 'GitSCM',
                            branches: [[name: params.BRANCH]],
                            userRemoteConfigs: [[
                                url: 'https://github.com/leonarduk/allotmint.git',
                                credentialsId: 'GITHUB_TOKEN'
                            ]]
                        ])
                    }
                }
                stash includes: '**', excludes: '.git/**,.pytest_cache/**,**/__pycache__/**,**/node_modules/**,**/.venv*/**,**/htmlcov/**,**/coverage/**,**/test-results/**,**/dist/**,**/playwright-report/**', name: 'source', useDefaultExcludes: false
            }
        }

        // ci.yml `test` job (repo-hygiene checks; ungated in CI).
        // Runs at the workspace root (not an unstashed copy) because
        // check_architecture_diagrams.py shells out to `git ls-files`, which
        // needs the .git directory that the stash excludes.
        stage('Repo Hygiene') {
            when { expression { runStage('repo-hygiene') } }
            steps {
                script {
                    docker.image('python:3.12').inside('-u root -v /var/jenkins_home/.cache/pip:/root/.cache/pip') {
                        sh '''
                            set -euo pipefail
                            apt-get update && apt-get install -y git
                            python --version
                            pip install --upgrade pip setuptools wheel
                            pip install --no-cache-dir --retries 10 -r requirements.txt -r requirements-dev.txt
                            python scripts/check_branch_protection_required_checks.py
                            python scripts/check_lockfile_platform_coverage.py
                            python scripts/check_architecture_diagrams.py
                        '''
                    }
                }
            }
        }

        // ci.yml `backend-lint` job: ruff + black over backend/tests.
        // Jenkins runs a branch (not a PR), so mirror the non-PR path and lint
        // the whole tree via git ls-files. Runs at the workspace root for the
        // same .git reason as Repo Hygiene.
        stage('Backend Lint') {
            when { expression { runStage('backend-lint') } }
            steps {
                script {
                    docker.image('python:3.12').inside('-u root -v /var/jenkins_home/.cache/pip:/root/.cache/pip') {
                        sh '''
                            set -euo pipefail
                            apt-get update && apt-get install -y git
                            pip install --no-cache-dir --retries 10 -r requirements.txt -r requirements-dev.txt
                            FILES=$(git ls-files backend tests | grep '\\.py$' || true)
                            if [ -z "$FILES" ]; then
                                echo "No backend/tests Python files to lint."
                            else
                                echo "$FILES" | xargs -d '\\n' ruff check --config backend/pyproject.toml
                                echo "$FILES" | xargs -d '\\n' black --check --config backend/pyproject.toml
                            fi
                        '''
                    }
                }
            }
        }

        stage('Backend Tests') {
            parallel {
                // backend-integration.yml integration-tests job. AWS/S3 sync and
                // Codecov upload are optional in CI and skipped here.
                stage('Backend Integration Tests') {
                    when { expression { runStage('backend-integration') } }
                    steps {
                        dir('workspace-integration') {
                            unstash 'source'
                        }
                        script {
                            docker.image('python:3.12').inside('-u root -v /var/jenkins_home/.cache/pip:/root/.cache/pip') {
                                dir('workspace-integration') {
                                    sh '''
                                        set -euo pipefail
                                        apt-get update && apt-get install -y git
                                        pip install --upgrade pip
                                        pip install --no-cache-dir --retries 10 -r requirements.txt -r requirements-dev.txt
                                        python scripts/check_contract_version_sync.py
                                        test -f mypy.ini
                                        python -m mypy backend --config-file mypy.ini --show-error-codes --pretty --explicit-package-bases
                                        ALLOTMINT_SKIP_SNAPSHOT_WARM=true pytest --no-cov tests/backend/common/test_data_provider_parity.py -q
                                        export ALLOTMINT_SKIP_SNAPSHOT_WARM=true
                                        export OLLAMA_ENDPOINT=http://127.0.0.1:1
                                        python -m coverage erase
                                        mkdir -p test-results
                                        pytest tests --ignore=tests/live --ignore=tests/test_review_common.py --ignore=tests/test_ai_review_scripts.py --ignore=tests/scripts/test_n_review_issue.py --cov=backend --cov-report=xml --cov-report=html --cov-report=term --cov-fail-under=80 -q --junit-xml=test-results/junit.xml
                                        pytest tests/test_backend_api.py::test_health tests/test_accounts_api.py --cov=backend --cov-append --cov-report=xml --cov-report=term --cov-fail-under=80 -q
                                    '''
                                }
                            }
                        }
                    }
                    post {
                        always {
                            script {
                                if (fileExists('workspace-integration/test-results/junit.xml')) {
                                    junit 'workspace-integration/test-results/junit.xml'
                                }
                                if (fileExists('workspace-integration/htmlcov/index.html')) {
                                    publishHTML([
                                        reportDir: 'workspace-integration/htmlcov',
                                        reportFiles: 'index.html',
                                        reportName: 'Backend Coverage Report',
                                        allowMissing: false,
                                        alwaysLinkToLastBuild: true,
                                        keepAll: true
                                    ])
                                }
                            }
                        }
                    }
                }

                // ci.yml `lambda-compat` job: full pytest suite against the
                // Lambda-pinned backend/requirements.txt in an isolated venv.
                stage('Lambda Compat') {
                    when { expression { runStage('lambda-compat') } }
                    steps {
                        dir('workspace-lambda') {
                            unstash 'source'
                        }
                        script {
                            docker.image('python:3.12').inside('-u root -v /var/jenkins_home/.cache/pip:/root/.cache/pip') {
                                dir('workspace-lambda') {
                                    sh '''
                                        set -euo pipefail
                                        apt-get update && apt-get install -y git
                                        python -m venv .venv-lambda
                                        .venv-lambda/bin/pip install --upgrade pip
                                        .venv-lambda/bin/pip install --no-cache-dir --retries 10 -r backend/requirements.txt -r backend/requirements-test.txt
                                        mkdir -p test-results
                                        ALLOTMINT_SKIP_SNAPSHOT_WARM=true .venv-lambda/bin/pytest tests/ --ignore=tests/test_review_common.py --ignore=tests/test_ai_review_scripts.py --ignore=tests/scripts/test_n_review_issue.py --junit-xml=test-results/junit.xml
                                    '''
                                }
                            }
                        }
                    }
                    post {
                        always {
                            script {
                                if (fileExists('workspace-lambda/test-results/junit.xml')) {
                                    junit 'workspace-lambda/test-results/junit.xml'
                                }
                            }
                        }
                    }
                }

                // ci.yml `validate-backend-deps` job: clean-venv resolution and
                // startup import so runner pre-installs cannot mask problems.
                stage('Validate Backend Deps') {
                    when { expression { runStage('validate-deps') } }
                    steps {
                        dir('workspace-deps') {
                            unstash 'source'
                        }
                        script {
                            docker.image('python:3.12').inside('-u root -v /var/jenkins_home/.cache/pip:/root/.cache/pip') {
                                dir('workspace-deps') {
                                    sh '''
                                        set -euo pipefail
                                        apt-get update && apt-get install -y git
                                        python - << 'PY'
import re, sys
from pathlib import Path
lines = Path("backend/requirements.txt").read_text(encoding="utf-8").splitlines()
pkgs = [
    re.sub(r"[-_.]+", "-",
           re.sub(r"\\[.*?\\]", "",
                  re.split(r"[~>=<!;\\s#]", line)[0].strip())).lower()
    for line in lines
    if line.strip() and not line.strip().startswith(("#", "-"))
]
seen, dups = set(), []
for pkg in pkgs:
    if pkg in seen:
        dups.append(pkg)
    else:
        seen.add(pkg)
if dups:
    print(f"Duplicate package names in backend/requirements.txt: {dups}", file=sys.stderr)
    sys.exit(1)
print(f"No duplicate package names ({len(pkgs)} packages checked).")
PY
                                        python -m venv .venv-lambda-check
                                        .venv-lambda-check/bin/pip install --upgrade pip
                                        .venv-lambda-check/bin/pip install --dry-run -r backend/requirements.txt
                                        python -m venv .venv-root-startup
                                        .venv-root-startup/bin/pip install --upgrade pip
                                        .venv-root-startup/bin/pip install -r requirements.txt
                                        ALLOTMINT_SKIP_SNAPSHOT_WARM=true .venv-root-startup/bin/python -c 'from backend.local_api.main import app; assert app is not None'
                                    '''
                                }
                            }
                        }
                    }
                }

                // ci.yml `python-compatibility` job: lightweight 3.11 smoke.
                stage('Python 3.11 Compat') {
                    when { expression { runStage('py311-compat') } }
                    steps {
                        dir('workspace-py311') {
                            unstash 'source'
                        }
                        script {
                            docker.image('python:3.11').inside('-u root -v /var/jenkins_home/.cache/pip:/root/.cache/pip') {
                                dir('workspace-py311') {
                                    sh '''
                                        set -euo pipefail
                                        apt-get update && apt-get install -y git
                                        pip install --upgrade pip
                                        pip install --no-cache-dir --retries 10 -r requirements.txt -r requirements-dev.txt
                                        python scripts/check_contract_version_sync.py
                                        ALLOTMINT_SKIP_SNAPSHOT_WARM=true pytest --no-cov tests/test_backend_api.py::test_health tests/backend/common/test_data_provider_parity.py -q
                                    '''
                                }
                            }
                        }
                    }
                }
            }
        }

        // ci.yml `frontend-checks` + frontend-tests.yml frontend-tests jobs.
        // Repo canonical install is npm (frontend/package-lock.json);
        // frontend-tests.yml uses pnpm, so Jenkins uses npm instead.
        // The production build itself runs inside the CDK Validation & Dry-Run
        // stage (needed for synth), matching iac-validation.yml / cdk-dry-run.yml.
        stage('Frontend Checks') {
            when { expression { runStage('frontend-checks') } }
            steps {
                dir('workspace-frontend') {
                    unstash 'source'
                }
                script {
                    docker.image('node:24').inside('-u root -v /var/jenkins_home/.cache/npm:/root/.npm') {
                        dir('workspace-frontend') {
                            sh '''
                                set -euo pipefail
                                apt-get update && apt-get install -y git
                                node --version
                                cd frontend
                                npm ci
                                npm run lint
                                npm run type-check
                                # Single run with coverage: superset of ci.yml's
                                # `npm test -- --run` and frontend-tests.yml's
                                # `--run --coverage`, so tests execute once.
                                npm run coverage
                                npm audit --audit-level=high
                            '''
                        }
                    }
                    // frontend-tests.yml also runs SPA contract sync and a
                    // sitemap health check; both need Python.
                    docker.image('python:3.12').inside('-u root -v /var/jenkins_home/.cache/pip:/root/.cache/pip') {
                        dir('workspace-frontend') {
                            sh '''
                                set -euo pipefail
                                pip install --no-cache-dir requests
                                python scripts/check_contract_version_sync.py
                                python scripts/site_healthcheck.py
                            '''
                        }
                    }
                }
            }
        }

        stage('CDK') {
            parallel {
                // ci.yml `cdk-tests` job: cdk/tests against the root requirements set.
                stage('CDK Tests') {
                    when { expression { runStage('cdk-tests') } }
                    steps {
                        dir('workspace-cdk-tests') {
                            unstash 'source'
                        }
                        script {
                            docker.image('python:3.12').inside('-u root -v /var/jenkins_home/.cache/pip:/root/.cache/pip') {
                                dir('workspace-cdk-tests') {
                                    sh '''
                                        set -euo pipefail
                                        apt-get update && apt-get install -y git
                                        pip install --no-cache-dir --retries 10 -r requirements.txt -r requirements-dev.txt
                                        test -d cdk/tests && test -n "$(ls -A cdk/tests/)"
                                        pytest cdk/tests/ --no-cov
                                    '''
                                }
                            }
                        }
                    }
                }

                // iac-validation.yml cdk-validation + cdk-dry-run.yml cdk-synth.
                // Runs cdk/tests against cdk/requirements.txt in an isolated venv,
                // then both synth invocations (default app + prod dry-run) with
                // placeholder env values. No AWS credentials required.
                // cdk.json runs `python3 app.py` and the stacks import aws_cdk,
                // so the venv holding cdk/requirements.txt must be on PATH when
                // the cdk CLI spawns python. node:24 (bookworm) ships Python
                // 3.11, matching the repo's .python-version.
                stage('CDK Validation & Dry-Run') {
                    when { expression { runStage('cdk-validation') } }
                    steps {
                        dir('workspace-cdk') {
                            unstash 'source'
                        }
                        script {
                            docker.image('node:24').inside('-u root -v /var/jenkins_home/.cache/npm:/root/.npm') {
                                dir('workspace-cdk') {
                                    sh '''
                                        set -euo pipefail
                                        apt-get update && apt-get install -y git python3 python3-venv
                                        npm ci
                                        cd frontend && npm ci && npm run build && cd ..
                                        python3 -m venv .venv-cdk
                                        .venv-cdk/bin/pip install --upgrade pip
                                        .venv-cdk/bin/pip install --no-cache-dir pytest -r cdk/requirements.txt
                                        .venv-cdk/bin/pytest cdk/tests -v --tb=short --override-ini="addopts="
                                        # cdk.json app is `python3 app.py`; point python3 at the venv.
                                        export PATH="$PWD/.venv-cdk/bin:$PATH"
                                        cd cdk
                                        JWT_SECRET=ci-cdk-validation-secret GOOGLE_CLIENT_ID=ci-cdk-validation-client-id.apps.googleusercontent.com ../node_modules/.bin/cdk synth
                                        JWT_SECRET=dry-run-placeholder GOOGLE_CLIENT_ID=dry-run-placeholder.apps.googleusercontent.com GITHUB_DEPLOY_ROLE_ARN=arn:aws:iam::123456789012:role/dry-run-placeholder npx cdk synth BackendLambdaStack StaticSiteStack -c prod=true --output /tmp/cdk.out
                                        cd ..
                                        grep -v '^[[:space:]]*#' .github/workflows/deploy-lambda.yml | grep -E 'cdk diff.*--method=template([[:space:]]|$)' >/dev/null || {
                                            echo "deploy-lambda.yml does not contain an active 'cdk diff --method=template' invocation." >&2
                                            exit 1
                                        }
                                    '''
                                }
                            }
                        }
                    }
                }
            }
        }

        // ci.yml `shell-tests` job: bats tests for deploy shell scripts.
        // All AWS CLI calls in these tests are mocked, so no network needed.
        stage('Shell Tests') {
            when { expression { runStage('shell-tests') } }
            steps {
                dir('workspace-shell') {
                    unstash 'source'
                }
                script {
                    docker.image('node:24').inside('-u root -v /var/jenkins_home/.cache/npm:/root/.npm') {
                        dir('workspace-shell') {
                            sh '''
                                set -euo pipefail
                                apt-get update && apt-get install -y git
                                npx --yes bats@1.13.0 tests/bash/*.bats
                            '''
                        }
                    }
                }
            }
        }

        // ci.yml `frontend-smoke` job (optional; needs network for browser download).
        stage('Frontend Smoke') {
            when {
                allOf {
                    expression { runStage('frontend-smoke') }
                    expression { params.RUN_FRONTEND_SMOKE }
                }
            }
            steps {
                dir('workspace-smoke') {
                    unstash 'source'
                }
                script {
                    docker.image('node:24').inside('-u root -v /var/jenkins_home/.cache/npm:/root/.npm') {
                        dir('workspace-smoke') {
                            sh '''
                                set -euo pipefail
                                apt-get update && apt-get install -y git
                                cd frontend
                                npm ci
                                npm run build:preview
                                if grep -q '<base href="http' dist/index.html; then
                                    echo "Built index.html contains an absolute <base href> which breaks routing." >&2
                                    exit 1
                                fi
                                npx playwright install --with-deps chromium
                                npx playwright test --config playwright.config.ts tests/smoke.spec.ts tests/navActiveState.spec.ts
                            '''
                        }
                    }
                }
            }
        }
    }

post {
    success {
        echo '✅ Pipeline completed successfully'
        notifyPullRequest('success', '✅ Build succeeded')
        emailext(
            to: 'steveleonard11@gmail.com',
            subject: "PASS: ${env.JOB_NAME} #${env.BUILD_NUMBER}",
            body: "Batch job ${env.JOB_NAME} #${env.BUILD_NUMBER} PASSED.\n\nBuild: ${env.BUILD_URL}"
        )
    }
    failure {
        echo '❌ Pipeline failed. Check logs for details.'
        notifyPullRequest('failure', '❌ Build failed')
        emailext(
            to: 'steveleonard11@gmail.com',
            subject: "FAIL: ${env.JOB_NAME} #${env.BUILD_NUMBER}",
            body: "Batch job ${env.JOB_NAME} #${env.BUILD_NUMBER} FAILED.\n\nBuild: ${env.BUILD_URL}",
            attachLog: true
        )
    }
}
}
