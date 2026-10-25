"""PressVisual — overlay de visualisation des frappes et des clics.

Le code est réparti par responsabilité :

* :mod:`pressvisual_app.config` — chargement, validation et persistance ;
* :mod:`pressvisual_app.i18n` — catalogues de traduction et choix de la langue ;
* :mod:`pressvisual_app.keymap` — raccourcis et libellés de touches ;
* :mod:`pressvisual_app.capture` — écoute globale via ``pynput`` ;
* :mod:`pressvisual_app.theme`, :mod:`~.widgets`, :mod:`~.appearance` — rendu ;
* :mod:`pressvisual_app.overlay` — fenêtre flottante ;
* :mod:`pressvisual_app.tray` — icône de notification et menu ;
* :mod:`pressvisual_app.cli` — ligne de commande et démarrage.

Le script ``pressvisual.py`` à la racine reste le point d'entrée.
"""

from __future__ import annotations

from .appearance import (
    AppearanceDialog,
    ColorButton,
    PreviewPanel,
    _choose_font_family,
)
from .capture import (
    DOUBLE_CLICK_WINDOW,
    MOUSE_BUTTON_NAMES,
    NUMPAD_VK_CHARS,
    InputListener,
    _classify_key,
    _is_altgr,
)
from .cli import (
    _default_config_path,
    _instance_lock_path,
    _language_argument,
    acquire_instance_lock,
    apply_arguments,
    build_arg_parser,
    main,
)
from .config import (
    APPEARANCE_COLOR_FIELDS,
    APPEARANCE_CONFIG_KEYS,
    Config,
    _as_bool,
    _color_to_text,
)
from .constants import APP_NAME
from .events import InputBridge, KeyEvent, MouseEvent
from .i18n import (
    LANGUAGE_AUTO,
    SUPPORTED_LANGUAGES,
    TRANSLATION_CONTEXT,
    _t,
    apply_language_change,
    install_translator,
    resolve_language,
    translations_directory,
)
from .icon import build_app_icon
from .keyboard import (
    AZERTY,
    LAYOUTS,
    QWERTY,
    InputView,
    KeyboardLayout,
    KeyboardView,
    Key,
    layout_for,
)
from .keymap import (
    DISPLAY_MODES,
    KEYBOARD_LAYOUTS,
    MULTI_CLICK_LABELS,
    MODIFIER_ALIASES,
    MODIFIER_KEYS,
    MODIFIER_ORDER,
    POSITION_CHOICES,
    POSITION_LABELS,
    SPECIAL_KEY_LABELS,
    describe_hotkey,
    key_label,
    modifier_label,
    parse_hotkey,
    should_use_combo,
)
from .mouse import MOUSE_BUTTONS, MOUSE_SCROLL_FLASH_MS, MouseView
from .overlay import (
    KEYBOARD_MAX_LIT,
    MAX_TEXT_LENGTH,
    SCROLL_AGGREGATE_WINDOW,
    Overlay,
)
from .theme import Palette, _blend, _config_color, _luminance, _with_alpha
from .tray import TrayController
from .widgets import Badge, KeyRow

__all__ = [
    "APP_NAME",
    "APPEARANCE_COLOR_FIELDS",
    "APPEARANCE_CONFIG_KEYS",
    "AZERTY",
    "AppearanceDialog",
    "Badge",
    "ColorButton",
    "Config",
    "DISPLAY_MODES",
    "DOUBLE_CLICK_WINDOW",
    "InputBridge",
    "InputListener",
    "InputView",
    "KEYBOARD_MAX_LIT",
    "KEYBOARD_LAYOUTS",
    "LAYOUTS",
    "Key",
    "KeyEvent",
    "KeyboardLayout",
    "KeyboardView",
    "KeyRow",
    "LANGUAGE_AUTO",
    "MAX_TEXT_LENGTH",
    "MODIFIER_ALIASES",
    "MODIFIER_KEYS",
    "MODIFIER_ORDER",
    "MOUSE_BUTTON_NAMES",
    "MOUSE_BUTTONS",
    "MOUSE_SCROLL_FLASH_MS",
    "MULTI_CLICK_LABELS",
    "MouseEvent",
    "MouseView",
    "NUMPAD_VK_CHARS",
    "Overlay",
    "POSITION_CHOICES",
    "POSITION_LABELS",
    "Palette",
    "PreviewPanel",
    "QWERTY",
    "SCROLL_AGGREGATE_WINDOW",
    "SPECIAL_KEY_LABELS",
    "SUPPORTED_LANGUAGES",
    "TRANSLATION_CONTEXT",
    "TrayController",
    "_as_bool",
    "_blend",
    "_choose_font_family",
    "_classify_key",
    "_color_to_text",
    "_config_color",
    "_default_config_path",
    "_instance_lock_path",
    "_is_altgr",
    "_language_argument",
    "_luminance",
    "_t",
    "_with_alpha",
    "acquire_instance_lock",
    "apply_arguments",
    "apply_language_change",
    "build_app_icon",
    "build_arg_parser",
    "describe_hotkey",
    "install_translator",
    "key_label",
    "layout_for",
    "main",
    "modifier_label",
    "parse_hotkey",
    "resolve_language",
    "should_use_combo",
    "translations_directory",
]
