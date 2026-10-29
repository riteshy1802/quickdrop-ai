"use client";
import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { API_BASE } from "@/lib/api/client";
import { emptyStream, reduceStream } from "@/lib/realtime/events";
import { listen } from "@/lib/realtime/connection";
export function useEvents(
  path: string | null,
  conversationId?: string,
  riderId?: string,
) {
  const client = useQueryClient();
  const [state, setState] = useState({
    path,
    stream: emptyStream,
    connection: "connecting",
  });
  useEffect(() => {
    if (!path) return;
    const source = new EventSource(`${API_BASE}${path}`, {
      withCredentials: true,
    });
    const refresh = () => {
      void client.invalidateQueries({ queryKey: ["rider-ui"] });
      void client.invalidateQueries({ queryKey: ["ops-data"] });
    };
    return listen(
      source,
      (event) => {
        if (
          conversationId &&
          (event.conversation_id !== conversationId ||
            event.rider_id !== riderId)
        )
          return;
        setState((previous) => ({
          path,
          connection: "connected",
          stream: reduceStream(
            previous.path === path ? previous.stream : emptyStream,
            event,
          ),
        }));
        if (
          !["agent.status", "agent.started", "agent.message.delta"].includes(
            event.event_type,
          )
        )
          refresh();
      },
      () => {
        setState({ path, stream: emptyStream, connection: "connected" });
        refresh();
      },
      () => {
        setState({ path, stream: emptyStream, connection: "reconnecting" });
        refresh();
      },
      () => {
        if (conversationId) {
          window.dispatchEvent(
            new CustomEvent("quickdrop:rider-context-expired", {
              detail: riderId,
            }),
          );
          setState({ path, stream: emptyStream, connection: "reconnecting" });
          refresh();
        } else {
          source.close();
          window.dispatchEvent(new Event("quickdrop:session-expired"));
        }
      },
    );
  }, [path, client, conversationId, riderId]);
  return state.path === path
    ? state
    : { path, stream: emptyStream, connection: "connecting" };
}
export function useConversationEvents(id: string, rider: string) {
  return useEvents(
    `/ui/conversations/${id}/events?rider_id=${encodeURIComponent(rider)}`,
    id,
    rider,
  );
}
export function useOpsEvents(enabled: boolean) {
  return useEvents(enabled ? "/ui/ops/events" : null);
}
