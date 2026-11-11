"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Badge, Card, QueryState } from "@/components/ui/primitives";
import { can, useMe } from "@/features/auth/use-me";
import { DocumentsPanel } from "@/features/documents/documents-panel";
import { IntakePanel } from "@/features/intake/intake-panel";
import { SummaryPanel } from "@/features/summaries/summary-panel";
import { api, type Encounter, type TriageEvent } from "@/lib/api";

const TABS = ["intake", "documents", "summary", "red flags"] as const;

function RedFlags({ encounterId }: { encounterId: string }) {
  const me = useMe();
  const qc = useQueryClient();
  const events = useQuery({ queryKey: ["triage", encounterId], queryFn: () => api<TriageEvent[]>(`/triage/events?encounter_id=${encounterId}`), enabled: can(me.data, "triage.read") });
  const act = useMutation({
    mutationFn: ({ id, action }: { id: string; action: string }) =>
      api(`/triage/events/${id}/transition`, { method: "POST", body: { action, ...(action === "resolve" ? { resolution_code: "addressed_in_consultation" } : {}) } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["triage", encounterId] }),
  });
  if (!can(me.data, "triage.read")) return <p className="text-sm">Your role cannot view red flags.</p>;
  return (
    <QueryState isLoading={events.isLoading} error={events.error || act.error} empty={events.data?.length === 0}>
      <ul className="space-y-2">
        {events.data?.map((e) => (
          <li key={e.id}>
            <Card className="flex flex-wrap items-center gap-2 text-sm">
              <Badge tone="danger">{e.severity}</Badge>{e.is_demo_rule && <Badge tone="warn">demo rule · not clinically validated</Badge>}
              <Badge>{e.status}</Badge><span>{e.reason}</span>
              {can(me.data, "triage.acknowledge") && e.status !== "resolved" && (
                <span className="ml-auto flex gap-1">
                  {e.status === "open" && <Button size="sm" variant="outline" onClick={() => act.mutate({ id: e.id, action: "acknowledge" })}>Acknowledge</Button>}
                  {e.status !== "escalated" && <Button size="sm" variant="outline" onClick={() => act.mutate({ id: e.id, action: "escalate" })}>Escalate</Button>}
                  <Button size="sm" onClick={() => act.mutate({ id: e.id, action: "resolve" })}>Resolve</Button>
                </span>
              )}
            </Card>
          </li>
        ))}
      </ul>
    </QueryState>
  );
}

export default function EncounterPage() {
  const { id } = useParams<{ id: string }>();
  const [tab, setTab] = useState<(typeof TABS)[number]>("intake");
  const enc = useQuery({ queryKey: ["encounter", id], queryFn: () => api<Encounter>(`/encounters/${id}`) });
  return (
    <QueryState isLoading={enc.isLoading} error={enc.error}>
      {enc.data && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <Link href={`/patients/${enc.data.patient_id}`} className="text-sm text-brand-700 underline">← Patient</Link>
            <h1 className="text-xl font-semibold">Encounter {new Date(enc.data.started_at).toLocaleString()}</h1>
            <Badge>{enc.data.status}</Badge>
          </div>
          <div role="tablist" aria-label="Encounter sections" className="flex gap-2 border-b">
            {TABS.map((t) => (
              <button key={t} role="tab" aria-selected={tab === t} aria-controls={`panel-${t}`} id={`tab-${t}`} onClick={() => setTab(t)}
                className={`px-3 py-2 text-sm capitalize ${tab === t ? "border-b-2 border-brand-600 font-semibold" : "text-slate-600"}`}>
                {t}
              </button>
            ))}
          </div>
          <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
            {tab === "intake" && <IntakePanel encounterId={id} />}
            {tab === "documents" && <DocumentsPanel encounterId={id} />}
            {tab === "summary" && <SummaryPanel encounterId={id} />}
            {tab === "red flags" && <RedFlags encounterId={id} />}
          </div>
        </div>
      )}
    </QueryState>
  );
}
