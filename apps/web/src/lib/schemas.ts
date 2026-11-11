import { z } from "zod";

export const loginSchema = z.object({
  email: z.string().trim().min(3, "Enter your email"),
  password: z.string().min(1, "Enter your password"),
});
export type LoginInput = z.infer<typeof loginSchema>;

const phone = z
  .string()
  .trim()
  .regex(/^\+?[0-9]{7,15}$/, "Use 7–15 digits, optional leading +")
  .or(z.literal(""));

export const patientSchema = z
  .object({
    given_name: z.string().trim().min(1, "Required").max(100),
    family_name: z.string().trim().max(100),
    dob_mode: z.enum(["birth_date", "age"]),
    birth_date: z.string(),
    age_years: z.string(),
    sex_for_clinical_use: z.enum(["female", "male", "intersex", "unknown"]),
    phone,
    preferred_language: z.enum(["en", "hi", "ta"]),
    consent_data_processing: z.boolean(),
    consent_ai: z.boolean(),
    consent_reminders: z.boolean(),
  })
  .superRefine((v, ctx) => {
    if (v.dob_mode === "birth_date" && !/^\d{4}-\d{2}-\d{2}$/.test(v.birth_date))
      ctx.addIssue({ code: "custom", path: ["birth_date"], message: "Enter a date (YYYY-MM-DD)" });
    if (v.dob_mode === "age") {
      const n = Number(v.age_years);
      if (v.age_years.trim() === "" || !Number.isInteger(n) || n < 0 || n > 130) ctx.addIssue({ code: "custom", path: ["age_years"], message: "Age must be 0–130" });
    }
  });
export type PatientFormInput = z.infer<typeof patientSchema>;

export function toPatientPayload(v: PatientFormInput) {
  const today = new Date().toISOString().slice(0, 10);
  const consents = (
    [
      ["data_processing", v.consent_data_processing],
      ["ai_assisted_documentation", v.consent_ai],
      ["contact_reminders", v.consent_reminders],
    ] as const
  )
    .filter(([, granted]) => granted)
    .map(([consent_type]) => ({ consent_type, status: "granted", method: "verbal" }));
  return {
    given_name: v.given_name,
    family_name: v.family_name,
    sex_for_clinical_use: v.sex_for_clinical_use,
    preferred_language: v.preferred_language,
    phone: v.phone || null,
    ...(v.dob_mode === "birth_date"
      ? { birth_date: v.birth_date }
      : { age_years: Number(v.age_years), age_recorded_on: today }),
    consents,
  };
}
