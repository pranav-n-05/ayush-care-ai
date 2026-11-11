import { Badge } from "@/components/ui/primitives";
import type { Claim } from "@/lib/api";

export const PROVENANCE_LABEL: Record<string, { label: string; tone: "info" | "ok" | "neutral" | "warn" }> = {
  patient_reported: { label: "Patient-reported", tone: "neutral" },
  practitioner_observed: { label: "Practitioner-observed", tone: "info" },
  document_verified: { label: "Verified document", tone: "ok" },
  practitioner_authored: { label: "Practitioner-authored", tone: "info" },
};

export function ClaimList({ claims }: { claims: Claim[] }) {
  if (claims.length === 0) return <p className="text-sm text-slate-500">No sourced information.</p>;
  return (
    <ul className="space-y-1">
      {claims.map((c, i) => {
        const p = PROVENANCE_LABEL[c.provenance] ?? { label: c.provenance, tone: "neutral" as const };
        return (
          <li key={i} className="text-sm">
            <Badge tone={p.tone}>{p.label}</Badge>{" "}
            {c.certainty === "uncertain" && <Badge tone="warn">uncertain</Badge>} {c.text}{" "}
            <span className="text-xs text-slate-500" title={c.source_refs.map((r) => `${r.kind}:${r.id}@${r.revision}`).join("\n")}>
              [{c.source_refs.length} source{c.source_refs.length === 1 ? "" : "s"}]
            </span>
          </li>
        );
      })}
    </ul>
  );
}
