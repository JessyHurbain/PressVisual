"""Traductions de l'interface : catalogues ``.qm`` et choix de la langue."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from PyQt6.QtCore import QCoreApplication, QLocale, QTranslator
from PyQt6.QtWidgets import QApplication

from . import diagnostics

if TYPE_CHECKING:
    from .tray import TrayController

#: Langues pour lesquelles un catalogue ``.qm`` est fourni (le français est
#: la langue source, écrite directement dans le code).
SUPPORTED_LANGUAGES: tuple[str, ...] = ("fr", "en")

#: Valeur de configuration « suivre la langue du système ».
LANGUAGE_AUTO = "auto"

#: Contexte utilisé par toutes les chaînes traduisibles.
TRANSLATION_CONTEXT = "PressVisual"

# ---------------------------------------------------------------------------
# Traductions
# ---------------------------------------------------------------------------


def _t(text: str) -> str:
    """Traduit un texte d'interface (la source est en français)."""
    return QCoreApplication.translate(TRANSLATION_CONTEXT, text)


def translations_directory() -> Path:
    """Dossier des catalogues ``.qm`` (compatible PyInstaller)."""
    bundle = getattr(sys, "_MEIPASS", None)
    if getattr(sys, "frozen", False) and bundle:
        candidate = Path(bundle) / "translations"
        if candidate.is_dir():
            return candidate
    return Path(__file__).resolve().parents[1] / "translations"


def resolve_language(configured: str) -> str:
    """Langue effective : choix explicite, sinon langue du système.

    Une locale inconnue (allemand, espagnol...) retombe sur l'anglais, qui
    sert de langue de repli aux côtés du français.
    """
    value = str(configured or LANGUAGE_AUTO).strip().lower().replace("_", "-")
    if value in SUPPORTED_LANGUAGES:
        return value
    if value.startswith("fr"):
        return "fr"
    if value.startswith("en"):
        return "en"
    system = QLocale.system().name().lower()
    return "fr" if system.startswith("fr") else "en"


def install_translator(
    app: QApplication, language: str, previous: Optional[QTranslator] = None
) -> Optional[QTranslator]:
    """Installe le catalogue de ``language`` et renvoie le traducteur.

    Le français étant la langue source, aucun catalogue n'est nécessaire :
    l'application affiche alors ses chaînes telles quelles.
    """
    if previous is not None:
        app.removeTranslator(previous)
    if language == "fr":
        return None

    translator = QTranslator(app)
    path = translations_directory() / f"pressvisual_{language}.qm"
    if not translator.load(str(path)):
        diagnostics.warn(
            _t("Traduction introuvable ou illisible : {path}").format(path=path)
        )
        return None
    app.installTranslator(translator)
    return translator


def apply_language_change(
    app: QApplication,
    tray: "TrayController",
    translator: Optional[QTranslator],
    language: str,
) -> Optional[QTranslator]:
    """Installe la langue choisie et rafraîchit les textes du menu."""
    translator = install_translator(app, resolve_language(language), translator)
    tray.retranslate()
    return translator

