"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Alert, Badge, Card, Input, Label, QueryState, Select } from "@/components/ui/primitives";
import { can, useMe } from "@/features/auth/use-me";
import { api, idempotencyKey, type DocumentInfo, type Entity, type Job } from "@/lib/api";

function EntityRow({ e, documentId }: { e: Entity; documentId: string }) {
  const qc = useQueryClient();
  const [text, setText] = useState(e.text);
  const review = useMutation({
    mutationFn: (body: object) => api<Entity>(`/extracted-entities/${e.id}/review`, { method: "POST", body: { expected_revision: e.revision, ...body } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["entities", documentId] }),
  });
  const tone = e.verification_status === "unverified" ? "warn" : e.verification_status === "rejected" ? "danger" : "ok";
  return (
    <li className="flex flex-wrap items-center gap-2 border-t py-2 text-sm">
      <Badge>{e.entity_type}</Badge>
      <Badge tone={tone}>{e.verification_status}</Badge>
      <span className="text-xs text-slate-500">page {e.page} line {e.line} · confidence {e.confidence ?? "not reported"}</span>
      <Input aria-label={`Value for ${e.entity_type}`} className="max-w-md" value={text} onChange={(ev) => setText(ev.target.value)} />
      <Button size="sm" onClick={() => review.mutate({ action: "verify" })} disabled={text !== e.text}>Verify</Button>
      <Button size="sm" variant="outline" onClick={() => review.mutate({ action: "correct", corrected_text: text })} disabled={text === e.text}>Save correction</Button>
      <Button size="sm" variant="ghost" onClick={() => review.mutate({ action: "reject" })}>Reject</Button>
      {review.error && <span className="text-xs text-red-600">{(review.error as Error).message}</span>}
    </li>
  );
}

function DocumentCard({ d }: { d: DocumentInfo }) {
  const me = useMe();
  const qc = useQueryClient();
  const [job, setJob] = useState<Job | null>(null);
  const process = useMutation({
    mutationFn: () => api<Job>(`/documents/${d.id}/process`, { method: "POST", headers: { "Idempotency-Key": idempotencyKey() } }),
    onSuccess: setJob,
  });
  const jobStatus = useQuery({
    queryKey: ["ocr-job", job?.id],
    queryFn: async () => {
      const j = await api<Job>(`/ocr-jobs/${job?.id}`);
      if (j.status === "succeeded") qc.invalidateQueries({ queryKey: ["entities", d.id] });
      return j;
    },
    enabled: !!job,
    refetchInterval: (q) => (q.state.data && ["succeeded", "failed"].includes(q.state.data.status) ? false : 2000),
  });
  const entities = useQuery({ queryKey: ["entities", d.id], queryFn: () => api<Entity[]>(`/documents/${d.id}/entities`) });
  const status = jobStatus.data ?? job;
  return (
    <Card>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <strong>{d.display_filename}</strong><Badge>{d.document_type}</Badge><Badge tone="info">{d.scan_status.replaceAll("_", " ")}</Badge>
        {can(me.data, "document.download") && <a className="text-brand-700 underline" href={`/api/v1/documents/${d.id}/content`}>Download</a>}
        {can(me.data, "ocr.process") && <Button size="sm" variant="outline" onClick={() => process.mutate()} disabled={process.isPending}>Run OCR</Button>}
        {status && <Badge tone={status.status === "failed" ? "danger" : "neutral"}>OCR {status.status}</Badge>}
      </div>
      {status?.failure_reason && <Alert tone="danger" className="mt-2">{status.failure_reason}</Alert>}
      {entities.data && entities.data.length > 0 && (
        <>
          <p className="mt-2 text-xs text-amber-800">Extracted fields are unverified until reviewed. Only verified/corrected fields are used in AI drafts.</p>
          <ul>{entities.data.map((e) => <EntityRow key={e.id} e={e} documentId={d.id} />)}</ul>
        </>
      )}
    </Card>
  );
}

export function DocumentsPanel({ encounterId }: { encounterId: string }) {
  const me = useMe();
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [type, setType] = useState("prescription");
  const docs = useQuery({ queryKey: ["docs", encounterId], queryFn: () => api<DocumentInfo[]>(`/encounters/${encounterId}/documents`), enabled: can(me.data, "document.read") });
  const upload = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      form.append("document_type", type);
      return api<DocumentInfo>(`/encounters/${encounterId}/documents`, { method: "POST", form });
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["docs", encounterId] }); if (fileRef.current) fileRef.current.value = ""; },
  });
  return (
    <div className="space-y-3">
      {can(me.data, "document.upload") && (
        <Card className="flex flex-wrap items-end gap-3">
          <div>
            <Label htmlFor="doctype">Document type</Label>
            <Select id="doctype" value={type} onChange={(e) => setType(e.target.value)}>
              {["prescription", "lab_report", "prior_note", "discharge_summary", "other"].map((t) => <option key={t} value={t}>{t.replace("_", " ")}</option>)}
            </Select>
          </div>
          <div>
            <Label htmlFor="file">File (pdf, png, jpg, txt · synthetic only)</Label>
            <input id="file" ref={fileRef} type="file" accept=".pdf,.png,.jpg,.jpeg,.txt" className="text-sm" onChange={(e) => e.target.files?.[0] && upload.mutate(e.target.files[0])} />
          </div>
          {upload.error && <Alert tone="danger">{(upload.error as Error).message}</Alert>}
        </Card>
      )}
      {can(me.data, "document.read") ? (
        <QueryState isLoading={docs.isLoading} error={docs.error} empty={docs.data?.length === 0}>
          {docs.data?.map((d) => <DocumentCard key={d.id} d={d} />)}
        </QueryState>
      ) : (
        <p className="text-sm">Your role can upload but not view documents.</p>
      )}
    </div>
  );
}
