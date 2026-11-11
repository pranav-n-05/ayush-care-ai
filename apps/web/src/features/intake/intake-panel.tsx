"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Alert, Badge, Card, Label, QueryState, Select } from "@/components/ui/primitives";
import { can, useMe } from "@/features/auth/use-me";
import { api, ApiError, type IntakeSession, type QuestionnaireVersion } from "@/lib/api";

import { QuestionField, type AnswerDraft } from "./question-field";

export function IntakePanel({ encounterId }: { encounterId: string }) {
  const me = useMe();
  const qc = useQueryClient();
  const [lang, setLang] = useState("en");
  const [error, setError] = useState<string | null>(null);
  const sessions = useQuery({ queryKey: ["sessions", encounterId], queryFn: () => api<string[]>(`/encounters/${encounterId}/intake-sessions`) });
  const versions = useQuery({ queryKey: ["questionnaires"], queryFn: () => api<QuestionnaireVersion[]>("/questionnaires") });
  const sessionId = sessions.data?.at(-1);
  const session = useQuery({ queryKey: ["session", sessionId], queryFn: () => api<IntakeSession>(`/intake-sessions/${sessionId}`), enabled: !!sessionId });

  const onErr = (e: unknown) => {
    if (e instanceof ApiError && Array.isArray(e.details)) setError(`${e.message}: ${(e.details as { question?: string; error?: string }[]).map((d) => `${d.question} — ${d.error}`).join("; ")}`);
    else if (e instanceof ApiError && e.details && typeof e.details === "object" && "missing" in e.details) setError(`${e.message}: ${(e.details as { missing: string[] }).missing.join(", ")}`);
    else setError(e instanceof Error ? e.message : "Request failed");
  };
  const setSession = (s: IntakeSession) => { setError(null); qc.setQueryData(["session", s.id], s); qc.invalidateQueries({ queryKey: ["triage", encounterId] }); };

  const start = useMutation({
    mutationFn: (versionId: string) => api<IntakeSession>(`/encounters/${encounterId}/intake-sessions`, { method: "POST", body: { questionnaire_version_id: versionId, language: lang } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sessions", encounterId] }),
    onError: onErr,
  });
  const save = useMutation({ mutationFn: (a: AnswerDraft) => api<IntakeSession>(`/intake-sessions/${sessionId}/answers`, { method: "POST", body: { answers: [a] } }), onSuccess: setSession, onError: onErr });
  const submit = useMutation({ mutationFn: () => api<IntakeSession>(`/intake-sessions/${sessionId}/submit`, { method: "POST" }), onSuccess: setSession, onError: onErr });
  const review = useMutation({ mutationFn: () => api<IntakeSession>(`/intake-sessions/${sessionId}/review`, { method: "POST" }), onSuccess: setSession, onError: onErr });

  if (!can(me.data, "intake.read")) return <p className="text-sm">Your role cannot view intake responses.</p>;
  if (sessions.isLoading) return <p role="status">Loading…</p>;

  if (!sessionId) {
    const v = versions.data?.[0];
    return (
      <Card className="space-y-3">
        {error && <Alert tone="danger">{error}</Alert>}
        <p className="text-sm">No intake session yet.</p>
        {v && <p className="text-xs text-amber-800">Questionnaire: {v.title} v{v.version_number} — {v.clinical_review_status.replace("_", " ")}</p>}
        <div className="max-w-xs">
          <Label htmlFor="lang">Intake language</Label>
          <Select id="lang" value={lang} onChange={(e) => setLang(e.target.value)}>
            <option value="en">English</option><option value="hi">हिन्दी</option><option value="ta">தமிழ்</option>
          </Select>
        </div>
        {can(me.data, "intake.answer") && v && <Button onClick={() => start.mutate(v.id)} disabled={start.isPending}>Start intake</Button>}
      </Card>
    );
  }

  const s = session.data;
  const editable = s && s.status === "in_progress" ? can(me.data, "intake.answer") : s?.status === "submitted" && can(me.data, "intake.review");
  const sections = s ? [...new Set(s.questions.map((q) => q.section))] : [];
  return (
    <QueryState isLoading={session.isLoading} error={session.error}>
      {s && (
        <div className="space-y-4">
          <Alert tone="warn">{s.clinical_disclaimer}</Alert>
          {error && <Alert tone="danger">{error}</Alert>}
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <Badge>{s.status}</Badge><Badge tone="info">language: {s.language}</Badge>
            {s.missing_required.length > 0 && <Badge tone="warn">{s.missing_required.length} required without a response</Badge>}
            {s.red_flag_rule_coverage.filter((r) => r.outcome === "not_evaluable").length > 0 && (
              <Badge tone="warn">{s.red_flag_rule_coverage.filter((r) => r.outcome === "not_evaluable").length} red-flag rule(s) not evaluable (missing data ≠ no risk)</Badge>
            )}
          </div>
          {sections.map((sec) => (
            <section key={sec} aria-labelledby={`sec-${sec}`} className="space-y-2">
              <h3 id={`sec-${sec}`} className="font-semibold capitalize">{sec.replaceAll("_", " ")}</h3>
              {s.questions.filter((q) => q.section === sec && q.visible).map((q) => (
                <QuestionField key={`${q.code}-${q.current_answer?.revision ?? 0}`} q={q} onSave={(a) => save.mutate(a)} disabled={!editable || save.isPending || (q.respondent === "practitioner" && !can(me.data, "intake.review"))} needsReason={s.status === "submitted"} />
              ))}
            </section>
          ))}
          <div className="flex gap-2">
            {s.status === "in_progress" && can(me.data, "intake.answer") && <Button onClick={() => submit.mutate()}>Submit intake</Button>}
            {s.status === "submitted" && can(me.data, "intake.review") && <Button onClick={() => review.mutate()}>Mark reviewed</Button>}
          </div>
        </div>
      )}
    </QueryState>
  );
}
