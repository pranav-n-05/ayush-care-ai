/** Typed API client. Session lives in an HttpOnly cookie; the CSRF token comes from the
 * readable `ayush_csrf` cookie and is echoed in X-CSRF-Token on unsafe requests.
 * No credential is ever stored in localStorage. */

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: unknown,
  ) {
    super(message);
  }
}

export function readCookie(name: string, source: string = typeof document === "undefined" ? "" : document.cookie): string | null {
  for (const part of source.split(";")) {
    const [k, ...v] = part.trim().split("=");
    if (k === name) return decodeURIComponent(v.join("="));
  }
  return null;
}

type Options = { method?: string; body?: unknown; headers?: Record<string, string>; form?: FormData };

export async function api<T>(path: string, opts: Options = {}): Promise<T> {
  const method = opts.method ?? "GET";
  const headers: Record<string, string> = { ...(opts.headers ?? {}) };
  if (method !== "GET") {
    const csrf = readCookie("ayush_csrf");
    if (csrf) headers["X-CSRF-Token"] = csrf;
  }
  let body: BodyInit | undefined;
  if (opts.form) body = opts.form;
  else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  const res = await fetch(`/api/v1${path}`, { method, headers, body, credentials: "same-origin", cache: "no-store" });
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const err = data?.error ?? {};
    throw new ApiError(res.status, err.code ?? "unknown_error", err.message ?? `Request failed (${res.status})`, err.details);
  }
  return data as T;
}

export function idempotencyKey(): string {
  return crypto.randomUUID();
}

// ---- contract types (mirror backend Pydantic models) ----
export type Me = {
  id: string;
  email: string;
  full_name: string;
  is_platform_admin: boolean;
  active_organization_id: string | null;
  permissions: string[];
  memberships: { membership_id: string; organization_id: string; organization_name: string; roles: string[] }[];
};
export type Metric = { key: string; value: number; definition: string };
export type Overview = { generated_at: string; metrics: Metric[]; open_red_flags_from_demo_rules: number };
export type PatientListItem = {
  id: string;
  record_number: string;
  given_name: string;
  family_name: string;
  birth_date: string | null;
  age_years: number | null;
  sex_for_clinical_use: string;
  preferred_language: string;
  created_at: string;
};
export type Page<T> = { items: T[]; total: number; limit: number; offset: number };
export type Patient = PatientListItem & { phone: string | null; email: string | null; lock_version: number; birth_date_precision: string };
export type Duplicate = { id: string; record_number: string; match_reasons: string[] };
export type Consent = { consent_type: string; status: string; updated_at: string };
export type Encounter = { id: string; patient_id: string; status: string; visit_reason: string | null; started_at: string };
export type TimelineItem = {
  encounter_id: string;
  started_at: string;
  status: string;
  visit_reason: string | null;
  intake_sessions: number;
  documents: number;
  summary_status: string | null;
  approved_version: number | null;
  open_red_flags: number;
};
export type QuestionnaireVersion = { id: string; title: string; version_number: number; clinical_review_status: string };
export type AnswerStatus = "answered" | "unknown" | "declined" | "not_applicable";
export type Answer = {
  id: string;
  revision: number;
  answer_status: AnswerStatus;
  value: unknown;
  source: string;
  original_language: string;
  translation_status: string;
};
export type Question = {
  code: string;
  section: string;
  type: string;
  respondent: "patient" | "practitioner";
  required: boolean;
  text: string;
  text_is_fallback: boolean;
  help: string | null;
  options: { code: string; label: string }[] | null;
  min: number | null;
  max: number | null;
  unit: string | null;
  visible: boolean;
  state: string;
  current_answer: Answer | null;
};
export type IntakeSession = {
  id: string;
  status: string;
  language: string;
  questionnaire_clinical_review_status: string;
  clinical_disclaimer: string;
  questions: Question[];
  missing_required: string[];
  red_flag_rule_coverage: { severity: string; status: string; outcome: string }[];
};
export type DocumentInfo = {
  id: string;
  document_type: string;
  status: string;
  display_filename: string;
  mime_type: string;
  size_bytes: number;
  scan_status: string;
  created_at: string;
};
export type Job = { id: string; status: string; attempts: number; max_attempts: number; failure_reason: string | null };
export type Entity = {
  id: string;
  revision: number;
  entity_type: string;
  text: string;
  page: number | null;
  line: number | null;
  confidence: number | null;
  verification_status: string;
};
export type SourceRef = { kind: string; id: string; revision: number };
export type Claim = { text: string; provenance: string; certainty: string; source_refs: SourceRef[] };
export type SummaryContent = {
  sections: { code: string; title: string; claims: Claim[] }[];
  missing_information: { question_code: string; state: string }[];
  contradictions: { description: string; source_refs: SourceRef[] }[];
  clarification_questions: { text: string }[];
  disclaimer: string;
};
export type Summary = {
  id: string;
  status: "draft" | "approved";
  current_version_number: number;
  approved_version_number: number | null;
  current_version: { version_number: number; origin: string; content: SummaryContent; provider: string | null; model: string | null; created_at: string } | null;
  approvals: { version_number: number; approved_by_user_id: string; approved_at: string }[];
};
export type TriageEvent = { id: string; severity: string; reason: string; is_demo_rule: boolean; status: string; evaluated_at: string };
