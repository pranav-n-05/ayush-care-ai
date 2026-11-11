"""OCR provider interface. Implementations MUST report confidence only when the engine
actually produces one; otherwise None."""

from dataclasses import dataclass, field
from typing import Protocol


class OCRUnsupported(Exception):
    """The configured provider cannot process this file type (non-retryable)."""


class OCRTransientError(Exception):
    """Temporary failure (timeout, engine unavailable) — the job may be retried."""


@dataclass
class OCRLine:
    text: str
    confidence: float | None = None
    bbox: dict[str, float] | None = None


@dataclass
class OCRPage:
    number: int
    lines: list[OCRLine] = field(default_factory=list)


@dataclass
class OCRResult:
    provider: str
    provider_version: str
    pages: list[OCRPage]

    @property
    def text(self) -> str:
        return "\n\n".join("\n".join(line.text for line in p.lines) for p in self.pages)


class OCRProvider(Protocol):
    name: str
    version: str

    def extract(self, data: bytes, mime_type: str) -> OCRResult: ...


class DemoTextOCRProvider:
    """DEMO provider: reads synthetic UTF-8 .txt "scans" line by line. It performs no image
    recognition and reports no confidence. PaddleOCR (or similar) can be added behind the same
    interface; it is not installed in this project."""

    name = "demo-text"
    version = "1"

    def extract(self, data: bytes, mime_type: str) -> OCRResult:
        if mime_type != "text/plain":
            raise OCRUnsupported(
                "The configured demo OCR provider only reads synthetic .txt documents"
            )
        pages = []
        for n, chunk in enumerate(data.decode("utf-8").split("\f"), start=1):
            pages.append(OCRPage(number=n, lines=[OCRLine(text=t) for t in chunk.splitlines()]))
        return OCRResult(provider=self.name, provider_version=self.version, pages=pages)


_provider: OCRProvider | None = None


def get_ocr_provider() -> OCRProvider:
    global _provider
    if _provider is None:
        _provider = DemoTextOCRProvider()
    return _provider


def set_ocr_provider(p: OCRProvider | None) -> None:
    global _provider
    _provider = p
