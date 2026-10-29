import { eventNames, parseEvent, type LiveEvent } from "./events";
export interface EventConnection {
  addEventListener: (type: string, listener: EventListener) => void;
  removeEventListener: (type: string, listener: EventListener) => void;
  close: () => void;
}
export function listen(
  source: EventConnection,
  onEvent: (event: LiveEvent) => void,
  onReady: () => void,
  onError: () => void,
  onExpired: () => void,
) {
  const seen = new Set<string>();
  const receive: EventListener = (raw) => {
    const event = parseEvent((raw as MessageEvent<string>).data);
    if (!event || seen.has(event.event_id)) return;
    seen.add(event.event_id);
    if (seen.size > 1000) seen.delete(seen.values().next().value!);
    onEvent(event);
  };
  const ready: EventListener = () => onReady(),
    error: EventListener = () => onError(),
    expired: EventListener = () => onExpired();
  for (const name of eventNames) source.addEventListener(name, receive);
  source.addEventListener("ready", ready);
  source.addEventListener("error", error);
  source.addEventListener("unavailable", error);
  source.addEventListener("session.expired", expired);
  return () => {
    for (const name of eventNames) source.removeEventListener(name, receive);
    source.removeEventListener("ready", ready);
    source.removeEventListener("error", error);
    source.removeEventListener("unavailable", error);
    source.removeEventListener("session.expired", expired);
    source.close();
    seen.clear();
  };
}
