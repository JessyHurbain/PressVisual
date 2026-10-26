#!/usr/bin/env bash
# Construit un AppImage autonome de PressVisual (Linux).
#
# Le script enchaîne trois étapes, toutes dans build/appimage/ :
#   1. environnement virtuel dédié et dépendances (PyQt6, pynput, PyInstaller) ;
#   2. empaquetage PyInstaller en dossier autonome (dist/PressVisual/) ;
#   3. assemblage d'un AppDir puis fabrication de l'AppImage avec appimagetool.
#
# Le résultat est écrit dans dist/PressVisual-<version>-<architecture>.AppImage.
#
# Variables d'environnement facultatives :
#   PYTHON=python3.12        interpréteur utilisé pour créer l'environnement
#   VERSION=1.2.3            version inscrite dans le nom du fichier (défaut : git)
#   APPIMAGETOOL=/chemin     outil déjà téléchargé (sinon il est récupéré)
#   SKIP_PYINSTALLER=1       réutilise l'empaquetage existant, sans le refaire
#
# Utilisation :
#   bash tools/build_appimage.sh
#
# Prérequis : Linux, python3 avec le module venv, et un accès réseau pour
# télécharger PyInstaller et, la première fois, appimagetool.

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT_DIR"

BUILD_DIR="$ROOT_DIR/build/appimage"
VENV_DIR="$BUILD_DIR/venv"
APP_NAME="PressVisual"
APPDIR="$BUILD_DIR/$APP_NAME.AppDir"
PYINSTALLER_DIR="$BUILD_DIR/pyinstaller"
DIST_DIR="$ROOT_DIR/dist"

PYTHON=${PYTHON:-python3}

die() {
    printf '[AppImage] erreur : %s\n' "$1" >&2
    exit 1
}

log() {
    printf '[AppImage] %s\n' "$1"
}

# ---------------------------------------------------------------------------
# Vérifications préalables
# ---------------------------------------------------------------------------

[[ $(uname -s) == Linux ]] || die "ce script ne fonctionne que sous Linux."

case $(uname -m) in
    x86_64 | amd64) ARCH=x86_64 ;;
    aarch64 | arm64) ARCH=aarch64 ;;
    *) die "architecture non prise en charge : $(uname -m) (x86_64 ou aarch64)." ;;
esac

command -v "$PYTHON" >/dev/null 2>&1 \
    || die "$PYTHON introuvable ; définissez PYTHON=/chemin/vers/python3."

