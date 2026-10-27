"""Messages d'erreur et journal.

Le ``.exe`` Windows et le bundle ``.app`` macOS sont construits en mode
fenêtré : PyInstaller laisse alors ``sys.stdout`` et ``sys.stderr`` à ``None``
et écrire dedans lève ``AttributeError: 'NoneType' object has no attribute
'write'``. L'application mourrait au moment précis où elle doit expliquer ce
qui ne va pas — configuration illisible, capture refusée, raccourci invalide —
et l'utilisateur d'un exécutable sans console ne verrait jamais le message
prévu pour le dépanner.

Tous les messages passent donc par :func:`warn` : la sortie d'erreur quand
elle existe, et dans tous les cas un journal que l'utilisateur peut
transmettre pour expliquer un problème.
"""

from __future__ import annotations

import contextlib
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QStandardPaths

from .constants import APP_NAME

#: Nom du fichier de journal.
LOG_FILENAME = "pressvisual.log"
#: Taille au-delà de laquelle le journal est mis de côté (256 Kio).
MAX_LOG_BYTES = 256 * 1024
#: Suffixe de la version précédente du journal.
ROTATED_SUFFIX = ".1"

#: Emplacement forcé du journal (``None`` : emplacement par défaut).
_log_path: Optional[Path] = None


def default_log_path() -> Path:
    """``pressvisual.log`` dans le dossier de données de l'utilisateur.

    ``GenericDataLocation`` suivi du nom de l'application, plutôt que
    ``AppLocalDataLocation`` : ce dernier dépend du nom déclaré dans Qt, qui
    n'est pas encore fixé quand la capture signale un problème à l'import.
    """
    base = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.GenericDataLocation
    )
    directory = Path(base) if base else Path(tempfile.gettempdir())
    return directory / APP_NAME / LOG_FILENAME


def log_path() -> Path:
    """Emplacement courant du journal."""
    return _log_path if _log_path is not None else default_log_path()


def set_log_path(path: Optional[Path]) -> None:
    """Force l'emplacement du journal (``None`` rétablit celui par défaut)."""
    global _log_path
    _log_path = Path(path) if path is not None else None


def warn(message: str) -> None:
    """Signale ``message`` : sortie d'erreur si elle existe, et journal.

    Rien ici ne doit interrompre l'application : un disque plein ou un dossier
    inaccessible se traduit par un message perdu, jamais par un plantage.
    """
    line = f"[{APP_NAME}] {message}"
    stream = sys.stderr
    if stream is not None:
        with contextlib.suppress(OSError, ValueError):
            stream.write(line + "\n")
    _append(line)


def _append(line: str) -> None:
    """Ajoute ``line`` au journal, horodatée, en mettant de côté l'ancien."""
    path = log_path()
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with contextlib.suppress(OSError, ValueError):
        path.parent.mkdir(parents=True, exist_ok=True)
        # Mise de côté plutôt que troncature : la ligne en cours d'écriture ne
        # doit jamais être coupée en deux.
        if path.exists() and path.stat().st_size > MAX_LOG_BYTES:
            path.replace(path.with_name(path.name + ROTATED_SUFFIX))
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"{stamp} {line}\n")
