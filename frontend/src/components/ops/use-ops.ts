"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { opsApi } from "@/lib/api/ops";
import { ApiError } from "@/lib/api/client";
import type { OpsAction } from "@/types/ops";
import { useOpsAuth } from "./auth-context";
export const opsKey = ["ops-data"] as const;
export function useOpsData() {
  const { user } = useOpsAuth();
  return useQuery({
    queryKey: opsKey,
    queryFn: () => opsApi.getSnapshot(),
    enabled: !!user,
    refetchInterval: 15000,
    retry: (count, error) =>
      !(error instanceof ApiError && error.status === 401) && count < 1,
  });
}
export function useOpsAction() {
  const { user } = useOpsAuth(),
    client = useQueryClient();
  return useMutation({
    mutationFn: (action: OpsAction) => {
      if (!user) throw new Error("Sign in first.");
      return opsApi.act(action, user);
    },
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: opsKey }),
        client.invalidateQueries({ queryKey: ["rider-ui"] }),
      ]);
    },
  });
}
