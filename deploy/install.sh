#!/usr/bin/env bash
# Production install for Linux (Ubuntu/Debian). Run as root or with sudo.
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/captcha-solver}"
SERVICE_USER="${SERVICE_USER:-captcha}"
REPO_SRC="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> Installing captcha-solver to ${INSTALL_DIR}"

if ! id "$SERVICE_USER" &>/dev/null; then
  useradd --system --home "$INSTALL_DIR" --shell /usr/sbin/nologin "$SERVICE_USER"
fi

apt-get update -qq
apt-get install -y --no-install-recommends \
  python3 python3-venv python3-pip xvfb \
  libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
  libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
  libgbm1 libasound2t64 libpango-1.0-0 libcairo2 2>/dev/null || \
apt-get install -y --no-install-recommends \
  python3 python3-venv python3-pip xvfb \
  libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
  libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
  libgbm1 libasound2 libpango-1.0-0 libcairo2

mkdir -p "$INSTALL_DIR"
rsync -a --delete \
  --exclude '.git' --exclude '.venv' --exclude '__pycache__' \
  --exclude '.proxy.env' --exclude '.env' \
  --exclude 'github_signup*.html' --exclude '*.png' \
  "$REPO_SRC/" "$INSTALL_DIR/"

python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"
"$INSTALL_DIR/venv/bin/python" -m playwright install chromium

if [[ ! -f "$INSTALL_DIR/common/mistral.json" ]]; then
  cp "$INSTALL_DIR/common/mistral.json.example" "$INSTALL_DIR/common/mistral.json"
  echo "Created common/mistral.json — edit models or use dashboard Global Setup"
fi

if [[ ! -f "$INSTALL_DIR/common/apikey.txt" ]]; then
  cp "$INSTALL_DIR/common/apikey.example.txt" "$INSTALL_DIR/common/apikey.txt"
  echo "Created common/apikey.txt — add Mistral keys for image challenges"
fi

chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
chmod 600 "$INSTALL_DIR/common/apikey.txt" "$INSTALL_DIR/common/mistral.json" 2>/dev/null || true

install -m 644 "$INSTALL_DIR/deploy/captcha-solver.service" /etc/systemd/system/captcha-solver.service
systemctl daemon-reload
systemctl enable captcha-solver.service

echo ""
echo "==> Done. Next steps:"
echo "  1. Add Mistral keys: ${INSTALL_DIR}/common/apikey.txt (for reCAPTCHA/hCaptcha images)"
echo "  2. Set models: ${INSTALL_DIR}/common/mistral.json or http://127.0.0.1:8877/dashboard → Global Setup"
echo "  3. Optional Arkose: download models into ${INSTALL_DIR}/arkose/models/"
echo "  4. Optional env overrides: deploy/env.optional.example → ${INSTALL_DIR}/.env + systemd EnvironmentFile"
echo "  5. sudo systemctl start captcha-solver.service"
echo "  6. curl http://127.0.0.1:8877/health"
echo "  7. Dashboard: http://127.0.0.1:8877/dashboard"
