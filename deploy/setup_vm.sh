#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# setup_vm.sh
# Prepara una VM Ubuntu limpia (pensado para el "Always Free tier" de Oracle
# Cloud) para correr el pipeline. Ejecútalo UNA VEZ, recién creada la VM:
#
#   bash deploy/setup_vm.sh
#
# Qué hace:
#   1. Instala paquetes del sistema necesarios (Python, ffmpeg, git, fuentes).
#   2. Crea el entorno virtual de Python e instala las dependencias.
#   3. Instala la fuente Poppins del proyecto en el sistema (por si algo la
#      busca fuera del venv).
#   4. Deja preparada la carpeta de logs/estado.
#   5. Instala la entrada de cron (ver crontab.example) SOLO si el usuario
#      confirma que ya ha rellenado config/.env (si no, avisa y no la instala,
#      para no arrancar el pipeline con credenciales a medias).
# ---------------------------------------------------------------------------
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

echo ">> Actualizando paquetes del sistema..."
sudo apt-get update -y
sudo apt-get install -y python3 python3-venv python3-pip ffmpeg git curl fontconfig

echo ">> Instalando la fuente Poppins (usada en los subtítulos)..."
sudo mkdir -p /usr/share/fonts/truetype/poppins
sudo cp assets/fonts/*.ttf /usr/share/fonts/truetype/poppins/
sudo fc-cache -f

echo ">> Creando entorno virtual de Python..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

mkdir -p logs state output

echo ""
echo "============================================================"
echo " Dependencias instaladas correctamente."
echo ""
if [ -f "config/.env" ]; then
    echo " Se ha detectado config/.env -> instalando tarea programada (cron)."
    CRON_CMD="cd $PROJECT_DIR && venv/bin/python src/orchestrator.py >> logs/cron.log 2>&1"
    ( crontab -l 2>/dev/null | grep -v "src/orchestrator.py" ; echo "0 */8 * * * $CRON_CMD" ) | crontab -
    echo " Cron instalado: el pipeline se ejecutará cada 8 horas."
    echo " (con 3 vídeos/día/canal, 3 ejecuciones/día reparten bien el ritmo de subida)"
else
    echo " AVISO: todavía no existe config/.env"
    echo " 1. Copia config/.env.example a config/.env"
    echo " 2. Rellena tus claves (Reddit, Pexels/Pixabay)"
    echo " 3. Autoriza YouTube: ver GUIA_CONFIGURACION.md"
    echo " 4. Vuelve a ejecutar este script para instalar la tarea programada."
fi
echo "============================================================"
