import type { LoginInput, OpsUser } from "@/types/ops";
const key = "quickdrop-demo-operator";
let current: OpsUser | null = null;
// Demo navigation state only. A future transport will use server-managed HttpOnly cookies.
export const mockOpsAuth = {
  async me(): Promise<OpsUser | null> {
    if (typeof window !== "undefined")
      try {
        const stored = sessionStorage.getItem(key);
        if (stored) {
          const value = JSON.parse(stored);
          if (value.id === "demo-ops" && typeof value.email === "string")
            current = value;
        }
      } catch {
        current = null;
      }
    return current;
  },
  async login(input: LoginInput): Promise<OpsUser> {
    await new Promise((resolve) => setTimeout(resolve, 400));
    if (input.password !== "demo-only")
      throw new Error(
        "Invalid demo password. Use demo-only to enter this prototype.",
      );
    current = {
      id: "demo-ops",
      name: "Demo Operator",
      email: input.email,
      role: "Demo operator",
    };
    if (typeof window !== "undefined")
      try {
        sessionStorage.setItem(key, JSON.stringify(current));
      } catch {
        /* In-memory demo login still works. */
      }
    return current;
  },
  async logout() {
    current = null;
    if (typeof window !== "undefined")
      try {
        sessionStorage.removeItem(key);
      } catch {
        /* No stored demo state. */
      }
  },
};
