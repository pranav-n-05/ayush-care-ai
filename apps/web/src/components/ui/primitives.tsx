import * as React from "react";

import { cn } from "@/lib/utils";

export function Input({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn("h-9 w-full rounded-md border border-slate-300 bg-white px-3 text-sm aria-invalid:border-red-500", className)} {...props} />;
}

export function Textarea({ className, ...props }: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={cn("min-h-20 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm", className)} {...props} />;
}

export function Select({ className, ...props }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={cn("h-9 w-full rounded-md border border-slate-300 bg-white px-2 text-sm", className)} {...props} />;
}

export function Label({ className, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) {
  return <label className={cn("mb-1 block text-sm font-medium text-slate-700", className)} {...props} />;
}

export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("rounded-lg border border-slate-200 bg-white p-4 shadow-sm", className)} {...props} />;
}

const tones = {
  neutral: "bg-slate-100 text-slate-700",
  info: "bg-blue-100 text-blue-800",
  warn: "bg-amber-100 text-amber-900",
  danger: "bg-red-100 text-red-800",
  ok: "bg-green-100 text-green-800",
} as const;

export function Badge({ tone = "neutral", className, ...props }: React.HTMLAttributes<HTMLSpanElement> & { tone?: keyof typeof tones }) {
  return <span className={cn("inline-flex items-center rounded px-2 py-0.5 text-xs font-medium", tones[tone], className)} {...props} />;
}

export function Alert({ tone = "info", className, ...props }: React.HTMLAttributes<HTMLDivElement> & { tone?: keyof typeof tones }) {
  return <div role={tone === "danger" ? "alert" : "status"} className={cn("rounded-md px-3 py-2 text-sm", tones[tone], className)} {...props} />;
}

export function FieldError({ message, id }: { message?: string; id?: string }) {
  if (!message) return null;
  return (
    <p id={id} className="mt-1 text-xs text-red-600">
      {message}
    </p>
  );
}

export function QueryState({ isLoading, error, empty, children }: { isLoading: boolean; error: unknown; empty?: boolean; children: React.ReactNode }) {
  if (isLoading) return <p className="text-sm text-slate-500" role="status">Loading…</p>;
  if (error) return <Alert tone="danger">{error instanceof Error ? error.message : "Something went wrong"}</Alert>;
  if (empty) return <p className="text-sm text-slate-500">Nothing here yet.</p>;
  return <>{children}</>;
}
