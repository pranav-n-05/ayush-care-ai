import { afterEach, describe, expect, it, vi } from "vitest";

import { api, ApiError, readCookie } from "@/lib/api";
import { patientSchema, toPatientPayload } from "@/lib/schemas";

afterEach(() => vi.unstubAllGlobals());

describe("api client", () => {
  it("reads cookies", () => {
    expect(readCookie("ayush_csrf", "a=1; ayush_csrf=tok%3D; b=2")).toBe("tok=");
    expect(readCookie("missing", "a=1")).toBeNull();
  });

  it("sends CSRF header only on unsafe requests and never uses localStorage", async () => {
    document.cookie = "ayush_csrf=csrf-123";
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    await api("/patients");
    await api("/patients", { method: "POST", body: { a: 1 } });
    expect(fetchMock.mock.calls[0]![1].headers["X-CSRF-Token"]).toBeUndefined();
    expect(fetchMock.mock.calls[1]![1].headers["X-CSRF-Token"]).toBe("csrf-123");
    expect(fetchMock.mock.calls[1]![1].credentials).toBe("same-origin");
    expect(setItem).not.toHaveBeenCalled();
  });

  it("maps the backend error envelope", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: { code: "stale_version", message: "Reload" } }), { status: 409 })));
    await expect(api("/x", { method: "PUT", body: {} })).rejects.toMatchObject({ status: 409, code: "stale_version", message: "Reload" });
    expect(new ApiError(1, "c", "m")).toBeInstanceOf(Error);
  });
});

describe("patient form schema", () => {
  const base = { given_name: "Kavya", family_name: "", dob_mode: "age", birth_date: "", age_years: "40", sex_for_clinical_use: "female", phone: "", preferred_language: "ta", consent_data_processing: true, consent_ai: true, consent_reminders: false } as const;

  it("requires age when birth date is unknown and records estimate", () => {
    expect(patientSchema.safeParse({ ...base, age_years: "" }).success).toBe(false);
    const parsed = patientSchema.parse(base);
    const payload = toPatientPayload(parsed);
    expect(payload).toMatchObject({ age_years: 40, phone: null });
    expect(payload).not.toHaveProperty("birth_date");
    expect(payload.consents.map((c) => c.consent_type)).toEqual(["data_processing", "ai_assisted_documentation"]);
  });

  it("rejects malformed phone numbers", () => {
    expect(patientSchema.safeParse({ ...base, phone: "12ab" }).success).toBe(false);
  });
});
