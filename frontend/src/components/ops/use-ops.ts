"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { opsApi } from "@/lib/api/ops";
import type { OpsAction } from "@/types/ops";
import { useOpsAuth } from "./auth-context";
export const opsKey = ["ops-data"] as const;
export function useOpsData() {
  return useQuery({
    queryKey: opsKey,
    queryFn: () => opsApi.getSnapshot(),
    retry: 1,
  });
}
export function useOpsAction() {
  const { user } = useOpsAuth(),
    client = useQueryClient();
  return useMutation({
    mutationFn: (action: OpsAction) => {
      if (!user) throw new Error("Sign in to the demo workspace first.");
      return opsApi.act(action, user);
    },
    onSuccess: async (snapshot) => {
      client.setQueryData(opsKey, snapshot);
      await client.invalidateQueries({ queryKey: ["rider-ui"] });
    },
  });
}
