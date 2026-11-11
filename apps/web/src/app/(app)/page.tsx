"use client";

import { useQuery } from "@tanstack/react-query";

import { Card, QueryState } from "@/components/ui/primitives";
import { can, useMe } from "@/features/auth/use-me";
import { api, type Overview } from "@/lib/api";

const LABELS: Record<string, string> = {
  open_encounters: "Open encounters",
  intake_in_progress: "Intake in progress",
  intake_awaiting_review: "Intake awaiting review",
  unverified_extracted_entities: "Unverified OCR fields",
  ocr_jobs_pending_or_failed: "OCR jobs pending / failed",
  summaries_pending_approval: "Summaries pending approval",
  open_red_flags: "Open red flags",
  follow_ups_due_24h: "Follow-ups due (24h)",
};

export default function DashboardPage() {
  const me = useMe();
  const q = useQuery({ queryKey: ["overview"], queryFn: () => api<Overview>("/dashboard/overview"), enabled: can(me.data, "dashboard.read") });
  if (!can(me.data, "dashboard.read")) return <p className="text-sm text-slate-600">Your role does not include the dashboard.</p>;
  return (
    <section aria-labelledby="dash-title">
      <h1 id="dash-title" className="mb-4 text-xl font-semibold">Dashboard</h1>
      <QueryState isLoading={q.isLoading} error={q.error}>
        <ul className="grid grid-cols-2 gap-4 md:grid-cols-4">
          {q.data?.metrics.map((m) => (
            <li key={m.key}>
              <Card title={m.definition}>
                <p className="text-sm text-slate-600">{LABELS[m.key] ?? m.key}</p>
                <p className="text-3xl font-semibold">{m.value}</p>
              </Card>
            </li>
          ))}
        </ul>
        {!!q.data?.open_red_flags_from_demo_rules && (
          <p className="mt-3 text-xs text-amber-800">
            {q.data.open_red_flags_from_demo_rules} open red flag(s) come from demo rules that are not clinically validated.
          </p>
        )}
      </QueryState>
    </section>
  );
}
