#!/usr/bin/env bash
# Provision the lab proxy; Jenkins continues listening on loopback port 8080.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
if [[ "$EUID" -ne 0 ]]; then
    exec sudo bash "$ROOT/scripts/setup_jenkins_proxy.sh" "$@"
fi

# Run this only on the controller, never on the separate SocketCAN agent.
curl --noproxy '*' --fail --silent --show-error --connect-timeout 5 --max-time 10 \
    http://127.0.0.1:8080/login >/dev/null || {
    echo 'Start the local Jenkins controller before provisioning its proxy.' >&2
    exit 1
}

SITE=/etc/nginx/sites-available/jenkins.ice.tech
ENABLED=/etc/nginx/sites-enabled/jenkins.ice.tech
if [[ -e "$ENABLED" || -L "$ENABLED" ]]; then
    if [[ ! -L "$ENABLED" || "$(readlink "$ENABLED")" != "$SITE" ]]; then
        echo "Existing site entry is not managed by this installer: $ENABLED" >&2
        exit 1
    fi
fi

if ! command -v nginx >/dev/null 2>&1; then
    apt-get update
    apt-get install -y nginx
fi
backup="$(mktemp -d)"
had_site=0
had_link=0
[[ ! -e "$SITE" ]] || { cp -p "$SITE" "$backup/site"; had_site=1; }
[[ ! -L "$ENABLED" ]] || had_link=1
rollback() {
    rc=$?
    if ((rc != 0)); then
        if ((had_site)); then cp -p "$backup/site" "$SITE"; else rm -f "$SITE"; fi
        if ((!had_link)); then rm -f "$ENABLED"; fi
    fi
    rm -rf "$backup"
}
trap rollback EXIT
install -m 0644 "$ROOT/config/jenkins.nginx.conf" "$SITE"
if ((!had_link)); then ln -s "$SITE" "$ENABLED"; fi
nginx -t
systemctl enable nginx
if systemctl is-active --quiet nginx; then
    systemctl reload nginx
else
    systemctl start nginx
fi
curl --noproxy '*' --fail --silent --show-error \
    --retry 5 --retry-all-errors --retry-delay 1 --connect-timeout 5 --max-time 20 \
    --resolve jenkins.ice.tech:80:127.0.0.1 \
    http://jenkins.ice.tech/login >/dev/null
python3 - <<'PY'
from pathlib import Path
hosts = Path('/etc/hosts')
contents = hosts.read_text()
present = any('jenkins.ice.tech' in line.split('#', 1)[0].split()[1:]
              for line in contents.splitlines())
if not present:
    with hosts.open('a') as stream:
        stream.write(('' if contents.endswith('\n') else '\n') +
                     '127.0.0.1 jenkins.ice.tech\n')
PY
echo 'Proxy verified: http://jenkins.ice.tech -> 127.0.0.1:8080'
echo 'On the browser machine, resolve jenkins.ice.tech to the server IP using DNS or its hosts file.'
