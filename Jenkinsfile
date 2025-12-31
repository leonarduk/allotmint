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
                // Stash the entire workspace for parallel stages
                stash includes: '**', name: 'source', useDefaultExcludes: false
            }
        }
        
        stage('Build & Test') {
            parallel {
                stage('Python Tests') {
                    steps {
                        unstash 'source'
                        script {
                            docker.image('python:3.11').inside('-u root') {
                                sh '''
                                    apt-get update && apt-get install -y git
                                    python --version
                                    pip install --upgrade pip setuptools wheel
                                    pip install -r requirements.txt
                                    pip install pytest pytest-cov jinja2 python-multipart
                                    pytest tests --cov=backend --cov-report=html
                                '''
                            }
                        }
                    }
                    post {
                        always {
                            archiveArtifacts artifacts: 'htmlcov/**', fingerprint: true, allowEmptyArchive: true
                            publishHTML([
                                allowMissing: false,
                                keepAll: true,
                                alwaysLinkToLastBuild: true,
                                reportDir: 'htmlcov',
                                reportFiles: 'index.html',
                                reportName: 'Python Coverage Report'
                            ])
                        }
                    }
                }
                stage('Node.js Build') {
                    steps {
                        unstash 'source'
                        script {
                            docker.image('node:20').inside('-u root') {
                                sh '''
                                    apt-get update && apt-get install -y git
                                    node --version
                                    cd frontend
                                    npm ci
                                    npm test
                                    npm run build
                                '''
                            }
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
                            docker.image('maven:3.9.6-eclipse-temurin-17').inside('-u root') {
                                sh '''
                                    apt-get update && apt-get install -y git
                                    mvn clean install
                                '''
                            }
                        }
                    }
                }
            }
        }
    }
}
