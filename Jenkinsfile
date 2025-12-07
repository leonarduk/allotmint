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
                    agent {
                        docker {
                            image 'python:3.11'
                            args '-u root'
                        }
                    }
                    steps {
                        // Unstash the code
                        unstash 'source'
                        sh '''
                            apt-get update && apt-get install -y git
                            python --version
                            pip install --upgrade pip setuptools wheel
                            pip install -r requirements.txt
                            pip install pytest pytest-cov
                            pip install jinja2 python-multipart
                            pytest tests --cov=backend --cov-report=html
                        '''
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
                    agent {
                        docker {
                            image 'node:20'
                            args '-u root'
                        }
                    }
                    steps {
                        // Unstash the code
                        unstash 'source'
                        sh '''
                            apt-get update && apt-get install -y git
                            node --version
                            cd frontend
                            npm ci
                            npm test
                        '''
                    }
                }
                stage('Java Build') {
                    when {
                        expression { fileExists('pom.xml') }
                    }
                    agent {
                        docker {
                            image 'maven:3.9.6-eclipse-temurin-17'
                            args '-u root'
                        }
                    }
                    steps {
                        // Unstash the code
                        unstash 'source'
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
