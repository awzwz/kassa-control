#!/bin/bash
# Развёртывание на сервер DigitalOcean: подготовка машины (однократно), копирование кода, сборка, запуск.
#   tools/deploy.sh <ip>            — полное обновление (код + сборка + перезапуск)
#   tools/deploy.sh <ip> --logs     — только показать логи
# Ключ SSH: ~/.ssh/datathon_do. Настройки сервера берутся из локального файла .env (API_KEY, DOMAIN).
set -euo pipefail
IP="${1:?укажите IP сервера}"
MODE="${2:-deploy}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SSH=(ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 -o ServerAliveInterval=15 -i "$HOME/.ssh/datathon_do" "root@$IP")

[ -f "$ROOT/.env" ] || { echo "нет $ROOT/.env (скопируйте .env.example)"; exit 1; }
# shellcheck disable=SC1091
source "$ROOT/.env"
: "${API_KEY:?в .env нет API_KEY}"; : "${DOMAIN:?в .env нет DOMAIN}"

echo "== жду ssh $IP"
ok=0
for _ in $(seq 1 60); do
  if "${SSH[@]}" true 2>/dev/null; then ok=$((ok+1)); [ "$ok" -ge 2 ] && break; else ok=0; fi
  sleep 3
done
[ "$ok" -ge 2 ] || { echo "ssh недоступен"; exit 1; }

if [ "$MODE" = "--logs" ]; then
  "${SSH[@]}" 'cd /srv/kassa-control && docker compose ps --format "table {{.Name}}\t{{.Status}}" && docker compose logs --tail=40 --no-color'
  exit 0
fi

echo "== подготовка машины (пропускается, если уже сделана)"
"${SSH[@]}" 'bash -s' <<'EOF'
set -e
export DEBIAN_FRONTEND=noninteractive
if ! command -v docker >/dev/null; then
  apt-get update -qq >/dev/null
  apt-get install -y -qq ca-certificates curl ufw rsync >/dev/null 2>&1
  curl -fsSL https://get.docker.com | sh >/dev/null 2>&1
fi
command -v rsync >/dev/null || apt-get install -y -qq rsync >/dev/null 2>&1
ufw allow 22/tcp >/dev/null; ufw allow 80/tcp >/dev/null; ufw allow 443/tcp >/dev/null; ufw --force enable >/dev/null
mkdir -p /srv/kassa-control
echo "docker $(docker --version | cut -d, -f1 | cut -d' ' -f3) · compose $(docker compose version --short) · cpu $(nproc) · ram $(free -g | awk '/Mem/{print $2}') GB · диск $(df -h / | awk 'NR==2{print $4}') свободно"
EOF

echo "== копирую код"
rsync -az --delete --exclude .venv --exclude data --exclude .git --exclude .env --exclude models --exclude out \
  -e "ssh -i $HOME/.ssh/datathon_do" "$ROOT/" "root@$IP:/srv/kassa-control/"
"${SSH[@]}" "printf 'API_KEY=%s\nDATA_DIR=/data\nMAX_UPLOAD_MB=200\nDEADLINE_SEC=240\nRESULT_TTL_HOURS=24\nDOMAIN=%s\n' '$API_KEY' '$DOMAIN' > /srv/kassa-control/.env && chmod 600 /srv/kassa-control/.env"

echo "== сборка и запуск"
"${SSH[@]}" 'cd /srv/kassa-control && docker compose up -d --build --remove-orphans 2>&1 | grep -E "Built|Started|Created|Running|Error|error" | tail -8; sleep 4; docker compose ps --format "table {{.Name}}\t{{.Status}}"'

echo "== проверка снаружи: https://$DOMAIN/health"
CODE=000
for _ in $(seq 1 30); do
  CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "https://$DOMAIN/health" 2>/dev/null || true)
  [ "$CODE" = "200" ] && break
  sleep 5
done
echo "https → $CODE"
[ "$CODE" = "200" ] && curl -s --max-time 10 "https://$DOMAIN/health" && echo
