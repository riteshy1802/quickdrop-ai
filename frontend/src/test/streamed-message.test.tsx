import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { StreamedMessage } from "@/components/rider/streamed-message";
import type { Message } from "@/types/rider";

const preference = vi.hoisted(() => ({ reduced: false }));
vi.mock("motion/react", () => ({ useReducedMotion: () => preference.reduced }));
vi.mock("@/components/rider/chat-message", () => ({
  ChatMessage: ({message}: {message: Message}) => <p data-testid="reply">{message.text}</p>,
}));
const message: Message = {
  id: "reply", conversation_id: "thread", sender: "AI", text: "",
  created_at: "2026-10-30T00:00:00+05:30",
};
const reply = () => screen.getByTestId("reply").textContent;
beforeEach(() => { vi.useFakeTimers(); preference.reduced = false; });
afterEach(() => { cleanup(); vi.useRealTimers(); });

it("reveals buffered chunks progressively without restarting the prefix", () => {
  const view = render(<StreamedMessage message={{...message, text: "Hello "}} animate />);
  expect(reply()).toBe("");
  act(() => vi.advanceTimersByTime(48));
  expect(reply()).toBe("Hel");
  view.rerender(<StreamedMessage message={{...message, text: "Hello world"}} animate />);
  expect(reply()).toBe("Hel");
  act(() => vi.advanceTimersByTime(16));
  expect(reply()).toBe("Hell");
  act(() => vi.advanceTimersByTime(1000));
  expect(reply()).toBe("Hello world");
  expect(vi.getTimerCount()).toBe(0);
});

it("animates a full burst and repeated final snapshots do not restart it", () => {
  const view = render(<StreamedMessage message={{...message, text: "Complete answer"}} animate />);
  act(() => vi.advanceTimersByTime(64));
  expect(reply()).toBe("Comp");
  view.rerender(<StreamedMessage message={{...message, text: "Complete answer"}} animate />);
  expect(reply()).toBe("Comp");
  act(() => vi.advanceTimersByTime(1000));
  expect(reply()).toBe("Complete answer");
});

it("uses corrected authoritative text without stitching stale claims into it", () => {
  const view = render(<StreamedMessage message={{...message, text: "Paid already"}} animate />);
  act(() => vi.advanceTimersByTime(64));
  expect(reply()).toBe("Paid");
  view.rerender(<StreamedMessage message={{...message, text: "Verification required"}} animate />);
  expect(reply()).toBe("");
  act(() => vi.advanceTimersByTime(1000));
  expect(reply()).toBe("Verification required");
});

it("preserves Hindi combining characters and complete emoji graphemes", () => {
  render(<StreamedMessage message={{...message, text: "कृपा 👩🏽‍💻"}} animate />);
  act(() => vi.advanceTimersByTime(16));
  expect(reply()).toBe("कृ");
  act(() => vi.advanceTimersByTime(1000));
  expect(reply()).toBe("कृपा 👩🏽‍💻");
});

it("renders history and reduced-motion replies immediately", () => {
  const view = render(<StreamedMessage message={{...message, text: "Saved history"}} animate={false} />);
  expect(reply()).toBe("Saved history");
  preference.reduced = true;
  view.rerender(<StreamedMessage message={{...message, text: "Accessible answer"}} animate />);
  expect(reply()).toBe("Accessible answer");
  expect(vi.getTimerCount()).toBe(0);
});

it("cancels queued animation on thread/message replacement and unmount", () => {
  const view = render(<StreamedMessage key="old" message={{...message, text: "Old reply"}} animate />);
  act(() => vi.advanceTimersByTime(32));
  view.rerender(<StreamedMessage key="new" message={{...message, id: "new", text: "New reply"}} animate />);
  expect(reply()).toBe("");
  act(() => vi.advanceTimersByTime(16));
  expect(reply()).toBe("N");
  view.unmount();
  expect(vi.getTimerCount()).toBe(0);
});
