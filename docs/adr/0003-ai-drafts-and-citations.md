# ADR 0003: AI output is a cited, validated draft; demo provider is local

Status: Accepted (2026-11-11)

**Decision.**
* LLM access is behind `LLMProvider`. The only implementation is `DemoExtractiveProvider`, a
  deterministic, in-process template that restates source facts. No external model is called,
  so no identifiable data leaves the deployment.
* Output must parse into `SummaryContent` (Pydantic). Each claim needs ≥1 source reference
  `(kind, id, revision)` that exists in the encounter's current source set, a provenance that
  matches the source, and `uncertain` certainty when the source is an unreviewed translation.
  A coarse language guard rejects diagnostic/prescriptive phrasing in the model's own words
  (quoted source text is excluded from that check). Any violation fails the attempt.
* Retries are bounded (`llm_max_attempts`, default 2) with a per-call timeout. A failed job is
  `failed` with a user-safe reason; nothing is substituted.
* If a provider reports `is_external = True`, the worker refuses unless the organization has
  `external_ai_approved = true` — and that flag must only be set after processing terms,
  security controls and legal review are documented.
* Approval binds a practitioner to an immutable version and source snapshot hash.

**Consequences.** The demo summaries are not "intelligent" — they prove the safety plumbing,
not model quality. Integrating a real model needs prompt evaluation (see
`docs/evaluation/methodology.md`) before any claim about quality.
