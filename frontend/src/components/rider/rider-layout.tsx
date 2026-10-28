"use client";
import { useState } from "react";
import Link from "next/link";
import { Info, MessageSquare, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetTitle,
} from "@/components/ui/sheet";
import type { Rider, Scenario } from "@/types/rider";
import { ConversationSidebar } from "./conversation-sidebar";
import { ChatHeader } from "./chat-header";
import { ChatThread } from "./chat-thread";
import { DisputeDetailsPanel } from "./dispute-details-panel";
import { ConversationEmptyState } from "./conversation-empty-state";
import {
  useConversations,
  useDesktopDetails,
  useCreateConversation,
  useRiders,
  useThread,
} from "./use-rider-support";

function ErrorPanel({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <div className="rider-query-error" role="alert">
      <Info size={23} />
      <h2>Couldn’t load this workspace.</h2>
      <p>{message}</p>
      <Button variant="outline" onClick={onRetry}>
        <RotateCcw size={14} />
        Try again
      </Button>
      <Link href="/">Back to QuickDrop</Link>
    </div>
  );
}
function Workspace({
  rider,
  riders,
  onRider,
}: {
  rider: Rider;
  riders: Rider[];
  onRider: (id: string) => void;
}) {
  const [selected, setSelected] = useState<string>();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(true);
  const [detailsSheet, setDetailsSheet] = useState(false);
  const desktop = useDesktopDetails();
  const conversations = useConversations(rider.id);
  const activeId = selected ?? conversations.data?.[0]?.id;
  const thread = useThread(rider.id, activeId);
  const create = useCreateConversation(rider.id);
  async function start(scenario: Scenario | null = null) {
    try {
      const conversation = await create.mutateAsync(scenario);
      setSelected(conversation.id);
      setSidebarOpen(false);
    } catch {
      /* Mutation state renders the error. */
    }
  }
  function select(id: string) {
    setSelected(id);
    setSidebarOpen(false);
  }
  function toggleDetails() {
    if (desktop) setDetailsOpen(!detailsOpen);
    else setDetailsSheet(true);
  }
  const sidebar = (
    <ConversationSidebar
      rider={rider}
      riders={riders}
      onRider={onRider}
      conversations={conversations.data ?? []}
      activeId={activeId}
      onSelect={select}
      onNew={() => void start()}
      loading={conversations.isPending}
      creating={create.isPending}
    />
  );
  const details = (
    <DisputeDetailsPanel
      disputes={thread.data?.disputes ?? []}
      loading={thread.isFetching && !thread.data}
      onClose={() => {
        setDetailsOpen(false);
        setDetailsSheet(false);
      }}
    />
  );
  return (
    <div className={`rider-workspace ${detailsOpen ? "has-details" : ""}`}>
      <aside className="rider-sidebar" aria-label="Rider workspace">
        {sidebar}
      </aside>
      <main className="rider-chat-main">
        <ChatHeader
          conversation={thread.data?.conversation}
          onSidebar={() => setSidebarOpen(true)}
          onDetails={toggleDetails}
          detailsOpen={desktop ? detailsOpen : detailsSheet}
        />
        <div className="rider-demo-banner">
          <Info size={13} />
          <span>
            Demo workspace
            <span className="rider-banner-extra">
              {" "}
              · Scripted conversations. Sample financial records.
            </span>
          </span>
          <span>No real payouts</span>
        </div>
        {create.isError && (
          <div className="rider-inline-error" role="alert">
            {create.error.message}
            <Button size="sm" variant="ghost" onClick={() => void start()}>
              Retry
            </Button>
          </div>
        )}
        {conversations.isError ? (
          <ErrorPanel
            message={conversations.error.message}
            onRetry={() => void conversations.refetch()}
          />
        ) : thread.isError ? (
          <ErrorPanel
            message={thread.error.message}
            onRetry={() => void thread.refetch()}
          />
        ) : conversations.isPending || (activeId && thread.isPending) ? (
          <div
            className="rider-chat-loading"
            role="status"
            aria-label="Loading conversation"
          >
            <Skeleton className="rider-message-skeleton" />
            <Skeleton className="rider-message-skeleton is-right" />
            <Skeleton className="rider-message-skeleton" />
            <span>Loading your conversation…</span>
          </div>
        ) : thread.data ? (
          <ChatThread
            key={activeId}
            riderId={rider.id}
            conversation={thread.data.conversation}
            messages={thread.data.messages}
            onScenario={(scenario) => void start(scenario)}
            creating={create.isPending}
          />
        ) : (
          <>
            <ConversationEmptyState
              onScenario={(scenario) => void start(scenario)}
              creating={create.isPending}
            />
            <Button
              className="rider-start-button"
              disabled={create.isPending}
              onClick={() => void start()}
            >
              <MessageSquare size={15} />
              Start a conversation
            </Button>
          </>
        )}
      </main>
      {detailsOpen && (
        <aside
          className="rider-details"
          aria-label="Dispute and payout details"
        >
          {details}
        </aside>
      )}
      <Sheet open={sidebarOpen} onOpenChange={setSidebarOpen}>
        <SheetContent side="left" className="rider-sheet rider-sidebar-sheet">
          <SheetTitle className="sr-only">Rider conversations</SheetTitle>
          <SheetDescription className="sr-only">
            Select a demo rider or open a conversation.
          </SheetDescription>
          {sidebar}
        </SheetContent>
      </Sheet>
      <Sheet open={detailsSheet} onOpenChange={setDetailsSheet}>
        <SheetContent
          side="right"
          className="rider-sheet rider-details-sheet"
          showCloseButton={false}
        >
          <SheetTitle className="sr-only">
            Dispute and payout details
          </SheetTitle>
          <SheetDescription className="sr-only">
            Illustrative dispute information and payment status.
          </SheetDescription>
          {details}
        </SheetContent>
      </Sheet>
    </div>
  );
}
export function RiderLayout() {
  const riders = useRiders();
  const [riderId, setRiderId] = useState("R003");
  if (riders.isError)
    return (
      <div className="rider-app">
        <ErrorPanel
          message={riders.error.message}
          onRetry={() => void riders.refetch()}
        />
      </div>
    );
  const rider = riders.data?.find((profile) => profile.id === riderId);
  return (
    <div className="rider-app">
      {!rider ? (
        <div className="rider-initial-loading" role="status">
          <span className="rider-welcome-icon">
            <MessageSquare size={26} />
          </span>
          <p>Opening Rider Support…</p>
          <Skeleton className="rider-loading-bar" />
        </div>
      ) : (
        <Workspace
          key={rider.id}
          rider={rider}
          riders={riders.data!}
          onRider={setRiderId}
        />
      )}
    </div>
  );
}
