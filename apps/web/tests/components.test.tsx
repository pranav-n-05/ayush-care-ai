import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { LoginForm } from "@/app/login/page";
import { QueryState } from "@/components/ui/primitives";
import { QuestionField } from "@/features/intake/question-field";
import { ClaimList } from "@/features/summaries/claim-list";
import type { Question } from "@/lib/api";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

const q = (over: Partial<Question> = {}): Question => ({
  code: "has_allergies", section: "history", type: "boolean", respondent: "patient", required: true,
  text: "Do you have any known allergies?", text_is_fallback: false, help: null, options: null, min: null, max: null,
  unit: null, visible: true, state: "unanswered", current_answer: null, ...over,
});

describe("QuestionField", () => {
  it("distinguishes an explicit 'no' from 'unknown'", async () => {
    const onSave = vi.fn();
    render(<QuestionField q={q()} onSave={onSave} />);
    await userEvent.click(screen.getByRole("button", { name: "No" }));
    await userEvent.click(screen.getByRole("button", { name: "Unknown" }));
    expect(onSave.mock.calls[0]![0]).toMatchObject({ answer_status: "answered", value: false });
    expect(onSave.mock.calls[1]![0]).toMatchObject({ answer_status: "unknown", value: null });
  });

  it("flags missing translations and practitioner fields", () => {
    render(<QuestionField q={q({ respondent: "practitioner", text_is_fallback: true })} onSave={() => {}} />);
    expect(screen.getByText(/translation missing/)).toBeInTheDocument();
    expect(screen.getByText("practitioner observation")).toBeInTheDocument();
  });

  it("normalizes durations and requires reason after submission", async () => {
    const onSave = vi.fn();
    render(<QuestionField q={q({ code: "complaint_duration", type: "duration" })} onSave={onSave} needsReason />);
    await userEvent.type(screen.getByLabelText("Amount"), "3");
    await userEvent.type(screen.getByLabelText(/Change reason/), "Clarified");
    await userEvent.click(screen.getByRole("button", { name: "Save answer" }));
    expect(onSave.mock.calls[0]![0]).toEqual({ question_code: "complaint_duration", answer_status: "answered", value: { amount: 3, unit: "days" }, change_reason: "Clarified" });
  });
});

describe("ClaimList", () => {
  it("labels provenance, uncertainty and citations", () => {
    render(<ClaimList claims={[
      { text: "Patient reports knee pain", provenance: "patient_reported", certainty: "stated", source_refs: [{ kind: "intake_answer", id: "a", revision: 1 }] },
      { text: "Verified document states: allergy", provenance: "document_verified", certainty: "uncertain", source_refs: [] },
    ]} />);
    expect(screen.getByText("Patient-reported")).toBeInTheDocument();
    expect(screen.getByText("Verified document")).toBeInTheDocument();
    expect(screen.getByText("uncertain")).toBeInTheDocument();
    expect(screen.getByText("[1 source]")).toBeInTheDocument();
  });
});

describe("LoginForm", () => {
  it("shows accessible validation errors without calling the API", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<LoginForm onSuccess={() => {}} />);
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Enter your email")).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toHaveAttribute("aria-invalid", "true");
    expect(fetchMock).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it("surfaces the server's generic login error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: { code: "invalid_credentials", message: "Invalid email or password" } }), { status: 401 })));
    render(<LoginForm onSuccess={() => {}} />);
    await userEvent.type(screen.getByLabelText("Email"), "a@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "x");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid email or password");
    vi.unstubAllGlobals();
  });
});

describe("QueryState", () => {
  it("renders loading, error and empty states", () => {
    const { rerender } = render(<QueryState isLoading error={null}>x</QueryState>);
    expect(screen.getByRole("status")).toHaveTextContent("Loading");
    rerender(<QueryState isLoading={false} error={new Error("boom")}>x</QueryState>);
    expect(screen.getByRole("alert")).toHaveTextContent("boom");
    rerender(<QueryState isLoading={false} error={null} empty>x</QueryState>);
    expect(screen.getByText("Nothing here yet.")).toBeInTheDocument();
  });
});
