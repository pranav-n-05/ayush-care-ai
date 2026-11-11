"""DEMO extractive summarizer. Deterministic and local (no network, no model). It restates
source facts with citations and never adds clinical interpretation. It exists so the full
workflow (citations, validation, versioning, approval) can be exercised without sending data
to an external AI provider."""

import json
from typing import Any

from app.providers.llm import GenerationResult, SummaryRequest

SECTION_FOR_QUESTION = {
    "chief_complaint": "presenting_complaint",
    "chest_pain": "presenting_complaint",
    "chest_pain_breathless": "presenting_complaint",
    "complaint_duration": "history_of_present_illness",
    "onset": "history_of_present_illness",
    "severity": "history_of_present_illness",
    "progression": "history_of_present_illness",
    "associated_symptoms": "history_of_present_illness",
    "prior_treatment": "history_of_present_illness",
    "medical_history": "relevant_medical_history",
    "surgical_history": "relevant_medical_history",
    "family_history": "relevant_medical_history",
    "current_medications": "medications_and_allergies",
    "has_allergies": "medications_and_allergies",
    "allergy_details": "medications_and_allergies",
}
SECTION_FOR_SOURCE_SECTION = {
    "lifestyle": "relevant_medical_history",
    "ayurveda_patient_reported": "ayurveda_observations",
    "practitioner_observations": "ayurveda_observations",
}
SECTION_FOR_ENTITY = {
    "medication": "medications_and_allergies",
    "allergy": "medications_and_allergies",
    "lab_result": "relevant_medical_history",
    "condition_mentioned": "relevant_medical_history",
    "other": "relevant_medical_history",
}
TITLES = {
    "presenting_complaint": "Presenting complaint",
    "history_of_present_illness": "History of present illness",
    "relevant_medical_history": "Relevant medical history",
    "medications_and_allergies": "Medications and allergies",
    "ayurveda_observations": "Ayurveda observations",
}
LEAD = {
    "patient_reported": "Patient reports",
    "practitioner_observed": "Practitioner observed",
    "document_verified": "Verified document states",
}


def _render_value(src: dict[str, Any]) -> tuple[str, str]:
    value = src["value"]
    certainty = "stated"
    if isinstance(value, str):
        if src.get("text_en"):
            text = src["text_en"]
            if src.get("translation_status") == "draft_requires_review":
                text += " (draft translation; requires review)"
                certainty = "uncertain"
        else:
            text = f"[untranslated response] {value}"
            certainty = "uncertain"
    elif isinstance(value, bool):
        text = "yes" if value else "no"
    elif isinstance(value, dict) and set(value) == {"amount", "unit"}:
        text = f"{value['amount']} {value['unit']}"
    elif isinstance(value, list):
        text = ", ".join(str(v).replace("_", " ") for v in value)
    else:
        text = str(value).replace("_", " ") if isinstance(value, str) else str(value)
    return text, certainty


class DemoExtractiveProvider:
    name = "demo-extractive"
    model = "deterministic-template-v1"
    is_external = False

    async def generate(self, request: SummaryRequest) -> GenerationResult:
        sections: dict[str, list[dict[str, Any]]] = {k: [] for k in TITLES}
        answered = [s for s in request.sources if s["answer_status"] == "answered"]
        for src in answered:
            if src["kind"] == "extracted_entity":
                sec = SECTION_FOR_ENTITY.get(src["label"], "relevant_medical_history")
                prefix = f"{LEAD['document_verified']} ({src['prompt_en']})"
            else:
                sec = SECTION_FOR_QUESTION.get(src["label"]) or SECTION_FOR_SOURCE_SECTION.get(
                    src["section"], "relevant_medical_history"
                )
                prefix = f"{LEAD[src['provenance']]} — {src['prompt_en'].rstrip('?').rstrip('.')}"
            text, certainty = _render_value(src)
            sections[sec].append(
                {
                    "text": f"{prefix}: {text}"[:1000],
                    "provenance": src["provenance"],
                    "certainty": certainty,
                    "source_refs": [
                        {"kind": src["kind"], "id": src["id"], "revision": src["revision"]}
                    ],
                }
            )

        contradictions = []
        by_label: dict[str, list[dict[str, Any]]] = {}
        for s in answered:
            by_label.setdefault(s["label"], []).append(s)
        for neg_q, entity in (("has_allergies", "allergy"), ("current_medications", "medication")):
            for q in by_label.get(neg_q, []):
                denies = q["value"] is False or (
                    isinstance(q["value"], str)
                    and q["value"].strip().lower() in {"none", "nil", "no"}
                )
                if denies and by_label.get(entity):
                    e = by_label[entity][0]
                    contradictions.append(
                        {
                            "description": f"Intake answer to '{q['prompt_en']}' conflicts with a verified document {entity} entry.",
                            "source_refs": [
                                {"kind": q["kind"], "id": q["id"], "revision": q["revision"]},
                                {"kind": e["kind"], "id": e["id"], "revision": e["revision"]},
                            ],
                        }
                    )

        clarifications = [
            {"text": f"Please clarify: {m['prompt_en']}", "source_refs": []}
            for m in request.missing
            if m.get("prompt_en")
        ]
        content = {
            "sections": [{"code": k, "title": TITLES[k], "claims": v} for k, v in sections.items()],
            "missing_information": [
                {"question_code": m["question_code"], "state": m["state"]} for m in request.missing
            ],
            "contradictions": contradictions,
            "clarification_questions": clarifications[:20],
            "disclaimer": (
                "AI-assisted DRAFT generated by a deterministic demo summarizer from synthetic data. "
                "Not a diagnosis or treatment recommendation. Requires practitioner review and approval."
            ),
        }
        raw = json.dumps(content, ensure_ascii=False)
        return GenerationResult(
            raw_output=raw,
            input_units=len(request.sources),
            output_units=len(raw),
            estimated_cost_usd=0.0,
        )
