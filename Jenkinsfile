pipeline {
    agent any  // Start with any agent to do the checkout
    
    stages {
        stage('Checkout') {
            steps {
                checkout([
                    $class: 'GitSCM',
                    branches: [[name: '*/main']],
                    userRemoteConfigs: [[
                        url: 'https://github.com/leonarduk/allotmint.git',
                        credentialsId: 'GITHUB_TOKEN'
                    ]]
                ])
                // Exclude .git to avoid permission issues during unstash
                stash includes: '**', excludes: '.git/**', name: 'source', useDefaultExcludes: false
            }
        }
        
        stage('Build & Test') {
            parallel {
                stage('Python Tests') {
                    steps {
                        unstash 'source'
                        script {
                            docker.image('python:3.11').inside('-u root -v /var/jenkins_home/.cache/pip:/root/.cache/pip') {
                                sh '''
                                    apt-get update && apt-get install -y git
                                    python --version
                                    pip install --upgrade pip setuptools wheel
                                    pip install --no-cache-dir -r requirements.txt
                                    pip install --no-cache-dir pytest pytest-cov jinja2 python-multipart
                                    pytest tests --cov=backend --cov-report=html || true
                                '''
                            }
                        }
                    }
                    post {
                        always {
                            script {
                                if (fileExists('htmlcov/index.html')) {
                                    publishHTML([
                                        reportDir: 'htmlcov',
                                        reportFiles: 'index.html',
                                        reportName: 'Python Coverage Report'
                                    ])
                                } else {
                                    echo "Coverage report not found"
                                }
                            }
                        }
                    }
                }

                stage('Node.js Build') {
                    steps {
                        unstash 'source'
                        script {
                            docker.image('node:20').inside('-u root -v /var/jenkins_home/.cache/npm:/root/.npm') {
                                sh '''
                                    apt-get update && apt-get install -y git
                                    node --version
                                    cd frontend
                                    npm ci
                                    npm test || true
                                    npm run build
                                '''
                            }
                        }
                    }
                    post {
                        always {
                            junit 'frontend/test-results/**/*.xml'
                        }
                    }
                }

                stage('Java Build') {
                    when {
                        expression { fileExists('pom.xml') }
                    }
                    steps {
                        // Unstash the code
                        unstash 'source'
                        script {
                            docker.image('maven:3.9.6-eclipse-temurin-17').inside('-u root -v /var/jenkins_home/.m2:/root/.m2') {
                                sh '''
                                    apt-get update && apt-get install -y git
                                    mvn clean install
                                '''
                            }
                        }
                    }
                    post {
                        always {
                            junit '**/target/surefire-reports/*.xml'
                        }
                    }
                }
            }
        }
    }

    post {
        success {
            echo '✅ Build & tests completed successfully'
        }
        failure {
            echo '❌ Pipeline failed. Check logs for details.'
        }
    }
}
