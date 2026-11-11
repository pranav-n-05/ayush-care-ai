"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Badge, Card, QueryState } from "@/components/ui/primitives";
import { can, useMe } from "@/features/auth/use-me";
import { api, type Consent, type Encounter, type Patient, type TimelineItem } from "@/lib/api";

export default function PatientDetailPage() {
  const { id } = useParams<{ id: string }>();
  const me = useMe();
  const qc = useQueryClient();
  const router = useRouter();
  const patient = useQuery({ queryKey: ["patient", id], queryFn: () => api<Patient>(`/patients/${id}`) });
  const consents = useQuery({ queryKey: ["consents", id], queryFn: () => api<Consent[]>(`/patients/${id}/consents`) });
  const timeline = useQuery({ queryKey: ["timeline", id], queryFn: () => api<TimelineItem[]>(`/patients/${id}/timeline`), enabled: can(me.data, "encounter.read") });
  const createEnc = useMutation({
    mutationFn: () => api<Encounter>(`/patients/${id}/encounters`, { method: "POST", body: {} }),
    onSuccess: (e) => {
      qc.invalidateQueries({ queryKey: ["timeline", id] });
      router.push(`/encounters/${e.id}`);
    },
  });
  return (
    <QueryState isLoading={patient.isLoading} error={patient.error}>
      {patient.data && (
        <div className="space-y-4">
          <Card>
            <h1 className="text-xl font-semibold">{patient.data.given_name} {patient.data.family_name}</h1>
            <p className="font-mono text-sm text-slate-600">{patient.data.record_number}</p>
            <dl className="mt-2 grid grid-cols-2 gap-1 text-sm md:grid-cols-4">
              <dt className="text-slate-500">Birth</dt><dd>{patient.data.birth_date ?? `~${patient.data.age_years} y`} ({patient.data.birth_date_precision})</dd>
              <dt className="text-slate-500">Sex</dt><dd>{patient.data.sex_for_clinical_use}</dd>
              <dt className="text-slate-500">Phone</dt><dd>{patient.data.phone ?? "—"}</dd>
              <dt className="text-slate-500">Language</dt><dd>{patient.data.preferred_language}</dd>
            </dl>
            <div className="mt-3 flex flex-wrap gap-2" aria-label="Consent status">
              {consents.data?.length === 0 && <Badge tone="warn">No consent recorded</Badge>}
              {consents.data?.map((c) => <Badge key={c.consent_type} tone={c.status === "granted" ? "ok" : "danger"}>{c.consent_type}: {c.status}</Badge>)}
            </div>
          </Card>
          <section aria-labelledby="tl-title">
            <div className="mb-2 flex items-center justify-between">
              <h2 id="tl-title" className="font-semibold">Encounter timeline</h2>
              {can(me.data, "encounter.create") && <Button onClick={() => createEnc.mutate()} disabled={createEnc.isPending}>New encounter</Button>}
            </div>
            <QueryState isLoading={timeline.isLoading} error={timeline.error || createEnc.error} empty={timeline.data?.length === 0}>
              <ol className="space-y-2">
                {timeline.data?.map((t) => (
                  <li key={t.encounter_id}>
                    <Card className="flex flex-wrap items-center gap-3 text-sm">
                      <Link className="text-brand-700 underline" href={`/encounters/${t.encounter_id}`}>{new Date(t.started_at).toLocaleString()}</Link>
                      <Badge>{t.status}</Badge>
                      <span>{t.intake_sessions} intake · {t.documents} documents</span>
                      {t.summary_status && <Badge tone={t.summary_status === "approved" ? "ok" : "warn"}>summary {t.summary_status}{t.approved_version ? ` (v${t.approved_version})` : ""}</Badge>}
                      {t.open_red_flags > 0 && <Badge tone="danger">{t.open_red_flags} open red flag(s)</Badge>}
                    </Card>
                  </li>
                ))}
              </ol>
            </QueryState>
          </section>
        </div>
      )}
    </QueryState>
  );
}
