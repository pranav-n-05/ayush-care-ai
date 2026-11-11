"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Alert, Badge, Card } from "@/components/ui/primitives";
import { can, useMe } from "@/features/auth/use-me";
import { api, ApiError, idempotencyKey, type Job, type Summary } from "@/lib/api";

import { ClaimList } from "./claim-list";

export function SummaryPanel({ encounterId }: { encounterId: string }) {
  const me = useMe();
  const qc = useQueryClient();
  const [job, setJob] = useState<Job | null>(null);
  const [confirm, setConfirm] = useState(false);
  const summary = useQuery({
    queryKey: ["summary", encounterId],
    queryFn: () => api<Summary>(`/encounters/${encounterId}/summary`).catch((e) => { if (e instanceof ApiError && e.status === 404) return null; throw e; }),
    enabled: can(me.data, "summary.read"),
  });
  const generate = useMutation({
    mutationFn: () => api<Job>(`/encounters/${encounterId}/summaries/generate`, { method: "POST", headers: { "Idempotency-Key": idempotencyKey() } }),
    onSuccess: setJob,
  });
  const jobQ = useQuery({
    queryKey: ["summary-job", job?.id],
    queryFn: async () => {
      const j = await api<Job>(`/summary-jobs/${job?.id}`);
      if (j.status === "succeeded") qc.invalidateQueries({ queryKey: ["summary", encounterId] });
      return j;
    },
    enabled: !!job,
    refetchInterval: (q) => (q.state.data && ["succeeded", "failed"].includes(q.state.data.status) ? false : 2000),
  });
  const approve = useMutation({
    mutationFn: (version: number) => api<Summary>(`/summaries/${summary.data?.id}/approve`, { method: "POST", body: { version_number: version, attestation_confirmed: true } }),
    onSuccess: (s) => { qc.setQueryData(["summary", encounterId], s); setConfirm(false); },
  });

  if (!can(me.data, "summary.read")) return <p className="text-sm">Your role cannot view summaries.</p>;
  const s = summary.data;
  const v = s?.current_version;
  const jobState = jobQ.data ?? job;
  return (
    <div className="space-y-3">
      <Alert tone="warn">AI-assisted drafts restate cited records only. They are not diagnoses or treatment advice and require practitioner approval.</Alert>
      {can(me.data, "summary.generate") && (
        <div className="flex items-center gap-2">
          <Button onClick={() => generate.mutate()} disabled={generate.isPending || jobState?.status === "queued" || jobState?.status === "running"}>Generate draft</Button>
          {jobState && <Badge tone={jobState.status === "failed" ? "danger" : "neutral"}>job {jobState.status}</Badge>}
        </div>
      )}
      {generate.error && <Alert tone="danger">{(generate.error as Error).message}</Alert>}
      {jobState?.failure_reason && <Alert tone="danger">{jobState.failure_reason}</Alert>}
      {summary.isLoading && <p role="status">Loading…</p>}
      {s === null && <p className="text-sm text-slate-500">No summary yet.</p>}
      {s && v && (
        <Card className="space-y-4">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <Badge tone={s.status === "approved" ? "ok" : "warn"}>{s.status === "approved" ? `approved v${s.approved_version_number}` : "DRAFT"}</Badge>
            <span>version {v.version_number} · {v.origin.replace("_", " ")} · {v.provider}/{v.model}</span>
            {s.approved_version_number && s.status === "draft" && <Badge>v{s.approved_version_number} previously approved</Badge>}
          </div>
          {v.content.sections.map((sec) => (
            <section key={sec.code} aria-labelledby={`s-${sec.code}`}>
              <h3 id={`s-${sec.code}`} className="mb-1 font-semibold">{sec.title}</h3>
              <ClaimList claims={sec.claims} />
            </section>
          ))}
          {v.content.contradictions.length > 0 && (
            <section><h3 className="font-semibold">Contradictions to check</h3><ul className="list-disc pl-5 text-sm">{v.content.contradictions.map((c, i) => <li key={i}>{c.description}</li>)}</ul></section>
          )}
          {v.content.missing_information.length > 0 && (
            <section><h3 className="font-semibold">Missing information</h3><p className="text-sm">{v.content.missing_information.map((m) => `${m.question_code} (${m.state})`).join(", ")}</p></section>
          )}
          {v.content.clarification_questions.length > 0 && (
            <section><h3 className="font-semibold">Clarification questions</h3><ul className="list-disc pl-5 text-sm">{v.content.clarification_questions.map((c, i) => <li key={i}>{c.text}</li>)}</ul></section>
          )}
          <p className="text-xs text-slate-500">{v.content.disclaimer}</p>
          {can(me.data, "summary.approve") && s.status === "draft" && (
            <div className="space-y-2 border-t pt-3">
              <label className="block text-sm"><input type="checkbox" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} /> I have reviewed this draft against its cited sources and approve version {v.version_number} for the record.</label>
              <Button disabled={!confirm || approve.isPending} onClick={() => approve.mutate(v.version_number)}>Approve version {v.version_number}</Button>
              {approve.error && <Alert tone="danger">{(approve.error as Error).message}</Alert>}
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
