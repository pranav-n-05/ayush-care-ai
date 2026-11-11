"use client";

import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/primitives";
import { useMe } from "@/features/auth/use-me";
import { api, ApiError } from "@/lib/api";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const qc = useQueryClient();
  const me = useMe();
  useEffect(() => {
    if (me.error instanceof ApiError && me.error.status === 401) router.replace("/login");
  }, [me.error, router]);

  if (me.isLoading || (me.error instanceof ApiError && me.error.status === 401)) return <p className="p-6" role="status">Loading…</p>;
  const org = me.data?.memberships.find((m) => m.organization_id === me.data?.active_organization_id);

  return (
    <div>
      <a href="#main" className="sr-only focus:not-sr-only">Skip to content</a>
      <header className="border-b border-slate-200 bg-white">
        <nav className="mx-auto flex max-w-6xl items-center gap-6 px-4 py-3" aria-label="Main">
          <span className="font-semibold text-brand-700">AyushCare AI</span>
          <Link href="/" className="text-sm hover:underline">Dashboard</Link>
          <Link href="/patients" className="text-sm hover:underline">Patients</Link>
          <span className="ml-auto text-xs text-slate-500">
            {me.data?.full_name} · {org?.organization_name ?? "No organization selected"} · {org?.roles.join(", ")}
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={async () => {
              await api("/auth/logout", { method: "POST" }).catch(() => undefined);
              qc.clear();
              router.replace("/login");
            }}
          >
            Sign out
          </Button>
        </nav>
      </header>
      <div className="bg-amber-50 px-4 py-1 text-center text-xs text-amber-900">
        Synthetic data only · AI output is a draft until a practitioner approves it · Not clinically validated
      </div>
      <main id="main" className="mx-auto max-w-6xl px-4 py-6">
        {me.error ? <Alert tone="danger">{(me.error as Error).message}</Alert> : children}
      </main>
    </div>
  );
}
