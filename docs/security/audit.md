# Audit logging

`audit_events` records actor, organization, action, entity type/id, outcome
(`success|denied|failure`), correlation ID, timestamp and **non-clinical** details. The audit
service rejects detail keys such as `value`, `text`, `name`, `phone`, `token`.

Audited reads include patient view/search, encounter view, intake session view, summary view,
document download, FHIR export and patient self-view. Denials and login failures are written
in an independent transaction.

**Integrity limitations.** This is an ordinary PostgreSQL table. It is not tamper-proof or
append-only at the database level. Recommended production hardening (not implemented here):
run the app as a role with `INSERT`/`SELECT` but no `UPDATE`/`DELETE` on `audit_events`,
ship events to an external write-once store, and consider hash chaining.
