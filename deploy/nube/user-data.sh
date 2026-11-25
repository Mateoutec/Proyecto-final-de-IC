#!/bin/bash
# EC2 (Amazon Linux 2023): instala Docker, clona el repo, construye la imagen y levanta app + Caddy.
# desplegar.sh reemplaza __ADMIN_PASSWORD__, __SESSION_SECRET__, __ENCRYPTION_KEY__ y __APAGAR_EN__.
set -euxo pipefail
dnf install -y docker git
systemctl enable --now docker
mkdir -p /usr/local/lib/docker/cli-plugins
curl -fsSL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-$(uname -m)" \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
if [ ! -f /swapfile ]; then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
TOKEN=$(curl -fsS -X PUT http://169.254.169.254/latest/api/token -H "X-aws-ec2-metadata-token-ttl-seconds: 300")
IP=$(curl -fsS -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/public-ipv4)
git clone --depth 1 https://github.com/Mateoutec/Proyecto-final-de-IC.git /opt/asistencia
cd /opt/asistencia
docker build -t asistencia:latest .
cd deploy/nube
echo "DOMINIO=${IP//./-}.sslip.io" > .env
cat > app.env <<ENV
ADMIN_PASSWORD=__ADMIN_PASSWORD__
SESSION_SECRET=__SESSION_SECRET__
ENCRYPTION_KEY=__ENCRYPTION_KEY__
TIMEZONE=America/Lima
FACE_ENGINE=insightface
LIVENESS_ENABLED=true
FINGERPRINT_PROVIDER=disabled
ENV
chmod 600 app.env
mkdir -p data
docker compose up -d
# Apagado programado: la instancia se termina sola (InstanceInitiatedShutdownBehavior=terminate)
cat > /etc/systemd/system/fin-proyecto.service <<UNIT
[Unit]
Description=Apaga la instancia del proyecto
[Service]
Type=oneshot
ExecStart=/usr/sbin/shutdown -h now
UNIT
cat > /etc/systemd/system/fin-proyecto.timer <<UNIT
[Unit]
Description=Fin del despliegue del proyecto
[Timer]
OnCalendar=__APAGAR_EN__
Persistent=false
[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload && systemctl enable --now fin-proyecto.timer
touch /opt/asistencia-listo
