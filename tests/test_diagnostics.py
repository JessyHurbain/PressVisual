"""Messages d'erreur et journal.

Le ``.exe`` Windows et le bundle ``.app`` macOS sont construits en mode
fenêtré : PyInstaller y laisse ``sys.stdout`` et ``sys.stderr`` à ``None``.
Écrire dedans levait ``AttributeError`` et faisait mourir l'application au
moment précis où elle devait expliquer un problème.
"""

from __future__ import annotations

import sys

from pressvisual_app import diagnostics


def test_default_log_sits_in_the_user_data_directory():
    path = diagnostics.default_log_path()

    assert path.name == diagnostics.LOG_FILENAME
    assert path.parent.name == "PressVisual"
    assert path.is_absolute()


def test_log_path_can_be_forced_and_reset(tmp_path):
    forced = tmp_path / "ailleurs.log"

    diagnostics.set_log_path(forced)
    assert diagnostics.log_path() == forced

    diagnostics.set_log_path(None)
    assert diagnostics.log_path() == diagnostics.default_log_path()


def test_warn_writes_to_stderr_when_it_exists(capsys, tmp_path):
    log = tmp_path / "pressvisual.log"
    diagnostics.set_log_path(log)

    diagnostics.warn("un souci")

    assert "[PressVisual] un souci" in capsys.readouterr().err
    assert "un souci" in log.read_text(encoding="utf-8")


def test_warn_survives_a_missing_stderr_and_still_logs(monkeypatch, tmp_path):
    """Exécutable fenêtré : plus aucune sortie d'erreur, mais le journal reste."""
    log = tmp_path / "pressvisual.log"
    diagnostics.set_log_path(log)
    monkeypatch.setattr(sys, "stderr", None)

    diagnostics.warn("configuration illisible")

    assert "configuration illisible" in log.read_text(encoding="utf-8")


def test_log_lines_are_timestamped(tmp_path):
    log = tmp_path / "pressvisual.log"
    diagnostics.set_log_path(log)

    diagnostics.warn("horodatage attendu")

    line = log.read_text(encoding="utf-8").strip()
    # « 2026-10-27 18:45:01 [PressVisual] horodatage attendu »
    date, hour, rest = line.split(" ", 2)
    assert len(date.split("-")) == 3
    assert len(hour.split(":")) == 3
    assert rest == "[PressVisual] horodatage attendu"


def test_log_is_rotated_instead_of_growing_without_end(tmp_path):
    log = tmp_path / "pressvisual.log"
    log.write_text("x" * (diagnostics.MAX_LOG_BYTES + 1), encoding="utf-8")
    diagnostics.set_log_path(log)

    diagnostics.warn("nouveau message")

    previous = log.with_name(log.name + diagnostics.ROTATED_SUFFIX)
    assert previous.read_text(encoding="utf-8").startswith("xxx")
    assert "nouveau message" in log.read_text(encoding="utf-8")
    assert "x" not in log.read_text(encoding="utf-8")


def test_unwritable_log_never_breaks_the_application(capsys, tmp_path):
    """Un dossier de journal inaccessible laisse perdre le message, pas l'app."""
    obstacle = tmp_path / "fichier"
    obstacle.write_text("je ne suis pas un dossier", encoding="utf-8")
    diagnostics.set_log_path(obstacle / "pressvisual.log")

    diagnostics.warn("message perdu")

    assert "message perdu" in capsys.readouterr().err
    assert obstacle.read_text(encoding="utf-8") == "je ne suis pas un dossier"
