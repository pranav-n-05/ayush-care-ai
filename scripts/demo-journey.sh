#!/usr/bin/env bash
# End-to-end synthetic demo journey through the Next.js proxy (localhost:3000).
set -euo pipefail
TMPF="$(mktemp -d)/synthetic-lab-report.txt"
B=http://localhost:3000/api/v1; J=$(mktemp); O="Origin: http://localhost:3000"
login() { curl -s -c $J -b $J -H "$O" -H 'Content-Type: application/json' -d "{\"email\":\"$1\",\"password\":\"Synthetic-Demo-Only-2026\"}" $B/auth/login | python3 -c 'import sys,json;print(json.load(sys.stdin)["csrf_token"])'; }
CSRF=$(login vaidya@demo.example.org)
post() { curl -s -b $J -H "$O" -H "X-CSRF-Token: $CSRF" -H 'Content-Type: application/json' "$@"; }
get() { curl -s -b $J "$@"; }
py() { python3 -c "import sys,json;d=json.load(sys.stdin);print($1)"; }
PID=$(get "$B/patients?q=Meera" | py 'd["items"][0]["id"]'); echo "patient $PID"
ENC=$(post -X POST -d '{"visit_reason":"Synthetic demo visit"}' $B/patients/$PID/encounters | py 'd["id"]'); echo "encounter $ENC"
QV=$(get $B/questionnaires | py 'd[0]["id"]')
SID=$(post -X POST -d "{\"questionnaire_version_id\":\"$QV\",\"language\":\"ta\"}" $B/encounters/$ENC/intake-sessions | py 'd["id"]'); echo "session $SID (ta)"
post -X POST $B/intake-sessions/$SID/answers -d '{"answers":[
 {"question_code":"chief_complaint","answer_status":"answered","value":"மூட்டு வலி","translated_text_en":"Joint pain"},
 {"question_code":"complaint_duration","answer_status":"answered","value":{"amount":2,"unit":"months"}},
 {"question_code":"chest_pain","answer_status":"answered","value":true},
 {"question_code":"chest_pain_breathless","answer_status":"answered","value":true},
 {"question_code":"current_medications","answer_status":"answered","value":"None"},
 {"question_code":"has_allergies","answer_status":"answered","value":false},
 {"question_code":"onset","answer_status":"unknown"},
 {"question_code":"jihva_observation","answer_status":"answered","value":"Synthetic coated tongue observation"}]}' | py '"answers saved; missing="+str(d["missing_required"])'
post -X POST $B/intake-sessions/$SID/submit | py '"intake status="+d["status"]'
get "$B/triage/events?encounter_id=$ENC" | py '"red flags: "+str([(e["severity"],e["is_demo_rule"]) for e in d])'
printf 'SYNTHETIC LAB REPORT\nAllergy: Synthetic penicillin-like agent\nLab: Hemoglobin = 11.9 g/dL\n' > "$TMPF"
DOC=$(curl -s -b $J -H "$O" -H "X-CSRF-Token: $CSRF" -F file=@"$TMPF" -F document_type=lab_report $B/encounters/$ENC/documents | py 'd["id"]'); echo "document $DOC"
OJ=$(post -X POST -H "Idempotency-Key: ocr-$RANDOM-$RANDOM" $B/documents/$DOC/process | py 'd["id"]')
for i in $(seq 1 20); do ST=$(get $B/ocr-jobs/$OJ | py 'd["status"]'); [ "$ST" = succeeded ] || [ "$ST" = failed ] && break; sleep 1; done; echo "ocr job $ST (via Celery worker)"
for E in $(get $B/documents/$DOC/entities | py '" ".join(e["id"] for e in d)'); do post -X POST -d '{"action":"verify","expected_revision":1}' $B/extracted-entities/$E/review >/dev/null; done; echo "entities verified"
SJ=$(post -X POST -H "Idempotency-Key: sum-$RANDOM-$RANDOM" $B/encounters/$ENC/summaries/generate | py 'd["id"]')
for i in $(seq 1 20); do ST=$(get $B/summary-jobs/$SJ | py 'd["status"]'); [ "$ST" = succeeded ] || [ "$ST" = failed ] && break; sleep 1; done; echo "summary job $ST"
get $B/encounters/$ENC/summary | py '"summary v"+str(d["current_version_number"])+" "+d["status"]+"; claims="+str(sum(len(s["claims"]) for s in d["current_version"]["content"]["sections"]))+"; contradictions="+str(len(d["current_version"]["content"]["contradictions"]))'
SUMID=$(get $B/encounters/$ENC/summary | py 'd["id"]')
post -X POST -d '{"version_number":1,"attestation_confirmed":true}' $B/summaries/$SUMID/approve | py '"after approve: "+d["status"]+" v"+str(d["approved_version_number"])'
get $B/dashboard/overview | py '"dashboard: "+", ".join(m["key"]+"="+str(m["value"]) for m in d["metrics"])'
