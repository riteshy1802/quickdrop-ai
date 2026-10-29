"use client";
import { createContext, useContext, useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { opsAuth } from "@/lib/api/auth";
import { useOpsEvents } from "@/hooks/realtime/use-events";
import type { LoginInput, OpsUser } from "@/types/ops";
interface Auth {
  user: OpsUser | null;
  loading: boolean;
  error: string | null;
  login: (input: LoginInput) => Promise<void>;
  logout: () => Promise<void>;
}
const AuthContext = createContext<Auth | null>(null);
export function OpsAuthProvider({ children }: { children: React.ReactNode }) {
  const client = useQueryClient(),
    router = useRouter();
  const session = useQuery({
    queryKey: ["ops-auth"],
    queryFn: () => opsAuth.me(),
    retry: false,
    staleTime: 30000,
    refetchInterval: 60000,
  });
  useOpsEvents(!!session.data);
  useEffect(() => {
    const expire = () => {
      client.setQueryData(["ops-auth"], null);
      client.removeQueries({ queryKey: ["ops-data"] });
    };
    window.addEventListener("quickdrop:session-expired", expire);
    return () =>
      window.removeEventListener("quickdrop:session-expired", expire);
  }, [client]);
  const login = useMutation({
    mutationFn: opsAuth.login,
    onSuccess: (user) => {
      client.setQueryData(["ops-auth"], user);
      router.replace("/ops");
    },
  });
  const logout = useMutation({
    mutationFn: opsAuth.logout,
    onSuccess: () => {
      client.setQueryData(["ops-auth"], null);
      client.removeQueries({ queryKey: ["ops-data"] });
      router.replace("/ops/login");
    },
  });
  return (
    <AuthContext.Provider
      value={{
        user: session.data ?? null,
        loading: session.isPending,
        error: session.error?.message ?? null,
        login: async (input) => {
          await login.mutateAsync(input);
        },
        logout: async () => {
          await logout.mutateAsync();
        },
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}
export function useOpsAuth() {
  const auth = useContext(AuthContext);
  if (!auth) throw new Error("Ops authentication provider missing.");
  return auth;
}
export function RequireOps({ children }: { children: React.ReactNode }) {
  const { user, loading, error } = useOpsAuth(),
    router = useRouter();
  useEffect(() => {
    if (!loading && !user && !error) router.replace("/ops/login");
  }, [loading, user, error, router]);
  if (error)
    return (
      <div className="ops-auth-loading" role="alert">
        {error}
      </div>
    );
  if (loading || !user)
    return (
      <div className="ops-auth-loading" role="status">
        Opening operations workspace…
      </div>
    );
  return children;
}
