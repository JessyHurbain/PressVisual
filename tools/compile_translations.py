#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compile les fichiers ``.ts`` en ``.qm`` lisibles par ``QTranslator``.

PyQt6 ne fournit pas ``lrelease`` ; ce script écrit donc directement le
format binaire de Qt (magic de 16 octets, blocs *Messages* et *Hashes*),
en suivant ``qttools/src/linguist/shared/qm.cpp``. Il couvre les traductions
simples, sans formes plurielles.

Utilisation :
    python tools/compile_translations.py            # compile tous les .ts
    python tools/compile_translations.py --check    # vérifie que les .qm sont à jour
    python tools/compile_translations.py --verify   # recharge les .qm avec Qt
"""

from __future__ import annotations

import argparse
import struct
import sys
import xml.etree.ElementTree as ElementTree
from pathlib import Path
from typing import Iterable, Optional

TRANSLATIONS_DIR = Path(__file__).resolve().parents[1] / "translations"

#: En-tête des fichiers .qm (16 octets, identique à lrelease).
QM_MAGIC = bytes(
    (
        0x3C,
        0xB8,
        0x64,
        0x18,
        0xCA,
        0xEF,
        0x9C,
        0x95,
        0xCD,
        0x21,
        0x1C,
        0xBF,
        0x60,
        0xA1,
        0xBD,
        0xDD,
    )
)

#: Sections du fichier (octet d'identification).
QM_TAG_CONTEXTS = 0x2F
QM_TAG_HASHES = 0x42
QM_TAG_MESSAGES = 0x69
QM_TAG_LANGUAGE = 0xA7

#: Sous-sections d'un message.
QM_TAG_END = 1
QM_TAG_TRANSLATION = 3
QM_TAG_SOURCE = 6
QM_TAG_CONTEXT = 7


class TranslationError(RuntimeError):
    """Fichier ``.ts`` illisible ou incohérent."""


def _uint32(value: int) -> bytes:
    return struct.pack(">I", value)


def _block(tag: int, payload: bytes) -> bytes:
    return bytes([tag]) + _uint32(len(payload)) + payload


def _text_block(tag: int, text: str) -> bytes:
    data = text.encode("utf-8")
    return bytes([tag]) + _uint32(len(data)) + data


def elf_hash(data: bytes) -> int:
    """Hash utilisé par Qt pour indexer les messages (algorithme ELF)."""
    value = 0
    for byte in data:
        value = ((value << 4) + byte) & 0xFFFFFFFF
        high = value & 0xF0000000
        if high:
            value ^= high >> 24
        value &= ~high & 0xFFFFFFFF
    return value or 1


def parse_ts(path: Path) -> tuple[str, list[tuple[str, str, str]]]:
    """Renvoie ``(langue, [(contexte, source, traduction), ...])``."""
    try:
        root = ElementTree.parse(path).getroot()
    except (OSError, ElementTree.ParseError) as exc:
        raise TranslationError(f"{path} : {exc}") from exc

    language = root.get("language", "")
    messages: list[tuple[str, str, str]] = []
    for context_element in root.iter("context"):
        name_element = context_element.find("name")
        context = (name_element.text or "").strip() if name_element is not None else ""
        if not context:
            raise TranslationError(f"{path} : contexte sans nom")
        for message in context_element.iter("message"):
            source_element = message.find("source")
            translation_element = message.find("translation")
            source = source_element.text if source_element is not None else None
            translation = (
                translation_element.text if translation_element is not None else None
            )
            if translation_element is not None and translation_element.get(
                "type"
            ) in ("unfinished", "obsolete"):
                translation = None
            if not source:
                raise TranslationError(f"{path} : message sans source")
            if translation:
                messages.append((context, source, translation))
    if not language:
        raise TranslationError(f"{path} : attribut « language » manquant")
    return language, messages


def _message_record(source: str, translation: str, context: str) -> bytes:
    payload = translation.encode("utf-16-be")
    parts = [
        bytes([QM_TAG_TRANSLATION])
        + struct.pack(">i", len(payload) if payload else -1)
        + payload,
        _text_block(QM_TAG_SOURCE, source),
        _text_block(QM_TAG_CONTEXT, context),
        bytes([QM_TAG_END]),
    ]
    return b"".join(parts)


def build_qm(
    messages: Iterable[tuple[str, str, str]], language: str = ""
) -> bytes:
    """Assemble un fichier .qm à partir des messages traduits."""
    unique: dict[tuple[str, str], str] = {}
    for context, source, translation in messages:
        unique[(context, source)] = translation

    records = b""
    hashes: list[tuple[int, int]] = []
    for (context, source), translation in sorted(unique.items()):
        offset = len(records)
        records += _message_record(source, translation, context)
        hashes.append((elf_hash(source.encode("utf-8")), offset))

    hashes.sort()
    hash_payload = b"".join(
        struct.pack(">II", value, offset) for value, offset in hashes
    )

    data = QM_MAGIC
    if language:
        data += _block(QM_TAG_LANGUAGE, language.encode("utf-8"))
    data += _block(QM_TAG_MESSAGES, records)
    data += _block(QM_TAG_HASHES, hash_payload)
    return data


def compile_ts_file(path: Path) -> bytes:
    """Contenu ``.qm`` correspondant au fichier ``.ts``."""
    language, messages = parse_ts(path)
    return build_qm(messages, language)


def ts_files(directory: Path = TRANSLATIONS_DIR) -> list[Path]:
    return sorted(directory.glob("*.ts"))


def write_qm(ts_path: Path) -> Path:
    qm_path = ts_path.with_suffix(".qm")
    qm_path.write_bytes(compile_ts_file(ts_path))
    return qm_path


def check(directory: Path = TRANSLATIONS_DIR) -> list[str]:
    """Liste des ``.qm`` absents ou différents du ``.ts``."""
    problems: list[str] = []
    for ts_path in ts_files(directory):
        qm_path = ts_path.with_suffix(".qm")
        expected = compile_ts_file(ts_path)
        if not qm_path.exists():
            problems.append(f"{qm_path.name} manquant")
        elif qm_path.read_bytes() != expected:
            problems.append(f"{qm_path.name} n'est pas à jour")
    return problems


def verify(directory: Path = TRANSLATIONS_DIR) -> list[str]:
    """Charge chaque ``.qm`` avec QTranslator et vérifie les traductions."""
    from PyQt6.QtCore import QCoreApplication, QTranslator

    app = QCoreApplication.instance() or QCoreApplication([])
    problems: list[str] = []
    for ts_path in ts_files(directory):
        qm_path = ts_path.with_suffix(".qm")
        _language, messages = parse_ts(ts_path)
        if not messages:
            problems.append(f"{ts_path.name} ne contient aucune traduction")
            continue
        translator = QTranslator()
        if not translator.load(str(qm_path)):
            problems.append(f"{qm_path.name} illisible par Qt")
            continue
        app.installTranslator(translator)
        try:
            for context, source, translation in messages:
                loaded = QCoreApplication.translate(context, source)
                if loaded != translation:
                    problems.append(
                        f"{qm_path.name} : {source!r} donne {loaded!r} "
                        f"au lieu de {translation!r}"
                    )
                    break
        finally:
            app.removeTranslator(translator)
    return problems


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compile les fichiers .ts de translations/ en .qm."
    )
    parser.add_argument(
        "--directory",
        type=Path,
        default=TRANSLATIONS_DIR,
        help="dossier contenant les .ts (par défaut : translations/)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="ne compile rien : échoue si un .qm manque ou est obsolète",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="recharge les .qm avec QTranslator après compilation",
    )
    args = parser.parse_args(argv)

    if not ts_files(args.directory):
        sys.stderr.write(f"Aucun fichier .ts dans {args.directory}\n")
        return 1

    problems: list[str] = []
    if args.check:
        problems = check(args.directory)
    else:
        for ts_path in ts_files(args.directory):
            qm_path = write_qm(ts_path)
            sys.stdout.write(f"{qm_path.name} mis à jour\n")
        problems = check(args.directory)
        if args.verify:
            problems += verify(args.directory)

    for problem in problems:
        sys.stderr.write(f"{problem}\n")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
