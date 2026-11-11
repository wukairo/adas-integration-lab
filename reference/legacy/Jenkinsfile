pipeline {
    agent { label 'linux-socketcan' }

    options {
        timestamps()
        timeout(time: 30, unit: 'MINUTES')
        disableConcurrentBuilds()
        skipDefaultCheckout(true)
        buildDiscarder(logRotator(numToKeepStr: '20', artifactDaysToKeepStr: '14'))
    }

    triggers { pollSCM('H/5 * * * *') }

    environment {
        BUILD_DIR = 'build-ci'
        REPORT_DIR = 'build-ci/reports/ci'
        VENV = '.venv'
        CAN_INTERFACE = 'vcan0'
    }

    stages {
        stage('Checkout') {
            steps {
                deleteDir()
                checkout scm
                sh '''#!/usr/bin/env bash
                    set -euo pipefail
                    mkdir -p "$REPORT_DIR"
                    git rev-parse HEAD | tee "$REPORT_DIR/commit.txt"
                '''
            }
        }

        stage('Environment') {
            steps {
                sh '''#!/usr/bin/env bash
                    set -euo pipefail
                    mkdir -p "$REPORT_DIR"
                    {
                        date -u +%Y-%m-%dT%H:%M:%SZ
                        git rev-parse HEAD
                        uname -a
                        c++ --version | head -n 1
                        cmake --version | head -n 1
                        python3 --version
                        cppcheck --version
                        ip -details link show dev "$CAN_INTERFACE"
                    } 2>&1 | tee "$REPORT_DIR/environment.txt"

                    python3 - "$CAN_INTERFACE" <<'PYTHON'
import socket, sys
sys.path.insert(0, 'integration')
from common import virtual_can_problem
interface = sys.argv[1]
problem = virtual_can_problem(interface)
if problem:
    raise SystemExit(problem)
with socket.socket(socket.PF_CAN, socket.SOCK_RAW, socket.CAN_RAW) as bus:
    bus.bind((interface,))
PYTHON

                    python3 -m venv "$VENV"
                    "$VENV/bin/python" -m pip install --upgrade pip
                    "$VENV/bin/python" -m pip install -r requirements.txt
                '''
            }
        }

        stage('Configure') {
            steps {
                sh '''#!/usr/bin/env bash
                    set -euo pipefail
                    cmake -S . -B "$BUILD_DIR" \
                      -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON \
                      2>&1 | tee "$REPORT_DIR/configure.log"
                '''
            }
        }

        stage('Build') {
            steps {
                sh '''#!/usr/bin/env bash
                    set -euo pipefail
                    cmake --build "$BUILD_DIR" --parallel 2 \
                      2>&1 | tee "$REPORT_DIR/build.log"
                '''
            }
        }

        stage('Static Analysis') {
            steps {
                sh '''#!/usr/bin/env bash
                    set -euo pipefail
                    "$VENV/bin/python" scripts/static_analysis.py \
                      --run-dir "$REPORT_DIR/static-analysis"
                '''
            }
        }

        stage('Unit Test') {
            steps {
                sh '''#!/usr/bin/env bash
                    set -euo pipefail
                    "$VENV/bin/python" scripts/run_tests.py --suite unit \
                      --build-dir "$BUILD_DIR" --run-dir "$REPORT_DIR/unit"
                '''
            }
        }

        stage('Integration Test') {
            options { timeout(time: 10, unit: 'MINUTES') }
            steps {
                sh '''#!/usr/bin/env bash
                    set -euo pipefail
                    "$VENV/bin/python" scripts/run_tests.py --suite integration \
                      --build-dir "$BUILD_DIR" --interface "$CAN_INTERFACE" \
                      --run-dir "$REPORT_DIR/integration"
                '''
            }
        }

        stage('System Information') {
            steps {
                sh '''#!/usr/bin/env bash
                    set -euo pipefail
                    "$VENV/bin/python" scripts/collect_system_info.py \
                      --build-dir "$BUILD_DIR" --output "$REPORT_DIR/system_info.json"
                '''
            }
        }

        stage('Package') {
            steps {
                sh '''#!/usr/bin/env bash
                    set -euo pipefail
                    "$VENV/bin/python" scripts/package_artifact.py \
                      --build-dir "$BUILD_DIR" --output-dir "$BUILD_DIR/package" \
                      --commit "$(git rev-parse HEAD)" --build-number "$BUILD_NUMBER"
                    test -s "$REPORT_DIR/unit/summary.json"
                    test -s "$REPORT_DIR/integration/summary.json"
                    test -s "$REPORT_DIR/system_info.json"
                '''
            }
        }
    }

    post {
        always {
            script {
                if (fileExists('scripts/collect_system_info.py')) {
                    sh returnStatus: true, script: '''#!/usr/bin/env bash
                        python3 scripts/collect_system_info.py --build-dir "$BUILD_DIR" \
                          --output "$REPORT_DIR/system_info_final.json"
                    '''
                }
            }
            archiveArtifacts artifacts: 'build-ci/reports/ci/**,build-ci/package/**,build-ci/adas_app',
                allowEmptyArchive: true, fingerprint: true
        }
    }
}
