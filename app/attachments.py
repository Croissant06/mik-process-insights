"""Validate upload data and scan it before saving the report."""
from __future__ import annotations

import base64
import binascii
import re
import socket
import struct
import unicodedata

from app.config import Settings
from app.models import ReportAttachment

UPLOAD_PATH = "/api/submissions/with-attachments"
MAX_FILES = 3
MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_ENCODED_BYTES = 4 * ((MAX_FILE_BYTES + 2) // 3)
MAX_UPLOAD_REQUEST = MAX_FILES * MAX_ENCODED_BYTES + 256 * 1024


class InvalidAttachment(ValueError):
    pass


class ScannerUnavailable(RuntimeError):
    pass


def _scan(content: bytes, host: str, port: int) -> None:
    try:
        with socket.create_connection((host, port), timeout=10) as client:
            client.sendall(b"zINSTREAM\0")
            for pos in range(0, len(content), 65536):
                chunk = content[pos:pos + 65536]
                client.sendall(struct.pack("!I", len(chunk)) + chunk)
            client.sendall(b"\0\0\0\0")
            with client.makefile("rb") as reply:
                result = b""
                while len(result) < 4096:
                    byte = reply.read(1)
                    if byte in (b"", b"\0"):
                        break
                    result += byte
    except OSError as exc:
        raise ScannerUnavailable from exc
    if byte == b"\0" and result == b"stream: OK":
        return
    if byte == b"\0" and result.endswith(b" FOUND"):
        raise InvalidAttachment("Един от файловете не премина проверката. Премахнете го и опитайте отново.")
    raise ScannerUnavailable


def prepare_files(raw: object, settings: Settings) -> list[ReportAttachment]:
    if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_FILES:
        raise InvalidAttachment(f"Изберете от 1 до {MAX_FILES} файла.")
    files = []
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            raise InvalidAttachment("Невалидно име на файл.")
        name = unicodedata.normalize("NFC", item["name"])
        if (not 1 <= len(name) <= 200 or not name.strip(". ")
                or re.search(r'[/\\\x00-\x1f\x7f]', name)
                or any(unicodedata.category(char) in {"Cf", "Cs"} for char in name)):
            raise InvalidAttachment("Името на файла е невалидно. Преименувайте файла и опитайте отново.")
        encoded = item.get("data")
        if not isinstance(encoded, str) or not 1 <= len(encoded) <= MAX_ENCODED_BYTES:
            raise InvalidAttachment("Всеки файл трябва да е до 5 MB.")
        try:
            content = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            raise InvalidAttachment("Файлът не може да бъде прочетен.") from None
        if not 1 <= len(content) <= MAX_FILE_BYTES:
            raise InvalidAttachment("Всеки файл трябва да съдържа данни и да е до 5 MB.")
        files.append(ReportAttachment(filename=name, content=content))

    if settings.attachment_scan_host:
        for attachment in files:
            _scan(attachment.content, settings.attachment_scan_host, settings.attachment_scan_port)
    elif settings.environment in {"staging", "production"}:
        raise ScannerUnavailable
    return files
