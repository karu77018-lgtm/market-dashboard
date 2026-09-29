#!/bin/sh
set -eu
test "$(id -u)" -eq 0 || { echo "run as root"; exit 1; }
id moomoo >/dev/null 2>&1 || useradd --system --home /var/lib/moomoo-collector --shell /usr/sbin/nologin moomoo
install -d -o moomoo -g moomoo -m 700 /var/lib/moomoo-collector /var/lib/moomoo-collector/data
install -d -m 755 /opt/moomoo-collector /etc/moomoo-collector
cp moomoo_collector.py moomoo-oauth-init.py requirements.txt /opt/moomoo-collector/
python3 -m venv /opt/moomoo-collector/venv
/opt/moomoo-collector/venv/bin/pip install --disable-pip-version-check -r /opt/moomoo-collector/requirements.txt
test -f /etc/moomoo-collector/config.json || cp config.example.json /etc/moomoo-collector/config.json
cp moomoo-collector.service /etc/systemd/system/
systemctl daemon-reload
echo "Installed. OAuth must be completed before enabling the service."
