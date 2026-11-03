#!/usr/bin/env bash
# Start the provisioned local validation controller as the current non-root user.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
if [[ "$EUID" -eq 0 ]]; then
    echo 'Run the Jenkins controller as an ordinary user.' >&2
    exit 1
fi
command -v java >/dev/null || { echo 'Java 21+ is required.' >&2; exit 1; }
test -s "$ROOT/build-jenkins/jenkins.war"
test -d "$ROOT/build-jenkins/home/plugins"
export JENKINS_HOME="$ROOT/build-jenkins/home"
exec java -Xms128m -Xmx512m -Djava.awt.headless=true \
    -Djenkins.install.runSetupWizard=false \
    -Dhudson.plugins.git.GitSCM.ALLOW_LOCAL_CHECKOUT=true \
    -jar "$ROOT/build-jenkins/jenkins.war" \
    --httpListenAddress=127.0.0.1 --httpPort=8080
