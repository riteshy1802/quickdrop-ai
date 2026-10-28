"use client";
import { createContext, useContext, useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { mockOpsAuth } from "@/lib/auth/ops-auth";
import type { LoginInput, OpsUser } from "@/types/ops";
interface Auth {
  user: OpsUser | null;
  loading: boolean;
  login: (input: LoginInput) => Promise<void>;
  logout: () => Promise<void>;
}
const AuthContext = createContext<Auth | null>(null);
export function OpsAuthProvider({ children }: { children: React.ReactNode }) {
  const client = useQueryClient(),
    router = useRouter();
  const session = useQuery({
    queryKey: ["ops-auth"],
    queryFn: () => mockOpsAuth.me(),
    retry: false,
    staleTime: Infinity,
  });
  const value: Auth = {
    user: session.data ?? null,
    loading: session.isPending,
    login: async (input) => {
      const user = await mockOpsAuth.login(input);
      client.setQueryData(["ops-auth"], user);
      router.replace("/ops");
    },
    logout: async () => {
      await mockOpsAuth.logout();
      client.setQueryData(["ops-auth"], null);
      client.removeQueries({ queryKey: ["ops-data"] });
      router.replace("/ops/login");
    },
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
export function useOpsAuth() {
  const auth = useContext(AuthContext);
  if (!auth) throw new Error("Ops authentication provider missing.");
  return auth;
}
export function RequireOps({ children }: { children: React.ReactNode }) {
  const { user, loading } = useOpsAuth(),
    router = useRouter();
  useEffect(() => {
    if (!loading && !user) router.replace("/ops/login");
  }, [loading, user, router]);
  if (loading || !user)
    return (
      <div className="ops-auth-loading" role="status">
        Opening demo workspace…
      </div>
    );
  return children;
}
