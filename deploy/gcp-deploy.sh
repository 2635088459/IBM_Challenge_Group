#!/usr/bin/env bash
# deploy/gcp-deploy.sh — Deploy the whole stack to one Google Compute Engine VM.
#
#   ./deploy/gcp-deploy.sh            # first run creates the VM; later runs redeploy the current code
#
# Optional env:
#   PROJECT  (default: gcloud's current project)   ZONE (default: us-west1-b)
#   VM       (default: customs-demo)               MACHINE (default: e2-medium — next build needs ~2 GB)
#   SITE_PASSWORD  set to require a shared login (user "demo"); default: public, no login
#   SEED=1         reset the demo data (default: only on the first deploy)
#
# The site is served over HTTPS at https://<static-ip>.sslip.io (public unless SITE_PASSWORD is set).
# backend/.env (secrets) is copied straight to the VM and never enters git or the images.
set -euo pipefail

cd "$(dirname "$0")/.."

PROJECT="${PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
ZONE="${ZONE:-us-west1-b}"
REGION="${ZONE%-*}"
VM="${VM:-customs-demo}"
MACHINE="${MACHINE:-e2-medium}"
IP_NAME="${VM}-ip"
CREDS=deploy/.credentials
SITE_USER="demo"
GC=(gcloud --project "$PROJECT" --quiet)

[[ -f backend/.env ]] || { echo "backend/.env is missing — it holds the API keys the VM needs." >&2; exit 1; }

SITE_PASSWORD="${SITE_PASSWORD:-}"

echo "==> Project $PROJECT, zone $ZONE, VM $VM ($MACHINE)"
"${GC[@]}" services enable compute.googleapis.com

# ── Static IP (so the sslip.io hostname and HTTPS certificate stay valid) ──
if ! "${GC[@]}" compute addresses describe "$IP_NAME" --region "$REGION" >/dev/null 2>&1; then
  "${GC[@]}" compute addresses create "$IP_NAME" --region "$REGION"
fi
IP="$("${GC[@]}" compute addresses describe "$IP_NAME" --region "$REGION" --format='value(address)')"
SITE="${IP//./-}.sslip.io"

# ── Firewall: web traffic only (SSH comes from the default network rules) ──
if ! "${GC[@]}" compute firewall-rules describe "${VM}-web" >/dev/null 2>&1; then
  "${GC[@]}" compute firewall-rules create "${VM}-web" \
    --allow tcp:80,tcp:443 --target-tags "${VM}-web" --direction INGRESS
fi

# ── VM with Docker ──
FIRST_DEPLOY=0
if ! "${GC[@]}" compute instances describe "$VM" --zone "$ZONE" >/dev/null 2>&1; then
  FIRST_DEPLOY=1
  "${GC[@]}" compute instances create "$VM" --zone "$ZONE" \
    --machine-type "$MACHINE" --address "$IP" --tags "${VM}-web" \
    --image-family debian-12 --image-project debian-cloud --boot-disk-size 30GB \
    --metadata startup-script='#!/bin/bash
      command -v docker >/dev/null || curl -fsSL https://get.docker.com | sh'
  echo "==> Waiting for Docker to finish installing on the VM…"
  for _ in $(seq 1 40); do
    "${GC[@]}" compute ssh "$VM" --zone "$ZONE" --command "sudo docker compose version" >/dev/null 2>&1 && break
    sleep 10
  done
fi

# ── Ship the working tree (no git history, secrets, dependencies or build output) ──
echo "==> Uploading code"
BUNDLE="$(mktemp -d)/app.tgz"
COPYFILE_DISABLE=1 tar czf "$BUNDLE" \
  --exclude .git --exclude node_modules --exclude .venv --exclude .next \
  --exclude '__pycache__' --exclude '*.db' --exclude backend/.env --exclude 'deploy/.credentials' \
  --exclude backend/celerybeat-schedule --exclude backend/evidence_store \
  .
"${GC[@]}" compute scp --zone "$ZONE" "$BUNDLE" "$VM":~/app.tgz
"${GC[@]}" compute scp --zone "$ZONE" backend/.env "$VM":~/backend.env
rm -f "$BUNDLE"

[[ "${SEED:-$FIRST_DEPLOY}" == "1" ]] && DO_SEED=1 || DO_SEED=0

echo "==> Building and starting on the VM (first build takes a few minutes)"
"${GC[@]}" compute ssh "$VM" --zone "$ZONE" --command "bash -s" <<REMOTE
set -euo pipefail
mkdir -p ~/app && tar xzf ~/app.tgz -C ~/app && rm ~/app.tgz
mv ~/backend.env ~/app/backend/.env && chmod 600 ~/app/backend/.env
cd ~/app

AUTH_BLOCK=""
if [ -n '$SITE_PASSWORD' ]; then
  HASH=\$(sudo docker run --rm caddy:2.8 caddy hash-password --plaintext '$SITE_PASSWORD')
  AUTH_BLOCK="basic_auth {
		$SITE_USER \$HASH
	}"
fi
# HTTPS on the sslip.io name, plus plain HTTP on the bare IP for networks that
# block wildcard-DNS domains like sslip.io. Access logs help diagnose "can't open".
cat > deploy/Caddyfile <<CADDY
$SITE, http://$IP {
	encode gzip
	log
	\$AUTH_BLOCK
	reverse_proxy frontend:3000
}
CADDY

COMPOSE="sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml"
\$COMPOSE up -d --build
# Caddy is not recreated when only its mounted Caddyfile changes — reload it explicitly
\$COMPOSE exec -T caddy caddy reload --config /etc/caddy/Caddyfile </dev/null
# -T and </dev/null: this script arrives on stdin, and \`run\` would otherwise swallow the rest of it
\$COMPOSE run --rm -T api alembic upgrade head </dev/null
if [ "$DO_SEED" = "1" ]; then \$COMPOSE run --rm -T api python scripts/seed.py </dev/null; fi
\$COMPOSE ps --format 'table {{.Name}}\t{{.Status}}'
REMOTE

echo
echo "==> Live at: https://$SITE"
echo "    Fallback (if a network blocks sslip.io): http://$IP"
if [[ -n "$SITE_PASSWORD" ]]; then
  printf 'url=https://%s\nuser=%s\npassword=%s\n' "$SITE" "$SITE_USER" "$SITE_PASSWORD" > "$CREDS"
  chmod 600 "$CREDS"
  echo "    Login:   $SITE_USER / $SITE_PASSWORD   (saved in $CREDS)"
else
  rm -f "$CREDS"
  echo "    Public — no login required"
fi
