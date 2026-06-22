#!/bin/bash
# Setup del Agregador de Noticias DiarioInfo
# Ejecutar desde la terminal de cPanel

SCRIPTS_DIR="/home/diarioin/scripts"
mkdir -p "$SCRIPTS_DIR"
cd "$SCRIPTS_DIR"

echo "Instalando dependencias Python..."
pip3 install requests beautifulsoup4 --user --quiet

echo "Probando la API de DiarioInfo..."
python3 -c "import requests; r=requests.get('https://api2.diarioinfo.com/health',timeout=5); print('API status:',r.json())"

echo "Ejecutando agregador (primera prueba)..."
python3 "$SCRIPTS_DIR/noticias_agregador.py"

echo "Configurando cron cada 2 horas..."
(crontab -l 2>/dev/null | grep -v noticias_agregador) | crontab -
(crontab -l; echo "0 */2 * * * python3 /home/diarioin/scripts/noticias_agregador.py >> /home/diarioin/scripts/noticias.log 2>&1") | crontab -
crontab -l

echo "Setup completado!"
echo "Log: tail -f /home/diarioin/scripts/noticias.log"