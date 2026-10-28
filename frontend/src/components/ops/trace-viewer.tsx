"use client";
import { useState } from "react";
import { Copy, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { AgentTrace, Json } from "@/types/ops";
import { StatusBadge, time } from "./common";
function JsonNode({
  value,
  label = "payload",
  depth = 0,
}: {
  value: Json;
  label?: string;
  depth?: number;
}) {
  if (value !== null && typeof value === "object")
    return (
      <details className="ops-json-node" open={depth === 0}>
        <summary>
          <span>{label}</span>
          <small>
            {Array.isArray(value)
              ? `[${value.length}]`
              : `{${Object.keys(value).length}}`}
          </small>
        </summary>
        <div>
          {Object.entries(value).map(([key, item]) => (
            <JsonNode key={key} value={item} label={key} depth={depth + 1} />
          ))}
        </div>
      </details>
    );
  return (
    <div className="ops-json-leaf">
      <span>{label}:</span>
      <code>{JSON.stringify(value)}</code>
    </div>
  );
}
export function TraceJsonViewer({ value }: { value: Json }) {
  const [copied, setCopied] = useState(false),
    [error, setError] = useState("");
  async function copy() {
    try {
      await navigator.clipboard.writeText(JSON.stringify(value, null, 2));
      setCopied(true);
      setError("");
    } catch {
      setError("Clipboard unavailable. Expand and select the values below.");
    }
  }
  return (
    <div className="ops-json">
      <div>
        <span>SANITIZED JSON</span>
        <Button variant="ghost" size="sm" onClick={() => void copy()}>
          {copied ? <Check size={12} /> : <Copy size={12} />}{" "}
          {copied ? "Copied" : "Copy JSON"}
        </Button>
      </div>
      {error && <p role="status">{error}</p>}
      <JsonNode value={value} />
    </div>
  );
}
export function AgentTraceTimeline({ events }: { events: AgentTrace[] }) {
  return (
    <ol className="ops-trace-timeline">
      {[...events]
        .sort((a, b) => Date.parse(a.created_at) - Date.parse(b.created_at))
        .map((event) => (
          <li key={event.id}>
            <span className={`ops-trace-node ${event.status.toLowerCase()}`} />
            <details>
              <summary>
                <div>
                  <strong>{event.name}</strong>
                  <span>
                    {time(event.created_at)} · {event.type}
                    {event.duration_ms !== null
                      ? ` · ${event.duration_ms} ms`
                      : ""}
                  </span>
                </div>
                <StatusBadge status={event.status} />
              </summary>
              <TraceJsonViewer
                value={{ input: event.input, output: event.output }}
              />
            </details>
          </li>
        ))}
    </ol>
  );
}
