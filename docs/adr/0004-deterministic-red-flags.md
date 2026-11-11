# ADR 0004: Deterministic, versioned red-flag rules

Status: Accepted (2026-11-11)

Rules are JSON conditions (`all` of clauses on question codes) evaluated by pure Python on
every answer write. Outcomes are `triggered`, `not_triggered` or `not_evaluable`;
missing/unknown/declined inputs are never treated as "no risk", and per-rule coverage is shown
to staff. Events record rule version, triggering answer and revision, reason, severity label,
evaluation time and the acknowledge/escalate/resolve lifecycle.

The three seeded rules are **demo-only**, written without clinical review. A database check
constraint prevents enabling demo rules for clinical use, and clinical use requires a recorded
approver. An LLM never participates in red-flag evaluation. A rule-authoring/approval API is
not yet implemented.
