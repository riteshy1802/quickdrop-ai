"use client";
import { useEffect, useSyncExternalStore } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { riderApi } from "@/lib/api/rider";
import type { PostMessageRequest, Scenario } from "@/types/rider";
export const riderKeys = {
  riders: ["rider-ui", "riders"] as const,
  conversations: (riderId: string) =>
    ["rider-ui", riderId, "conversations"] as const,
  thread: (riderId: string, id: string) =>
    ["rider-ui", riderId, "thread", id] as const,
};
export function useRiders() {
  return useQuery({
    queryKey: riderKeys.riders,
    queryFn: () => riderApi.getRiders(),
  });
}
export function useRiderContext(riderId: string) {
  const client = useQueryClient();
  const selection = useMutation({
    mutationFn: () => riderApi.selectRider(riderId),
    onSuccess: () =>
      client.invalidateQueries({ queryKey: ["rider-ui", riderId] }),
  });
  const select = selection.mutate;
  useEffect(() => {
    select();
  }, [select, riderId]);
  useEffect(() => {
    const renew = (event: Event) => {
      if ((event as CustomEvent<string>).detail === riderId) select();
    };
    window.addEventListener("quickdrop:rider-context-expired", renew);
    return () =>
      window.removeEventListener("quickdrop:rider-context-expired", renew);
  }, [riderId, select]);
  return selection;
}
export function useConversations(riderId: string, enabled = true) {
  return useQuery({
    queryKey: riderKeys.conversations(riderId),
    enabled,
    queryFn: () => riderApi.getConversations(riderId),
    refetchInterval: 15000,
  });
}
export function useThread(
  riderId: string,
  id: string | undefined,
  enabled = true,
) {
  return useQuery({
    queryKey: riderKeys.thread(riderId, id ?? "none"),
    enabled: !!id && enabled,
    refetchInterval: 15000,
    queryFn: async () => {
      if (!id) throw new Error("Select a conversation.");
      const [conversation, messages, disputes] = await Promise.all([
        riderApi.getConversation(riderId, id),
        riderApi.getMessages(riderId, id),
        riderApi.getDisputes(riderId, id),
      ]);
      return { conversation, messages, disputes };
    },
  });
}
export function useCreateConversation(riderId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (scenario: Scenario | null) =>
      riderApi.createConversation(riderId, scenario),
    onSuccess: () =>
      client.invalidateQueries({ queryKey: riderKeys.conversations(riderId) }),
  });
}
export function useSendMessage(riderId: string, id: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      request,
    }: {
      request: PostMessageRequest;
      simulateFailure?: boolean;
    }) => riderApi.postMessage(request, { conversation_id: id }),
    retry: false,
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: riderKeys.thread(riderId, id) }),
        client.invalidateQueries({
          queryKey: riderKeys.conversations(riderId),
        }),
      ]);
    },
  });
}

const desktopQuery = "(min-width: 1180px)";
function subscribeDesktop(callback: () => void) {
  const media = window.matchMedia(desktopQuery);
  media.addEventListener("change", callback);
  return () => media.removeEventListener("change", callback);
}
export function useDesktopDetails() {
  return useSyncExternalStore(
    subscribeDesktop,
    () => window.matchMedia(desktopQuery).matches,
    () => false,
  );
}
