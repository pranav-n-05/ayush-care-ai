"use client";

import { useQuery } from "@tanstack/react-query";

import { api, type Me } from "@/lib/api";

export function useMe() {
  return useQuery({ queryKey: ["me"], queryFn: () => api<Me>("/users/me"), retry: false });
}

export function can(me: Me | undefined, permission: string): boolean {
  return Boolean(me?.permissions.includes(permission));
}
