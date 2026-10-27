pipeline {
    agent {
        node {
            label ''
            customWorkspace '/opt/work'
        }
    }

    options {
        disableConcurrentBuilds(abortPrevious: true)
    }

    stages {
        stage('Check') {
            steps {
                sh 'pwd'
                sh 'git log -1 --oneline'
                sh 'ls -al'
            }
        }
    }
}
