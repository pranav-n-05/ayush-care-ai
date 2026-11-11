# Evaluation methodology (planned)

Nothing in this file is a result. Results go in `metrics.md` only after they are measured.

1. **API latency** — k6 or Locust against the compose stack with N synthetic patients; report
   p50/p95 per endpoint, hardware, dataset size, date, command.
2. **OCR** — labeled synthetic document set (count, types); field-level precision/recall of
   extracted entities vs labels. The current demo provider reads text only, so image OCR
   accuracy cannot be measured until a real engine (e.g. PaddleOCR) is integrated.
3. **Summary attribution validity** — % of claims whose citations resolve and whose text is
   supported by the cited source, judged by a written rubric on a synthetic set.
4. **Unsupported-claim rate** — claims not entailed by any cited source, per rubric.
5. **Simulated review** — edits/acceptance on a *clearly labeled simulated* review dataset.
   This is not clinician validation and must not be described as such.
6. **Accessibility** — axe-core + manual keyboard/screen-reader pass on core journeys.
