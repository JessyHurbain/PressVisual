#!/usr/bin/env bash
# Construit PressVisual.app (macOS) et l'emballe pour la distribution.
#
# Le script enchaîne cinq étapes, toutes dans build/macos/ :
#   1. environnement virtuel dédié et dépendances (PyQt6, pynput, PyInstaller) ;
#   2. compilation des traductions .ts en .qm ;
#   3. icône .icns dessinée par l'application elle-même (via iconutil) ;
#   4. empaquetage PyInstaller en bundle .app, puis signature ;
#   5. assemblage d'une image disque .dmg (ou d'une archive .zip).
#
# Le résultat est écrit dans dist/PressVisual-<version>-macos-<architecture>.dmg.
#
# Variables d'environnement facultatives :
#   PYTHON=python3.12        interpréteur utilisé pour créer l'environnement
#   VERSION=1.2.3            version inscrite dans le nom du fichier (défaut : git)
#   FORMAT=zip               archive .zip au lieu du .dmg
#   CODESIGN_ID="Developer ID Application: …"   identité de signature (sinon ad hoc)
#   SKIP_PYINSTALLER=1       réutilise le bundle existant, sans le reconstruire
#
# Utilisation :
#   bash tools/build_macos.sh
#
# Prérequis : macOS, les outils de ligne de commande Xcode (iconutil, codesign,
# hdiutil) et un accès réseau pour installer PyInstaller.
#
# Notes :
#   - le build n'est pas universel : il cible l'architecture de la machine qui
#     l'exécute (arm64 sur Apple Silicon, x86_64 sur Intel) ;
#   - PyInstaller ne produit pas de bundle .app pour une autre architecture que
#     celle de l'interpréteur utilisé, d'où un build par architecture ;
#   - un bundle non notarié déclenche Gatekeeper : voir le README.

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT_DIR"

BUILD_DIR="$ROOT_DIR/build/macos"
VENV_DIR="$BUILD_DIR/venv"
APP_NAME="PressVisual"
PYINSTALLER_DIR="$BUILD_DIR/pyinstaller"
# Le bundle est écrit sous le --distpath passé à PyInstaller, pas dans
# build/macos/dist : c'est pyinstaller/dist que le script interroge ensuite.
APP_BUNDLE="$PYINSTALLER_DIR/dist/$APP_NAME.app"
DIST_DIR="$ROOT_DIR/dist"
ICONSET_DIR="$BUILD_DIR/$APP_NAME.iconset"
ICON_PATH="$BUILD_DIR/$APP_NAME.icns"
BUNDLE_ID="com.pressvisual.pressvisual"

PYTHON=${PYTHON:-python3}
FORMAT=${FORMAT:-dmg}

die() {
    printf '[macOS] erreur : %s\n' "$1" >&2
    exit 1
}

log() {
    printf '[macOS] %s\n' "$1"
}

# ---------------------------------------------------------------------------
# Vérifications préalables
# ---------------------------------------------------------------------------

[[ $(uname -s) == Darwin ]] || die "ce script ne fonctionne que sous macOS."

case $(uname -m) in
    arm64) ARCH=arm64 ;;
    x86_64) ARCH=x86_64 ;;
    *) die "architecture non prise en charge : $(uname -m) (arm64 ou x86_64)." ;;
esac

command -v "$PYTHON" >/dev/null 2>&1 \
    || die "$PYTHON introuvable ; définissez PYTHON=/chemin/vers/python3."

# iconutil, codesign et hdiutil font partie des outils Xcode.
for tool in iconutil codesign; do
    command -v "$tool" >/dev/null 2>&1 \
        || die "$tool introuvable ; installez les outils de ligne de commande Xcode (xcode-select --install)."
done
if [[ $FORMAT == dmg ]]; then
    command -v hdiutil >/dev/null 2>&1 || die "hdiutil introuvable."
fi

