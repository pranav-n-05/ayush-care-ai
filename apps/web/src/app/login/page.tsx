"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { Button } from "@/components/ui/button";
import { Alert, Card, FieldError, Input, Label } from "@/components/ui/primitives";
import { api, ApiError } from "@/lib/api";
import { loginSchema, type LoginInput } from "@/lib/schemas";

export function LoginForm({ onSuccess }: { onSuccess: () => void }) {
  const [error, setError] = useState<string | null>(null);
  const { register, handleSubmit, formState } = useForm<LoginInput>({ resolver: zodResolver(loginSchema) });
  const onSubmit = handleSubmit(async (values) => {
    setError(null);
    try {
      await api("/auth/login", { method: "POST", body: values });
      onSuccess();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Unable to sign in");
    }
  });
  return (
    <form onSubmit={onSubmit} noValidate className="space-y-4" aria-label="Sign in">
      {error && <Alert tone="danger">{error}</Alert>}
      <div>
        <Label htmlFor="email">Email</Label>
        <Input id="email" type="email" autoComplete="username" aria-invalid={!!formState.errors.email} aria-describedby="email-error" {...register("email")} />
        <FieldError id="email-error" message={formState.errors.email?.message} />
      </div>
      <div>
        <Label htmlFor="password">Password</Label>
        <Input id="password" type="password" autoComplete="current-password" aria-invalid={!!formState.errors.password} aria-describedby="password-error" {...register("password")} />
        <FieldError id="password-error" message={formState.errors.password?.message} />
      </div>
      <Button type="submit" className="w-full" disabled={formState.isSubmitting}>
        {formState.isSubmitting ? "Signing in…" : "Sign in"}
      </Button>
    </form>
  );
}

export default function LoginPage() {
  const router = useRouter();
  const qc = useQueryClient();
  return (
    <main className="mx-auto mt-24 max-w-sm px-4">
      <h1 className="mb-1 text-2xl font-semibold">AyushCare AI</h1>
      <p className="mb-6 text-sm text-slate-600">Synthetic-data portfolio demo. Not for real patients.</p>
      <Card>
        <LoginForm
          onSuccess={async () => {
            await qc.invalidateQueries({ queryKey: ["me"] });
            router.push("/");
          }}
        />
      </Card>
    </main>
  );
}
