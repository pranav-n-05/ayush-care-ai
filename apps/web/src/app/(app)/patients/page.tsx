"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Alert, Card, Input, Label, QueryState } from "@/components/ui/primitives";
import { can, useMe } from "@/features/auth/use-me";
import { PatientForm } from "@/features/patients/patient-form";
import { api, type Duplicate, type Page, type Patient, type PatientListItem } from "@/lib/api";

export default function PatientsPage() {
  const me = useMe();
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);
  const [creating, setCreating] = useState(false);
  const [created, setCreated] = useState<{ p: Patient; dups: Duplicate[] } | null>(null);
  const list = useQuery({
    queryKey: ["patients", q, offset],
    queryFn: () => api<Page<PatientListItem>>(`/patients?${new URLSearchParams({ q, offset: String(offset), limit: "20" })}`),
    enabled: can(me.data, "patient.read"),
  });
  if (!can(me.data, "patient.read")) return <p className="text-sm">Your role cannot view patients.</p>;
  return (
    <section aria-labelledby="pt-title" className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 id="pt-title" className="text-xl font-semibold">Patients</h1>
        {can(me.data, "patient.create") && <Button onClick={() => setCreating((v) => !v)}>{creating ? "Close" : "Register patient"}</Button>}
      </div>
      {creating && (
        <Card>
          <PatientForm
            onCreated={(p, dups) => {
              setCreated({ p, dups });
              setCreating(false);
              qc.invalidateQueries({ queryKey: ["patients"] });
            }}
          />
        </Card>
      )}
      {created && (
        <Alert tone={created.dups.length ? "warn" : "ok"}>
          Registered {created.p.record_number}.{" "}
          {created.dups.length > 0 &&
            `Possible duplicates for human review (never merged automatically): ${created.dups.map((d) => `${d.record_number} (${d.match_reasons.join(", ")})`).join("; ")}`}
        </Alert>
      )}
      <form role="search" onSubmit={(e) => { e.preventDefault(); setOffset(0); }} className="max-w-sm">
        <Label htmlFor="search">Search by name, record number or phone</Label>
        <Input id="search" value={q} onChange={(e) => { setQ(e.target.value); setOffset(0); }} />
      </form>
      <QueryState isLoading={list.isLoading} error={list.error} empty={list.data?.items.length === 0}>
        <table className="w-full overflow-hidden rounded-lg bg-white text-sm shadow-sm">
          <thead className="bg-slate-100 text-left"><tr><th className="p-2">Record</th><th className="p-2">Name</th><th className="p-2">Birth / age</th><th className="p-2">Sex</th><th className="p-2">Language</th></tr></thead>
          <tbody>
            {list.data?.items.map((p) => (
              <tr key={p.id} className="border-t">
                <td className="p-2 font-mono"><Link className="text-brand-700 underline" href={`/patients/${p.id}`}>{p.record_number}</Link></td>
                <td className="p-2">{p.given_name} {p.family_name}</td>
                <td className="p-2">{p.birth_date ?? `~${p.age_years} y (estimated)`}</td>
                <td className="p-2">{p.sex_for_clinical_use}</td>
                <td className="p-2">{p.preferred_language}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 20))}>Previous</Button>
          <Button variant="outline" size="sm" disabled={!list.data || offset + 20 >= list.data.total} onClick={() => setOffset(offset + 20)}>Next</Button>
          <span className="text-xs text-slate-500">{list.data?.total ?? 0} total</span>
        </div>
      </QueryState>
    </section>
  );
}
