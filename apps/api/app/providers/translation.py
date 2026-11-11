"""Translation / speech / text-to-speech interfaces. No implementation is configured: the
'not configured' providers make the absence explicit instead of faking output."""

from dataclasses import dataclass
from typing import Protocol


@dataclass
class TranslationResult:
    text: str
    provider: str
    provider_version: str


class TranslationProvider(Protocol):
    def translate(
        self, text: str, source_lang: str, target_lang: str
    ) -> TranslationResult | None: ...


class SpeechProvider(Protocol):
    def transcribe(self, audio: bytes, language: str) -> TranslationResult | None: ...


class TextToSpeechProvider(Protocol):
    def synthesize(self, text: str, language: str) -> bytes | None: ...


class NotConfiguredTranslationProvider:
    def translate(self, text: str, source_lang: str, target_lang: str) -> None:
        return None


class NotConfiguredSpeechProvider:
    def transcribe(self, audio: bytes, language: str) -> None:
        return None
