import type { LoginInput, OpsUser } from "@/types/ops";
import { ApiError, post, request } from "./client";
interface Operator {
  id: string;
  email: string;
}
const operator = (u: Operator): OpsUser => ({
  ...u,
  name: u.email.split("@")[0],
  role: "Administrator",
});
export const opsAuth = {
  async me() {
    try {
      return operator(await request<Operator>("/auth/me"));
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) return null;
      throw error;
    }
  },
  async login(input: LoginInput) {
    return operator(await post<Operator>("/auth/login", input));
  },
  logout: () => post<void>("/auth/logout"),
};
