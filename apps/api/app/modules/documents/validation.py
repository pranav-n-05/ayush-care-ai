"""Upload validation: allowlisted extensions, magic-byte signatures that must agree with the
extension, size limits, PDF page/active-content limits and image dimension limits (to bound
decompression). No antivirus scanner is configured; results say so explicitly."""

import re
import struct
from dataclasses import dataclass
from pathlib import PurePath

MAX_IMAGE_PIXELS = 40_000_000  # ~ 6300 x 6300

_EXT_MIME = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".txt": "text/plain",
}


class UploadRejected(ValueError):
    pass


@dataclass
class ValidatedFile:
    mime_type: str
    display_filename: str
    page_count: int | None


def sanitize_filename(name: str) -> str:
    base = PurePath(name.replace("\\", "/")).name
    base = re.sub(r"[^A-Za-z0-9._ -]", "_", base).strip(" .")
    if not base:
        base = "document"
    stem, dot, ext = base.rpartition(".")
    if dot and len(base) > 100:
        base = stem[: 100 - len(ext) - 1] + "." + ext
    return base[:100]


def _sniff(data: bytes) -> str | None:
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    return None


def _png_dims(data: bytes) -> tuple[int, int]:
    if len(data) < 24 or data[12:16] != b"IHDR":
        raise UploadRejected("Malformed PNG")
    w, h = struct.unpack(">II", data[16:24])
    return w, h


def _jpeg_dims(data: bytes) -> tuple[int, int]:
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            h, w = struct.unpack(">HH", data[i + 5 : i + 9])
            return w, h
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        (seg_len,) = struct.unpack(">H", data[i + 2 : i + 4])
        i += 2 + seg_len
    raise UploadRejected("Malformed JPEG")


def validate_upload(
    filename: str, data: bytes, *, max_bytes: int, max_pdf_pages: int
) -> ValidatedFile:
    if not data:
        raise UploadRejected("File is empty")
    if len(data) > max_bytes:
        raise UploadRejected(f"File exceeds {max_bytes // (1024 * 1024)} MB limit")
    display = sanitize_filename(filename)
    ext = PurePath(display.lower()).suffix
    expected = _EXT_MIME.get(ext)
    if expected is None:
        raise UploadRejected("File type not allowed (pdf, png, jpg, txt)")
    sniffed = _sniff(data)
    if expected == "text/plain":
        if sniffed is not None or b"\x00" in data:
            raise UploadRejected("File content does not match its extension")
        try:
            data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise UploadRejected("Text files must be UTF-8") from exc
        return ValidatedFile("text/plain", display, 1)
    if sniffed != expected:
        raise UploadRejected("File content does not match its extension")
    if expected == "application/pdf":
        if re.search(rb"/(JavaScript|JS|Launch|EmbeddedFile|OpenAction)\b", data):
            raise UploadRejected("PDFs with active or embedded content are not accepted")
        pages = len(re.findall(rb"/Type\s*/Page(?!s)", data))
        if pages > max_pdf_pages:
            raise UploadRejected(f"PDF exceeds {max_pdf_pages} pages")
        return ValidatedFile(expected, display, pages or None)
    w, h = _png_dims(data) if expected == "image/png" else _jpeg_dims(data)
    if w <= 0 or h <= 0 or w * h > MAX_IMAGE_PIXELS:
        raise UploadRejected("Image dimensions exceed the allowed limit")
    return ValidatedFile(expected, display, 1)