if [[ -z ${VERSION:-} ]]; then
    VERSION=$(git describe --tags --always --dirty 2>/dev/null || echo "0.0.0")
    VERSION=${VERSION#v}
fi

log "PressVisual $VERSION ($ARCH)"

# ---------------------------------------------------------------------------
# Environnement virtuel et dépendances
# ---------------------------------------------------------------------------

if [[ ! -x $VENV_DIR/bin/python ]]; then
    log "création de l'environnement virtuel dans $VENV_DIR"
    "$PYTHON" -m venv "$VENV_DIR" || die "impossible de créer l'environnement virtuel."
fi

VENV_PYTHON="$VENV_DIR/bin/python"

# L'empreinte de requirements.txt évite de réinstaller à chaque build, tout en
# réagissant si les dépendances changent.
DEPS_STAMP="$VENV_DIR/.requirements-sum"
DEPS_SUM=$(cksum <requirements.txt)
if [[ ! -f $DEPS_STAMP || $(cat "$DEPS_STAMP") != "$DEPS_SUM" ]]; then
    log "installation des dépendances (PyQt6, pynput, PyInstaller)"
    if ! {
        "$VENV_PYTHON" -m pip install --quiet --upgrade pip &&
        "$VENV_PYTHON" -m pip install --quiet -r requirements.txt pyinstaller
    } >>"$BUILD_DIR/pip.log" 2>&1; then
        tail -n 20 "$BUILD_DIR/pip.log" >&2
        die "installation des dépendances impossible (journal : $BUILD_DIR/pip.log)."
    fi
    printf '%s' "$DEPS_SUM" >"$DEPS_STAMP"
fi

# Les catalogues .qm sont générés depuis les .ts, sans dépendre de lrelease.
log "compilation des traductions"
"$VENV_PYTHON" tools/compile_translations.py >/dev/null

# ---------------------------------------------------------------------------
# Empaquetage PyInstaller (dossier autonome)
# ---------------------------------------------------------------------------

if [[ ${SKIP_PYINSTALLER:-0} != 1 ]]; then
    log "empaquetage PyInstaller (quelques minutes la première fois)"
    "$VENV_PYTHON" -m PyInstaller \
        --noconfirm \
        --clean \
        --onedir \
        --name "$APP_NAME" \
        --distpath "$PYINSTALLER_DIR/dist" \
        --workpath "$PYINSTALLER_DIR/work" \
        --specpath "$PYINSTALLER_DIR" \
        --add-data "$ROOT_DIR/translations:translations" \
        --hidden-import pynput.keyboard._xorg \
        --hidden-import pynput.mouse._xorg \
        --hidden-import Xlib \
        pressvisual.py >"$BUILD_DIR/pyinstaller.log" 2>&1 \
        || {
            tail -n 40 "$BUILD_DIR/pyinstaller.log" >&2
            die "PyInstaller a échoué (journal : $BUILD_DIR/pyinstaller.log)."
        }
fi

BUNDLE_DIR="$PYINSTALLER_DIR/dist/$APP_NAME"
[[ -x $BUNDLE_DIR/$APP_NAME ]] \
    || die "empaquetage introuvable dans $BUNDLE_DIR (relancez sans SKIP_PYINSTALLER)."

# ---------------------------------------------------------------------------
# AppDir
# ---------------------------------------------------------------------------

log "assemblage de l'AppDir"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" \
    "$APPDIR/usr/share/applications" \
    "$APPDIR/usr/share/icons/hicolor/512x512/apps"

cp -a "$BUNDLE_DIR" "$APPDIR/usr/bin/$APP_NAME"

# L'icône est dessinée par l'application elle-même : pas de binaire à stocker
# dans le dépôt, et l'AppImage affiche exactement l'icône de la zone de
# notification.
#
# Le module est chargé par chemin plutôt que par `import pressvisual_app` :
# importer le paquet tire capture.py, donc pynput, qui exige une connexion X11.
# Un build sans écran (serveur, conteneur, CI) n'en a pourtant pas besoin.
log "génération de l'icône 512×512"
QT_QPA_PLATFORM=offscreen "$VENV_PYTHON" - \
    "$ROOT_DIR/pressvisual_app/icon.py" "$APPDIR/pressvisual.png" <<'PY' \
    || die "génération de l'icône impossible."
import importlib.util
import sys

from PyQt6.QtWidgets import QApplication

spec = importlib.util.spec_from_file_location("_pressvisual_icon", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

app = QApplication([])  # requis pour dessiner avec QPainter
pixmap = module._icon_pixmap(512)
if not pixmap.save(sys.argv[2], "PNG"):
    raise SystemExit("impossible d'enregistrer l'icône")
PY

cp "$APPDIR/pressvisual.png" "$APPDIR/usr/share/icons/hicolor/512x512/apps/pressvisual.png"
cp "$APPDIR/pressvisual.png" "$APPDIR/.DirIcon"

cat >"$APPDIR/pressvisual.desktop" <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=PressVisual
GenericName=Key and mouse overlay
Comment=Affiche les frappes clavier et les clics souris pour les captures d'écran
Comment[en]=Shows keyboard presses and mouse clicks for screenshots
Exec=PressVisual
Icon=pressvisual
Terminal=false
Categories=Utility;Education;
Keywords=keyboard;mouse;overlay;screencast;tutorial;clavier;souris;
StartupWMClass=PressVisual
DESKTOP
cp "$APPDIR/pressvisual.desktop" "$APPDIR/usr/share/applications/pressvisual.desktop"

# L'AppImage est montée en lecture seule : sans --config, la configuration
# serait cherchée à côté de l'exécutable, donc dans le point de montage. On la
# place dans le dossier XDG de l'utilisateur pour que la position et les
# réglages soient conservés d'un lancement à l'autre.
cat >"$APPDIR/AppRun" <<'APPRUN'
#!/bin/bash
set -e

HERE=$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/pressvisual"
mkdir -p "$CONFIG_DIR"

exec "$HERE/usr/bin/PressVisual/PressVisual" \
    --config "$CONFIG_DIR/config.json" "$@"
APPRUN
chmod +x "$APPDIR/AppRun"

# ---------------------------------------------------------------------------
# AppImage
# ---------------------------------------------------------------------------

TOOL=${APPIMAGETOOL:-"$BUILD_DIR/appimagetool-$ARCH.AppImage"}
if [[ ! -x $TOOL ]]; then
    log "téléchargement d'appimagetool ($ARCH)"
    mkdir -p "$BUILD_DIR"
    URL="https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-$ARCH.AppImage"
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL --retry 3 -o "$TOOL" "$URL" || die "téléchargement d'appimagetool impossible."
    elif command -v wget >/dev/null 2>&1; then
        wget -q -O "$TOOL" "$URL" || die "téléchargement d'appimagetool impossible."
    else
        die "curl ou wget est nécessaire pour récupérer appimagetool."
    fi
    chmod +x "$TOOL"
fi

mkdir -p "$DIST_DIR"
OUTPUT="$DIST_DIR/$APP_NAME-$VERSION-$ARCH.AppImage"
rm -f "$OUTPUT"

log "fabrication de l'AppImage"
# --appimage-extract-and-run évite d'exiger FUSE sur la machine de build.
ARCH="$ARCH" VERSION="$VERSION" "$TOOL" --appimage-extract-and-run \
    --no-appstream "$APPDIR" "$OUTPUT" \
    || die "appimagetool a échoué."

chmod +x "$OUTPUT"

log "terminé : $OUTPUT ($(du -h "$OUTPUT" | cut -f1))"
log "lancement : $OUTPUT"
