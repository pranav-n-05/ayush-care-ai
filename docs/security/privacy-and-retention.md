# Privacy, retention and open legal questions

* Synthetic data only; seeds and tests generate fictional people (`*Synthetic*`, `example.com`).
* Consent is recorded per type (`data_processing`, `ai_assisted_documentation`,
  `contact_reminders`) with an append-only event history. AI drafting and reminders check consent.
* Notifications use a generic template with no clinical content.
* No hard deletes of clinical data; patients can only be deactivated.

Unresolved (require legal review before any real use): retention periods per record type,
erasure requests vs clinical record-keeping duties, legal hold, backup expiry alignment,
audit-log minimization, cross-border processing, DPDP Act applicability. Removing direct
identifiers from an export must not be described as anonymization.
