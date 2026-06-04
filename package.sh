#!/bin/bash
# Zabalí plugin.video.moravec do ZIP souboru pro instalaci na Kodi
# Použití: ./package.sh

set -e

ADDON_DIR="plugin.video.moravec"
OUTPUT="plugin.video.moravec.zip"

if [ -f "$OUTPUT" ]; then
    rm "$OUTPUT"
fi

# ZIP musí obsahovat adresář plugin.video.moravec/ uvnitř
zip -r "$OUTPUT" "$ADDON_DIR" \
    --exclude "*.pyc" \
    --exclude "*/__pycache__/*" \
    --exclude "*/.DS_Store"

echo "Vytvořeno: $OUTPUT"
echo ""
echo "Instalace na Kodi:"
echo "  1. Zkopíruj $OUTPUT na RPi5 (např. přes SSH nebo USB)"
echo "  2. Kodi → Add-ons → ikona balíčku → Install from ZIP file"
echo "  3. Nastav e-mail + heslo v nastavení addonu"
echo ""
echo "Nebo přímo přes SSH na LibreELEC:"
echo "  scp -r $ADDON_DIR root@<IP_RPi5>:/storage/.kodi/addons/"
echo "  # Poté v Kodi: Settings → Add-ons → My add-ons → aktivovat"
