"""Deterministic line-pattern extraction from OCR text. Output is always UNVERIFIED."""

import re
from dataclasses import dataclass, field
from typing import Any

from app.providers.ocr import OCRResult

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("medication", re.compile(r"^\s*(?:medication|medicine|rx|drug)\s*[:\-]\s*(?P<v>.+)$", re.I)),
    ("allergy", re.compile(r"^\s*(?:allergy|allergies|allergic to)\s*[:\-]\s*(?P<v>.+)$", re.I)),
    (
        "condition_mentioned",
        re.compile(r"^\s*(?:diagnosis|impression|condition)\s*[:\-]\s*(?P<v>.+)$", re.I),
    ),
]
_LAB = re.compile(
    r"^\s*(?:lab|test)\s*[:\-]\s*(?P<name>[^=:]+?)\s*[=:]\s*(?P<value>-?[0-9]+(?:\.[0-9]+)?)\s*(?P<unit>[A-Za-z/%0-9.]+)?\s*$",
    re.I,
)


@dataclass
class Candidate:
    entity_type: str
    text: str
    page: int
    line: int
    confidence: float | None
    attributes: dict[str, Any] = field(default_factory=dict)
    region: dict[str, float] | None = None


def extract_entities(result: OCRResult) -> list[Candidate]:
    out: list[Candidate] = []
    for page in result.pages:
        for idx, line in enumerate(page.lines, start=1):
            text = line.text.strip()
            if not text:
                continue
            m = _LAB.match(text)
            if m:
                out.append(
                    Candidate(
                        "lab_result",
                        text[:500],
                        page.number,
                        idx,
                        line.confidence,
                        {"name": m["name"].strip(), "value": m["value"], "unit": m["unit"]},
                        line.bbox,
                    )
                )
                continue
            for etype, pat in _PATTERNS:
                m = pat.match(text)
                if m:
                    out.append(
                        Candidate(
                            etype,
                            m["v"].strip()[:500],
                            page.number,
                            idx,
                            line.confidence,
                            {},
                            line.bbox,
                        )
                    )
                    break
    return out