if [[ -z ${VERSION:-} ]]; then
    VERSION=$(git describe --tags --always --dirty 2>/dev/null || echo "0.0.0")
    VERSION=${VERSION#v}
fi

# CFBundleShortVersionString n'accepte que des nombres séparés par des points :
# un « 0.1.0-5-gabc1234 » issu de git describe est réduit à « 0.1.0 ».
PLIST_VERSION=$(printf '%s' "$VERSION" | grep -oE '^[0-9]+(\.[0-9]+)*' || true)
PLIST_VERSION=${PLIST_VERSION:-0.0.0}

log "PressVisual $VERSION ($ARCH)"

mkdir -p "$BUILD_DIR"

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
# Icône .icns
# ---------------------------------------------------------------------------

# L'icône est dessinée par l'application elle-même : aucun binaire à stocker
# dans le dépôt, et le bundle affiche exactement l'icône de la zone de
# notification.
#
# Le module est chargé par chemin plutôt que par `import pressvisual_app` :
# importer le paquet tire capture.py, donc pynput, et ses gestionnaires de
# périphériques, ce dont le dessin d'une icône n'a pas besoin.
log "génération de l'icône .icns"
rm -rf "$ICONSET_DIR"
mkdir -p "$ICONSET_DIR"
QT_QPA_PLATFORM=offscreen "$VENV_PYTHON" - \
    "$ROOT_DIR/pressvisual_app/icon.py" "$ICONSET_DIR" <<'PY' \
    || die "génération de l'icône impossible."
import importlib.util
import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication

spec = importlib.util.spec_from_file_location("_pressvisual_icon", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

app = QApplication([])  # requis pour dessiner avec QPainter
target = Path(sys.argv[2])

# Noms attendus par iconutil : icon_16x16.png, icon_16x16@2x.png, etc.
for base in (16, 32, 128, 256, 512):
    for scale in (1, 2):
        suffix = "@2x" if scale == 2 else ""
        name = f"icon_{base}x{base}{suffix}.png"
        if not module._icon_pixmap(base * scale).save(str(target / name), "PNG"):
            raise SystemExit(f"impossible d'enregistrer {name}")
PY
iconutil -c icns "$ICONSET_DIR" -o "$ICON_PATH" \
    || die "iconutil n'a pas pu fabriquer l'icône .icns."

# ---------------------------------------------------------------------------
# Empaquetage PyInstaller (bundle .app)
# ---------------------------------------------------------------------------

if [[ ${SKIP_PYINSTALLER:-0} != 1 ]]; then
    log "empaquetage PyInstaller (quelques minutes la première fois)"
    # --windowed est ce qui fait produire un .app : sans lui, PyInstaller ne
    # livre qu'un exécutable Unix, sans Info.plist ni icône dans le Dock.
    "$VENV_PYTHON" -m PyInstaller \
        --noconfirm \
        --clean \
        --windowed \
        --onedir \
        --name "$APP_NAME" \
        --osx-bundle-identifier "$BUNDLE_ID" \
        --icon "$ICON_PATH" \
        --distpath "$PYINSTALLER_DIR/dist" \
        --workpath "$PYINSTALLER_DIR/work" \
        --specpath "$PYINSTALLER_DIR" \
        --add-data "$ROOT_DIR/translations:translations" \
        --hidden-import pynput.keyboard._darwin \
        --hidden-import pynput.mouse._darwin \
        pressvisual.py >"$BUILD_DIR/pyinstaller.log" 2>&1 \
        || {
            tail -n 40 "$BUILD_DIR/pyinstaller.log" >&2
            die "PyInstaller a échoué (journal : $BUILD_DIR/pyinstaller.log)."
        }
fi

[[ -d $APP_BUNDLE ]] \
    || die "bundle introuvable dans $APP_BUNDLE (relancez sans SKIP_PYINSTALLER)."

# ---------------------------------------------------------------------------
# Info.plist et signature
# ---------------------------------------------------------------------------

PLIST="$APP_BUNDLE/Contents/Info.plist"

# PlistBuddy refuse « Set » sur une clé absente, et la présence de chaque clé
# dépend de la version de PyInstaller : on bascule sur « Add » dans ce cas.
set_plist_key() {
    /usr/libexec/PlistBuddy -c "Set :$1 $2" "$PLIST" 2>/dev/null \
        || /usr/libexec/PlistBuddy -c "Add :$1 string $2" "$PLIST" >/dev/null \
        || die "impossible de renseigner $1 dans Info.plist."
}

# PyInstaller laisse la version à 0.0.0 : la fiche « Lire les informations » du
# Finder afficherait cette valeur au lieu de celle du tag construit.
set_plist_key CFBundleShortVersionString "$PLIST_VERSION"
set_plist_key CFBundleVersion "$PLIST_VERSION"
set_plist_key NSHumanReadableCopyright "Copyright © 2026 Jessy Hurbain, licence MIT"

# Modifier Info.plist invalide la signature posée par PyInstaller : il faut
# resigner. Sans signature valide, un bundle est refusé au lancement sur Apple
# Silicon, d'où la signature ad hoc par défaut.
if [[ -n ${CODESIGN_ID:-} ]]; then
    log "signature avec l'identité « $CODESIGN_ID »"
    codesign --force --deep --timestamp --options runtime \
        --sign "$CODESIGN_ID" "$APP_BUNDLE" \
        || die "la signature a échoué (identité « $CODESIGN_ID »)."
else
    log "signature ad hoc (CODESIGN_ID non défini)"
    codesign --force --deep --sign - "$APP_BUNDLE" \
        || die "la signature ad hoc a échoué."
fi
codesign --verify --deep --strict "$APP_BUNDLE" \
    || die "la signature du bundle n'est pas valide."

# ---------------------------------------------------------------------------
# Livraison
# ---------------------------------------------------------------------------

mkdir -p "$DIST_DIR"

if [[ $FORMAT == zip ]]; then
    OUTPUT="$DIST_DIR/$APP_NAME-$VERSION-macos-$ARCH.zip"
    rm -f "$OUTPUT"
    log "compression du bundle"
    # ditto conserve les liens symboliques, les permissions et la signature,
    # ce que `zip` ne garantit pas.
    ditto -c -k --sequesterRsrc --keepParent "$APP_BUNDLE" "$OUTPUT" \
        || die "la compression a échoué."
else
    [[ $FORMAT == dmg ]] || die "FORMAT inconnu : $FORMAT (dmg ou zip)."
    OUTPUT="$DIST_DIR/$APP_NAME-$VERSION-macos-$ARCH.dmg"
    STAGE_DIR="$BUILD_DIR/dmg"
    log "assemblage de l'image disque"
    rm -rf "$STAGE_DIR" "$OUTPUT"
    mkdir -p "$STAGE_DIR"
    ditto "$APP_BUNDLE" "$STAGE_DIR/$APP_NAME.app" \
        || die "copie du bundle impossible."
    # Le lien vers /Applications permet de glisser l'application à l'endroit
    # habituel depuis la fenêtre du .dmg.
    ln -s /Applications "$STAGE_DIR/Applications"
    hdiutil create \
        -volname "$APP_NAME $VERSION" \
        -srcfolder "$STAGE_DIR" \
        -ov -format UDZO \
        "$OUTPUT" >/dev/null \
        || die "hdiutil n'a pas pu créer l'image disque."
fi

log "terminé : $OUTPUT ($(du -h "$OUTPUT" | cut -f1))"
log "installez l'application par glisser-déposer dans /Applications."
log "au premier lancement, autorisez PressVisual dans Réglages Système →"
log "Confidentialité et sécurité → Accessibilité, sinon le clavier est muet."
