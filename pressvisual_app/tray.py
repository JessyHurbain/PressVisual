"""Icône de notification et menu de contrôle de PressVisual."""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QObject
from PyQt6.QtGui import QAction, QActionGroup
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from .config import Config
from .constants import APP_NAME
from .i18n import _t
from .icon import build_app_icon
from .keymap import POSITION_CHOICES, POSITION_LABELS, describe_hotkey
from .overlay import Overlay

class TrayController(QObject):
    """Icône de notification et menu de contrôle de PressVisual."""

    def __init__(
        self,
        app: QApplication,
        overlay: Overlay,
        config: Config,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._overlay = overlay
        self._cfg = config

        self.tray = QSystemTrayIcon(build_app_icon(), self)
        self.tray.setToolTip(self._tooltip())
        self.menu = QMenu()

        self.act_visible = QAction("", self)
        self.act_visible.setCheckable(True)
        self.act_visible.triggered.connect(self._overlay.toggle_visible)

        self.act_click_through = QAction("", self)
        self.act_click_through.setCheckable(True)
        self.act_click_through.triggered.connect(self._overlay.toggle_click_through)

        self.act_masking = QAction("", self)
        self.act_masking.setCheckable(True)
        self.act_masking.triggered.connect(self._overlay.toggle_masking)

        self.act_quit = QAction("", self)
        self.act_quit.triggered.connect(app.quit)

        self.menu.addAction(self.act_visible)
        self.menu.addAction(self.act_click_through)
        self.menu.addAction(self.act_masking)
        self.menu.addSeparator()

        self.act_appearance = QAction("", self)
        self.act_appearance.triggered.connect(self._overlay.edit_appearance)
        self.menu.addAction(self.act_appearance)

        self.position_menu = self.menu.addMenu("")
        self.position_group = QActionGroup(self)
        self.position_group.setExclusive(True)
        self.position_actions: dict[str, QAction] = {}
        for position in POSITION_CHOICES:
            action = QAction("", self)
            action.setCheckable(True)
            action.triggered.connect(
                lambda _checked=False, chosen=position: self._overlay.set_position(
                    chosen
                )
            )
            self.position_group.addAction(action)
            self.position_menu.addAction(action)
            self.position_actions[position] = action

        self.menu.addSeparator()
        self.menu.addAction(self.act_quit)

        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._on_activated)
        self._overlay.state_changed.connect(self.sync_actions)

        self.retranslate()
        self.sync_actions()

    # ------------------------------------------------------------------
    def show(self) -> None:
        self.tray.show()

    def hide(self) -> None:
        self.tray.hide()

    def retranslate(self) -> None:
        """Applique la langue courante aux textes du menu."""
        toggle_hint = describe_hotkey(self._cfg, self._cfg.hotkey_toggle)
        click_hint = describe_hotkey(self._cfg, self._cfg.hotkey_click_through)
        mask_hint = describe_hotkey(self._cfg, self._cfg.hotkey_masking)
        quit_hint = describe_hotkey(self._cfg, self._cfg.hotkey_quit)

        self.act_visible.setText(
            _t("Afficher l'overlay")
            + ("   " + toggle_hint if toggle_hint else "")
        )
        self.act_click_through.setText(
            _t("Clics traversants")
            + ("   " + click_hint if click_hint else "")
        )
        self.act_masking.setText(
            _t("Masquer les frappes") + ("   " + mask_hint if mask_hint else "")
        )
        self.act_quit.setText(
            _t("Quitter") + ("   " + quit_hint if quit_hint else "")
        )
        self.act_appearance.setText(_t("Personnaliser l'overlay…"))
        self.position_menu.setTitle(_t("Position de l'overlay"))
        for position, action in self.position_actions.items():
            action.setText(_t(POSITION_LABELS[position]))
        self.tray.setToolTip(self._tooltip())

    def _tooltip(self) -> str:
        hints = []
        for label, spec in (
            (_t("Afficher/masquer"), self._cfg.hotkey_toggle),
            (_t("Clics traversants"), self._cfg.hotkey_click_through),
            (_t("Masquer les frappes"), self._cfg.hotkey_masking),
            (_t("Quitter"), self._cfg.hotkey_quit),
        ):
            description = describe_hotkey(self._cfg, spec)
            if description:
                hints.append(
                    _t("{label} : {shortcut}").format(
                        label=label, shortcut=description
                    )
                )
        return f"{APP_NAME}\n" + "\n".join(hints)

    def sync_actions(self) -> None:
        self.act_visible.setChecked(self._overlay.capture_enabled)
        self.act_click_through.setChecked(self._overlay.click_through)
        self.act_masking.setChecked(self._overlay.masked)
        for position, action in self.position_actions.items():
            action.setChecked(position == self._overlay.position_name)

    def _on_activated(self, reason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self._overlay.toggle_visible()

