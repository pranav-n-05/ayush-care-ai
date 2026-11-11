# API examples

Interactive OpenAPI docs: `http://localhost:8000/docs` (disabled in production). All errors use
`{"error": {"code", "message", "details"}}`. Unsafe requests need the session cookie,
`X-CSRF-Token`, and (if sent) a trusted `Origin`.

```bash
B=http://localhost:3000/api/v1; J=cookies.txt
# login -> sets HttpOnly ayush_session + readable ayush_csrf, returns csrf_token
CSRF=$(curl -s -c $J -H 'Content-Type: application/json' \
  -d '{"email":"vaidya@demo.example.org","password":"Synthetic-Demo-Only-2026"}' $B/auth/login | jq -r .csrf_token)
H=(-b $J -H "X-CSRF-Token: $CSRF" -H 'Content-Type: application/json')

curl -s -b $J "$B/patients?q=Meera&limit=10&sort=-created_at"          # Page[PatientListItem]
curl -s "${H[@]}" -d '{"given_name":"Test","sex_for_clinical_use":"unknown","age_years":30,"age_recorded_on":"2026-11-01"}' $B/patients
#  -> 201 {"patient": {...}, "possible_duplicates": [...]}   (flags only, never merged)

curl -s "${H[@]}" -X POST -d '{}' $B/patients/$PID/encounters                    # 201 Encounter
curl -s "${H[@]}" -d "{\"questionnaire_version_id\":\"$QV\",\"language\":\"hi\"}" $B/encounters/$ENC/intake-sessions
curl -s "${H[@]}" -d '{"answers":[{"question_code":"has_allergies","answer_status":"unknown"}]}' $B/intake-sessions/$SID/answers
#  -> 422 with per-question details if any answer is invalid or hidden; nothing is saved

curl -s -b $J -H "X-CSRF-Token: $CSRF" -F file=@synthetic.txt -F document_type=lab_report $B/encounters/$ENC/documents
curl -s "${H[@]}" -X POST -H 'Idempotency-Key: 7d6b...' $B/documents/$DOC/process
#  -> 202 {"id": job, "status": "queued"}; same key again -> 200 same job
curl -s "${H[@]}" -X POST -H 'Idempotency-Key: 9a1c...' $B/encounters/$ENC/summaries/generate
#  -> 202 job; 409 consent_required if AI-documentation consent is not granted
curl -s "${H[@]}" -d '{"version_number":1,"attestation_confirmed":true}' $B/summaries/$SUM/approve
#  -> 200; 409 stale_version | already_approved | sources_changed
```

Status codes: 401 not authenticated / expired / revoked; 403 permission denied, CSRF failure,
untrusted origin; 404 not found *or belongs to another organization*; 409 conflicts and stale
versions; 422 validation; 502 reserved for provider failures surfaced synchronously.
Rate limiting (429) is not implemented in the API.
