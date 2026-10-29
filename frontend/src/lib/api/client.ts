export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "/api/backend";
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}
export async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...options,
      signal: options.signal ?? AbortSignal.timeout(15000),
      credentials: "include",
      cache: "no-store",
      headers: {
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...options.headers,
      },
    });
  } catch {
    throw new ApiError(
      0,
      "Cannot reach QuickDrop. Check the API connection and retry.",
    );
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    if (
      response.status === 401 &&
      (path.startsWith("/ui/ops/") || path === "/auth/me") &&
      typeof window !== "undefined"
    )
      window.dispatchEvent(new Event("quickdrop:session-expired"));
    if (
      response.status === 401 &&
      path.startsWith("/ui/conversations/") &&
      typeof window !== "undefined"
    ) {
      const rider = new URL(path, "http://quickdrop.local").searchParams.get(
        "rider_id",
      );
      if (rider)
        window.dispatchEvent(
          new CustomEvent("quickdrop:rider-context-expired", { detail: rider }),
        );
    }
    throw new ApiError(
      response.status,
      body?.error?.message ?? `Request failed (${response.status})`,
    );
  }
  return response.status === 204
    ? (undefined as T)
    : (response.json() as Promise<T>);
}
export const post = <T>(path: string, body?: unknown) =>
  request<T>(path, {
    method: "POST",
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}
export async function allPages<T>(path: string): Promise<T[]> {
  const result: T[] = [];
  for (let offset = 0; ;) {
    const page = await request<Page<T>>(
      `${path}${path.includes("?") ? "&" : "?"}limit=100&offset=${offset}`,
    );
    result.push(...page.items);
    offset += page.items.length;
    if (offset >= page.total || page.items.length === 0) return result;
  }
}
