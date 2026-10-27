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
#: la langue source, écrite directement dans le code). L'ordre est celui du
#: choix dans les réglages : le français et l'anglais d'abord, puis les autres
#: par ordre alphabétique de code. Ajouter une langue demande deux choses : son
#: nom ci-dessous et son catalogue dans translations/ (voir le README).
SUPPORTED_LANGUAGES: tuple[str, ...] = (
    "fr",
    "en",
    "de",
    "es",
    "ja",
    "pt",
    "ru",
    "zh",
)

#: Nom de chaque langue **dans cette langue**, tel qu'il apparaît dans les
#: réglages : on cherche « Deutsch » quand on parle allemand, pas « Allemand ».
#: Ces noms ne se traduisent donc jamais.
LANGUAGE_LABELS: dict[str, str] = {
    "fr": "Français",
    "en": "English",
    "de": "Deutsch",
    "es": "Español",
    "ja": "日本語",
    "pt": "Português",
    "ru": "Русский",
    "zh": "简体中文",
}

#: Valeur de configuration « suivre la langue du système ».
LANGUAGE_AUTO = "auto"

#: Langue affichée quand le système en demande une qui n'est pas fournie.
LANGUAGE_FALLBACK = "en"

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


def _language_of(locale_name: str) -> Optional[str]:
    """Code de langue d'une locale, s'il est fourni sous forme de catalogue.

    « pt-BR », « zh_CN » ou « de-AT » désignent la même langue que leur code
    principal : la région ne change pas les textes de l'interface.
    """
    base = locale_name.strip().lower().replace("_", "-").split("-", 1)[0]
    return base if base in SUPPORTED_LANGUAGES else None


def resolve_language(configured: str) -> str:
    """Langue effective : choix explicite, sinon langue du système.

    Une locale que l'application ne parle pas (polonais, suédois...) retombe
    sur l'anglais, qui sert de langue de repli.
    """
    value = str(configured or LANGUAGE_AUTO).strip().lower().replace("_", "-")
    if value in SUPPORTED_LANGUAGES:
        return value
    explicit = _language_of(value)
    if explicit is not None:
        return explicit
    return _language_of(QLocale.system().name()) or LANGUAGE_FALLBACK


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

