"""Ligne de commande et démarrage de l'application."""

from __future__ import annotations

import argparse
import contextlib
import os
import signal
import sys
import tempfile
from pathlib import Path
from typing import Iterable, Optional

from PyQt6.QtCore import QLockFile, QStandardPaths, QTimer
from PyQt6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from .capture import InputListener
from .config import Config
from .constants import APP_NAME
from .events import InputBridge
from .i18n import (
    LANGUAGE_AUTO,
    SUPPORTED_LANGUAGES,
    _t,
    apply_language_change,
    install_translator,
    resolve_language,
)
from .icon import build_app_icon
from .keymap import POSITION_CHOICES, parse_hotkey
from .overlay import Overlay
from .tray import TrayController

# ---------------------------------------------------------------------------
# Ligne de commande
# ---------------------------------------------------------------------------


def _macos_config_path() -> Path:
    """Configuration d'un bundle .app : dossier utilisateur « Application Support ».

    Écrire à côté du ``.app`` ne conviendrait pas : déplacé dans
    ``/Applications``, un bundle n'est pas inscriptible, et une application
    lancée par le Finder n'a pas de console pour signaler l'échec. Les réglages
    disparaîtraient donc en silence d'un lancement à l'autre.
    """
    directory = Path.home() / "Library" / "Application Support" / APP_NAME
    # L'enregistrement d'un réglage ne crée pas les parents du fichier : le
    # dossier est préparé ici, au premier lancement. Un refus (droits, disque)
    # sera de toute façon signalé à la première écriture.
    with contextlib.suppress(OSError):
        directory.mkdir(parents=True, exist_ok=True)
    return directory / "config.json"


def _default_config_path() -> Path:
    """``config.json`` à côté du script ou de l'exécutable PyInstaller."""
    if getattr(sys, "frozen", False):
        executable = Path(sys.executable).resolve()
        # macOS : PressVisual.app/Contents/MacOS/PressVisual
        if sys.platform == "darwin" and executable.parent.name == "MacOS":
            return _macos_config_path()
        return executable.parent / "config.json"
    return Path(__file__).resolve().parents[1] / "config.json"


def _language_argument(arguments: Iterable[str]) -> str:
    """Lit ``--lang`` sans construire le parseur (pour traduire l'aide)."""
    options = list(arguments)
    for index, argument in enumerate(options):
        if argument == "--lang" and index + 1 < len(options):
            return options[index + 1]
        if argument.startswith("--lang="):
            return argument.split("=", 1)[1]
    return LANGUAGE_AUTO


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pressvisual",
        description=_t(
            "Overlay de visualisation des frappes clavier et des clics souris, "
            "pour les captures d'écran et tutoriels."
        ),
    )
    parser.add_argument(
        "--config",
        metavar=_t("FICHIER"),
        help=_t("fichier JSON de configuration"),
    )
    parser.add_argument(
        "--lang",
        choices=(LANGUAGE_AUTO, *SUPPORTED_LANGUAGES),
        help=_t("langue de l'interface : auto (système), fr ou en"),
    )
    parser.add_argument(
        "--duration",
        type=float,
        help=_t("durée affichée après la dernière entrée (s)"),
    )
    parser.add_argument(
        "--opacity", type=float, help=_t("opacité du fond (0.15 - 1.0)")
    )
    parser.add_argument("--font-size", type=int, help=_t("taille de police (pt)"))
    parser.add_argument(
        "--max-rows", type=int, help=_t("nombre de lignes conservées")
    )
    parser.add_argument(
        "--max-width", type=int, help=_t("largeur maximale du contenu (px)")
    )
    parser.add_argument(
        "--margin", type=int, help=_t("marge avec le bord de l'écran (px)")
    )
    parser.add_argument(
        "--position",
        choices=POSITION_CHOICES,
        help=_t(
            "position initiale : top-left, top-right, bottom-left, bottom-right "
            "ou bottom-center"
        ),
    )
    parser.add_argument(
        "--no-keyboard",
        action="store_true",
        help=_t("ne pas afficher les frappes (les raccourcis globaux restent actifs)"),
    )
    parser.add_argument(
        "--no-mouse",
        action="store_true",
        help=_t("ne pas capturer la souris"),
    )
    parser.add_argument(
        "--group-text",
        action="store_true",
        help=_t(
            "regrouper les caractères saisis en texte continu au lieu d'une "
            "touche par ligne"
        ),
    )
    parser.add_argument(
        "--start-hidden",
        action="store_true",
        help=_t("démarrer sans capture (Ctrl+F12 pour l'activer)"),
    )
    parser.add_argument(
        "--click-through",
        action="store_true",
        help=_t("démarrer en mode clics traversants"),
    )
    parser.add_argument(
        "--toggle-hotkey",
        metavar=_t("RACCOURCI"),
        help=_t(
            "raccourci afficher/masquer (ex. ctrl+f12, chaîne vide pour désactiver)"
        ),
    )
    return parser


def apply_arguments(config: Config, args: argparse.Namespace) -> None:
    """Applique les options de la ligne de commande à la configuration.

    Les options explicites l'emportent sur le fichier ; en particulier
    ``--position`` remplace une position libre mémorisée par un glisser.
    """
    if args.duration is not None:
        config.display_duration = args.duration
    if args.opacity is not None:
        config.opacity = args.opacity
    if args.font_size is not None:
        config.font_size = args.font_size
    if args.max_rows is not None:
        config.max_rows = args.max_rows
    if args.max_width is not None:
        config.max_width = args.max_width
    if args.margin is not None:
        config.margin = args.margin
    if args.position is not None:
        config.position = args.position
        config.free_position = None
    if args.no_keyboard:
        config.capture_keyboard = False
    if args.no_mouse:
        config.capture_mouse = False
    if args.group_text:
        config.concat_text = True
    if args.start_hidden:
        config.start_hidden = True
    if args.click_through:
        config.click_through_on_start = True
    if args.toggle_hotkey is not None:
        config.hotkey_toggle = args.toggle_hotkey
    if args.lang is not None:
        config.language = args.lang


