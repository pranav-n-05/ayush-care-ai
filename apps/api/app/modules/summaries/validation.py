import json

from pydantic import ValidationError

from app.modules.summaries.schema import SourceRef, SummaryContent, prohibited_language
from app.modules.summaries.sources import Source, SourceSet

_KIND_PROVENANCE = {
    "extracted_entity": {"document_verified"},
    "intake_answer": {"patient_reported", "practitioner_observed"},
}
_UNCERTAIN_TRANSLATIONS = {"translation_pending", "draft_requires_review"}


def _own_words(text: str, refs: list[SourceRef], index: dict[tuple[str, str, int], Source]) -> str:
    """Remove verbatim quotations of cited sources (patient text, question wording) so the
    language guard applies to what the model itself wrote, not to quoted source data."""
    for ref in refs:
        src = index.get((ref.kind, ref.id, ref.revision))
        if src is None:
            continue
        for quoted in (
            src.text_en,
            src.value if isinstance(src.value, str) else None,
            src.prompt_en.rstrip("?."),
        ):
            if quoted:
                text = text.replace(quoted, " ")
    return text


class SummaryValidationError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors[:5]))
        self.errors = errors


def validate_content(
    raw: str | dict[str, object], sources: SourceSet, *, allow_practitioner_authored: bool
) -> SummaryContent:
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        content = SummaryContent.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise SummaryValidationError(
            [f"Output does not match the summary schema: {type(exc).__name__}"]
        ) from exc

    index = sources.by_key()
    errors: list[str] = []

    def check_ref(ref: SourceRef, where: str) -> None:
        if (ref.kind, ref.id, ref.revision) not in index:
            errors.append(
                f"{where}: cites unknown or stale source {ref.kind}:{ref.id}@{ref.revision}"
            )

    for s_i, section in enumerate(content.sections):
        for c_i, claim in enumerate(section.claims):
            where = f"sections[{s_i}].claims[{c_i}]"
            if claim.provenance == "practitioner_authored":
                if not allow_practitioner_authored:
                    errors.append(f"{where}: AI drafts cannot contain practitioner-authored claims")
            elif not claim.source_refs:
                errors.append(f"{where}: claim has no source reference")
            if prohibited_language(_own_words(claim.text, claim.source_refs, index)):
                errors.append(f"{where}: contains diagnostic or prescriptive language")
            for ref in claim.source_refs:
                check_ref(ref, where)
                src = index.get((ref.kind, ref.id, ref.revision))
                if src is None:
                    continue
                if (
                    claim.provenance != "practitioner_authored"
                    and claim.provenance not in _KIND_PROVENANCE[ref.kind]
                ):
                    errors.append(
                        f"{where}: provenance {claim.provenance} does not match a {ref.kind}"
                    )
                if (
                    claim.provenance in ("patient_reported", "practitioner_observed")
                    and src.provenance != claim.provenance
                ):
                    errors.append(
                        f"{where}: claims {claim.provenance} but source is {src.provenance}"
                    )
                if src.answer_status != "answered":
                    errors.append(f"{where}: cites a '{src.answer_status}' response as a fact")
                if (
                    src.translation_status in _UNCERTAIN_TRANSLATIONS
                    and claim.certainty != "uncertain"
                ):
                    errors.append(f"{where}: unreviewed translation must be marked uncertain")
    for i, con in enumerate(content.contradictions):
        for ref in con.source_refs:
            check_ref(ref, f"contradictions[{i}]")
    for i, cq in enumerate(content.clarification_questions):
        if prohibited_language(cq.text):
            errors.append(
                f"clarification_questions[{i}]: contains diagnostic or prescriptive language"
            )
        for ref in cq.source_refs:
            check_ref(ref, f"clarification_questions[{i}]")
    if errors:
        raise SummaryValidationError(errors)
    return content
