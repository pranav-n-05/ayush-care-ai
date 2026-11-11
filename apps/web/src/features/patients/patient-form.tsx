"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";

import { Button } from "@/components/ui/button";
import { Alert, FieldError, Input, Label, Select } from "@/components/ui/primitives";
import { api, ApiError, type Duplicate, type Patient } from "@/lib/api";
import { patientSchema, toPatientPayload, type PatientFormInput } from "@/lib/schemas";

export function PatientForm({ onCreated }: { onCreated: (p: Patient, dups: Duplicate[]) => void }) {
  const [error, setError] = useState<string | null>(null);
  const { register, handleSubmit, control, formState } = useForm<PatientFormInput>({
    resolver: zodResolver(patientSchema),
    defaultValues: {
      given_name: "", family_name: "", dob_mode: "birth_date", birth_date: "", age_years: "",
      sex_for_clinical_use: "unknown", phone: "", preferred_language: "en",
      consent_data_processing: true, consent_ai: false, consent_reminders: false,
    },
  });
  const mode = useWatch({ control, name: "dob_mode" });
  const e = formState.errors;
  const onSubmit = handleSubmit(async (values) => {
    setError(null);
    try {
      const r = await api<{ patient: Patient; possible_duplicates: Duplicate[] }>("/patients", { method: "POST", body: toPatientPayload(values) });
      onCreated(r.patient, r.possible_duplicates);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not register patient");
    }
  });
  return (
    <form onSubmit={onSubmit} noValidate className="grid grid-cols-1 gap-3 md:grid-cols-2" aria-label="Register patient">
      {error && <Alert tone="danger" className="md:col-span-2">{error}</Alert>}
      <div>
        <Label htmlFor="given_name">Given name</Label>
        <Input id="given_name" aria-invalid={!!e.given_name} {...register("given_name")} />
        <FieldError message={e.given_name?.message} />
      </div>
      <div>
        <Label htmlFor="family_name">Family name</Label>
        <Input id="family_name" {...register("family_name")} />
      </div>
      <fieldset className="md:col-span-2">
        <legend className="mb-1 text-sm font-medium text-slate-700">Birth information</legend>
        <label className="mr-4 text-sm"><input type="radio" value="birth_date" {...register("dob_mode")} /> Date of birth</label>
        <label className="text-sm"><input type="radio" value="age" {...register("dob_mode")} /> Age only (recorded today, estimated)</label>
      </fieldset>
      {mode === "birth_date" ? (
        <div>
          <Label htmlFor="birth_date">Date of birth</Label>
          <Input id="birth_date" type="date" aria-invalid={!!e.birth_date} {...register("birth_date")} />
          <FieldError message={e.birth_date?.message} />
        </div>
      ) : (
        <div>
          <Label htmlFor="age_years">Age (years)</Label>
          <Input id="age_years" inputMode="numeric" aria-invalid={!!e.age_years} {...register("age_years")} />
          <FieldError message={e.age_years?.message} />
        </div>
      )}
      <div>
        <Label htmlFor="sex">Sex (clinically relevant)</Label>
        <Select id="sex" {...register("sex_for_clinical_use")}>
          <option value="female">Female</option>
          <option value="male">Male</option>
          <option value="intersex">Intersex</option>
          <option value="unknown">Unknown</option>
        </Select>
      </div>
      <div>
        <Label htmlFor="phone">Phone</Label>
        <Input id="phone" inputMode="tel" aria-invalid={!!e.phone} {...register("phone")} />
        <FieldError message={e.phone?.message} />
      </div>
      <div>
        <Label htmlFor="lang">Preferred language</Label>
        <Select id="lang" {...register("preferred_language")}>
          <option value="en">English</option>
          <option value="hi">हिन्दी (Hindi)</option>
          <option value="ta">தமிழ் (Tamil)</option>
        </Select>
      </div>
      <fieldset className="space-y-1 text-sm md:col-span-2">
        <legend className="mb-1 font-medium text-slate-700">Consent recorded (verbal)</legend>
        <label className="block"><input type="checkbox" {...register("consent_data_processing")} /> Data processing for care</label>
        <label className="block"><input type="checkbox" {...register("consent_ai")} /> AI-assisted documentation drafts</label>
        <label className="block"><input type="checkbox" {...register("consent_reminders")} /> Follow-up reminders</label>
      </fieldset>
      <div className="md:col-span-2">
        <Button type="submit" disabled={formState.isSubmitting}>{formState.isSubmitting ? "Saving…" : "Register patient"}</Button>
      </div>
    </form>
  );
}