def _instance_lock_path() -> Path:
    """Fichier de verrou empêchant deux instances de capturer le clavier."""
    base = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.TempLocation
    )
    directory = Path(base) if base else Path(tempfile.gettempdir())
    user = os.getuid() if hasattr(os, "getuid") else os.environ.get("USERNAME", "user")
    return directory / f"pressvisual-{user}.lock"


def acquire_instance_lock() -> Optional[QLockFile]:
    """Prend le verrou mono-instance, ou renvoie ``None`` s'il est déjà pris.

    Deux instances écouteraient le même clavier et afficheraient deux fois
    chaque frappe : le verrou n'admet qu'un seul PressVisual par utilisateur.
    Un verrou laissé par un processus disparu est récupéré par Qt.
    """
    lock = QLockFile(str(_instance_lock_path()))
    return lock if lock.tryLock(0) else None


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)

    existing = QApplication.instance()
    app = (
        existing
        if isinstance(existing, QApplication)
        else QApplication(sys.argv[:1])
    )
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(build_app_icon())

    # La langue est choisie avant de construire le parseur : l'aide de
    # --help s'affiche ainsi dans la langue demandée (--lang ou système).
    language = resolve_language(_language_argument(arguments))
    translator = install_translator(app, language)

    parser = build_arg_parser()
    args = parser.parse_args(arguments)

    def warn(message: str) -> None:
        sys.stderr.write(f"[{APP_NAME}] {message}\n")

    # Une seule instance peut écouter le clavier à la fois.
    instance_lock = acquire_instance_lock()
    if instance_lock is None:
        message = _t(
            "PressVisual est déjà lancé : une seule instance peut capturer "
            "le clavier."
        )
        if sys.stderr is not None:
            warn(message)
        else:
            # Exécutable sans console : le message doit rester visible.
            QMessageBox.information(None, APP_NAME, message)
        return 1

    config_path = (
        Path(args.config).expanduser().resolve()
        if args.config
        else _default_config_path()
    )
    config = Config.load(config_path, warn)

    apply_arguments(config, args)

    # Le fichier de configuration peut imposer une autre langue que --lang.
    wanted = resolve_language(config.language)
    if wanted != language:
        translator = install_translator(app, wanted, translator)
        language = wanted

    for note in config.validate():
        warn(note)

    if not config.capture_keyboard and not config.capture_mouse:
        warn(_t("Clavier et souris sont désactivés : l'overlay ne montrera rien."))

    overlay = Overlay(config)

    bridge = InputBridge()
    hotkeys: dict[tuple[frozenset[str], str], str] = {}
    for action, spec in (
        ("toggle", config.hotkey_toggle),
        ("click_through", config.hotkey_click_through),
        ("masking", config.hotkey_masking),
        ("quit", config.hotkey_quit),
    ):
        parsed = parse_hotkey(spec)
        if parsed is None:
            if spec:
                warn(
                    _t("Raccourci global invalide ignoré : {spec}").format(
                        spec=repr(spec)
                    )
                )
            continue
        hotkeys[parsed] = action

    listener = InputListener(bridge, config, hotkeys)

    def dispatch_hotkey(action: str) -> None:
        if action == "quit":
            app.quit()
            return
        overlay.cancel_live_combo()
        if action == "toggle":
            overlay.toggle_visible()
        elif action == "click_through":
            overlay.toggle_click_through()
        elif action == "masking":
            overlay.toggle_masking()

    bridge.key_event.connect(overlay._on_key)
    bridge.key_release.connect(overlay._on_key_release)
    bridge.mouse_event.connect(overlay._on_mouse)
    bridge.mouse_release.connect(overlay._on_mouse_release)
    bridge.modifiers_changed.connect(overlay._on_modifiers)
    bridge.modifier_sides_changed.connect(overlay._on_modifier_sides)
    bridge.hotkey.connect(dispatch_hotkey)

    def show_error(message: str) -> None:
        warn(message)
        QMessageBox.critical(
            None, f"{APP_NAME} — {_t('erreur de capture')}", message
        )

    bridge.error.connect(show_error)

    tray = TrayController(app, overlay, config)

    def change_language(chosen: str) -> None:
        """Applique le choix de langue de la fenêtre d'apparence."""
        nonlocal translator
        translator = apply_language_change(app, tray, translator, chosen)

    overlay.language_changed.connect(change_language)

    if QSystemTrayIcon.isSystemTrayAvailable():
        tray.show()
    else:
        warn(
            _t(
                "Aucune zone de notification disponible : utilisez les raccourcis "
                "globaux ou Ctrl+C dans le terminal pour quitter."
            )
        )

    def shutdown() -> None:
        listener.stop()
        tray.hide()

    app.aboutToQuit.connect(shutdown)

    # Permet à Ctrl+C (terminal) de fermer proprement l'application.
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    keep_alive = QTimer()
    keep_alive.start(250)
    keep_alive.timeout.connect(lambda: None)

    listener.start()

    try:
        return app.exec()
    finally:
        listener.stop()

