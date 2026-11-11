"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Badge, Input, Select, Textarea } from "@/components/ui/primitives";
import type { AnswerStatus, Question } from "@/lib/api";

export type AnswerDraft = { question_code: string; answer_status: AnswerStatus; value: unknown; change_reason?: string };

const STATE_TONE: Record<string, "neutral" | "ok" | "warn" | "info"> = {
  answered: "ok", unknown: "warn", declined: "warn", not_applicable: "info", unanswered: "neutral",
};

function initial(q: Question): unknown {
  const v = q.current_answer?.answer_status === "answered" ? q.current_answer.value : undefined;
  if (v !== undefined) return v;
  if (q.type === "multi_choice") return [];
  if (q.type === "duration") return { amount: "", unit: "days" };
  return "";
}

/** One question with an explicit status choice. Leaving a question blank is never treated as
 * a negative answer: staff choose "unknown", "declined" or "not applicable" explicitly. */
export function QuestionField({ q, onSave, disabled, needsReason }: { q: Question; onSave: (a: AnswerDraft) => void; disabled?: boolean; needsReason?: boolean }) {
  const [value, setValue] = useState<unknown>(initial(q));
  const [reason, setReason] = useState("");
  const id = `q-${q.code}`;
  const save = (answer_status: AnswerStatus, v: unknown = null) =>
    onSave({ question_code: q.code, answer_status, value: answer_status === "answered" ? normalize(q, v) : null, ...(needsReason ? { change_reason: reason } : {}) });

  let control: React.ReactNode;
  switch (q.type) {
    case "boolean":
      control = (
        <div className="flex gap-2" role="group" aria-labelledby={`${id}-label`}>
          <Button size="sm" variant={value === true ? "default" : "outline"} disabled={disabled} onClick={() => { setValue(true); save("answered", true); }}>Yes</Button>
          <Button size="sm" variant={value === false ? "default" : "outline"} disabled={disabled} onClick={() => { setValue(false); save("answered", false); }}>No</Button>
        </div>
      );
      break;
    case "single_choice":
      control = (
        <Select id={id} value={String(value)} disabled={disabled} onChange={(e) => setValue(e.target.value)}>
          <option value="">Select…</option>
          {q.options?.map((o) => <option key={o.code} value={o.code}>{o.label}</option>)}
        </Select>
      );
      break;
    case "multi_choice":
      control = (
        <div className="flex flex-wrap gap-3" role="group" aria-labelledby={`${id}-label`}>
          {q.options?.map((o) => {
            const list = (value as string[]) ?? [];
            return (
              <label key={o.code} className="text-sm">
                <input type="checkbox" disabled={disabled} checked={list.includes(o.code)} onChange={(e) => setValue(e.target.checked ? [...list, o.code] : list.filter((x) => x !== o.code))} /> {o.label}
              </label>
            );
          })}
        </div>
      );
      break;
    case "number":
      control = <Input id={id} type="number" min={q.min ?? undefined} max={q.max ?? undefined} disabled={disabled} value={String(value)} onChange={(e) => setValue(e.target.value)} />;
      break;
    case "duration": {
      const d = value as { amount: string | number; unit: string };
      control = (
        <div className="flex gap-2">
          <Input id={id} type="number" min={0} aria-label="Amount" disabled={disabled} value={String(d.amount)} onChange={(e) => setValue({ ...d, amount: e.target.value })} />
          <Select aria-label="Unit" disabled={disabled} value={d.unit} onChange={(e) => setValue({ ...d, unit: e.target.value })}>
            {["days", "weeks", "months", "years"].map((u) => <option key={u}>{u}</option>)}
          </Select>
        </div>
      );
      break;
    }
    case "long_text":
      control = <Textarea id={id} disabled={disabled} value={String(value)} onChange={(e) => setValue(e.target.value)} />;
      break;
    default:
      control = <Input id={id} type={q.type === "date" ? "date" : "text"} disabled={disabled} value={String(value)} onChange={(e) => setValue(e.target.value)} />;
  }

  return (
    <div className="rounded-md border border-slate-200 p-3" data-testid={`question-${q.code}`}>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <label id={`${id}-label`} htmlFor={id} className="text-sm font-medium">
          {q.text}{q.required && <span aria-label="required" className="text-red-600"> *</span>}
        </label>
        <Badge tone={STATE_TONE[q.state] ?? "neutral"}>{q.state.replace("_", " ")}</Badge>
        {q.respondent === "practitioner" && <Badge tone="info">practitioner observation</Badge>}
        {q.text_is_fallback && <Badge tone="warn">shown in English (translation missing)</Badge>}
        {q.current_answer && q.current_answer.translation_status !== "not_required" && <Badge tone="warn">translation: {q.current_answer.translation_status.replaceAll("_", " ")}</Badge>}
        {q.current_answer && q.current_answer.revision > 1 && <Badge>rev {q.current_answer.revision}</Badge>}
      </div>
      {q.help && <p className="mb-2 text-xs text-slate-500">{q.help}</p>}
      {control}
      {needsReason && <Input aria-label={`Change reason for ${q.code}`} placeholder="Reason for change (required after submission)" className="mt-2" value={reason} onChange={(e) => setReason(e.target.value)} />}
      <div className="mt-2 flex flex-wrap gap-2">
        {q.type !== "boolean" && <Button size="sm" disabled={disabled} onClick={() => save("answered", value)}>Save answer</Button>}
        <Button size="sm" variant="outline" disabled={disabled} onClick={() => save("unknown")}>Unknown</Button>
        <Button size="sm" variant="outline" disabled={disabled} onClick={() => save("declined")}>Declined</Button>
        <Button size="sm" variant="ghost" disabled={disabled} onClick={() => save("not_applicable")}>Not applicable</Button>
      </div>
    </div>
  );
}

export function normalize(q: Question, v: unknown): unknown {
  if (q.type === "number") return v === "" ? null : Number(v);
  if (q.type === "duration") {
    const d = v as { amount: string | number; unit: string };
    return { amount: Number(d.amount), unit: d.unit };
  }
  return v;
}
