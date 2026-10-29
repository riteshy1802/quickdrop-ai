import { allPages, post, request } from "./client";
import {
  mapConversation,
  mapDispute,
  type ConversationRecord,
  type DisputeRecord,
  type PayoutRecord,
  type RiderRecord,
} from "./contracts";
import type {
  Message,
  PostMessageRequest,
  PostMessageResponse,
  Scenario,
} from "@/types/rider";
const riderQuery = (rider: string) => `rider_id=${encodeURIComponent(rider)}`;
export const riderApi = {
  async getRiders() {
    return (await allPages<RiderRecord>("/ui/riders")).map((r) => ({
      id: r.rider_id,
      name: r.name,
      city: r.city,
      demo: true as const,
    }));
  },
  async selectRider(rider: string) {
    await post("/ui/demo/rider", { rider_id: rider });
  },
  async getConversations(rider: string) {
    return (
      await allPages<ConversationRecord>(
        `/ui/riders/${encodeURIComponent(rider)}/conversations`,
      )
    ).map(mapConversation);
  },
  async getConversation(rider: string, id: string) {
    return mapConversation(
      await request<ConversationRecord>(
        `/ui/conversations/${id}?${riderQuery(rider)}`,
      ),
    );
  },
  getMessages(rider: string, id: string) {
    return allPages<Message>(
      `/ui/conversations/${id}/messages?${riderQuery(rider)}`,
    );
  },
  async getDisputes(rider: string, id: string) {
    const [disputes, payouts] = await Promise.all([
      allPages<DisputeRecord>(
        `/ui/conversations/${id}/disputes?${riderQuery(rider)}`,
      ),
      allPages<PayoutRecord>(
        `/ui/conversations/${id}/payouts?${riderQuery(rider)}`,
      ),
    ]);
    return disputes.map((d) => mapDispute(d, payouts));
  },
  async createConversation(rider: string, scenario: Scenario | null) {
    void scenario;
    return mapConversation(
      await post<ConversationRecord>(
        `/ui/riders/${encodeURIComponent(rider)}/conversations`,
      ),
    );
  },
  postMessage(
    payload: PostMessageRequest,
    context: { conversation_id: string },
  ) {
    return post<PostMessageResponse>("/messages", {
      ...payload,
      conversation_id: context.conversation_id,
    });
  },
};
