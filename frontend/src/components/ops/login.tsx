"use client";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  ArrowRight,
  BrainCircuit,
  Eye,
  EyeOff,
  ShieldCheck,
  Wallet,
  ScanSearch,
} from "lucide-react";
import { Logo } from "@/components/shared/logo";
import { Button } from "@/components/ui/button";
import { useOpsAuth } from "./auth-context";
import type { LoginInput } from "@/types/ops";
const schema = z.object({
  email: z.email("Enter a valid demo email."),
  password: z.string().min(1, "Enter the demo password."),
});
export function OpsLogin() {
  const auth = useOpsAuth();
  const [show, setShow] = useState(false),
    [error, setError] = useState("");
  const form = useForm<LoginInput>({
    resolver: zodResolver(schema),
    defaultValues: { email: "ops@quickdrop.demo", password: "" },
  });
  async function submit(values: LoginInput) {
    try {
      setError("");
      await auth.login(values);
    } catch (error) {
      setError(error instanceof Error ? error.message : "Unable to sign in.");
    }
  }
  return (
    <main className="ops-login">
      <div className="ops-login-story">
        <Logo />
        <div>
          <span className="ops-kicker">QUICKDROP OPERATIONS</span>
          <h1>
            Operations,
            <br />
            under control.
          </h1>
          <p>
            AI investigates. Your team stays in charge.
            <br />
            One clear workspace for every payout decision.
          </p>
          <div className="ops-login-flow">
            {[
              { icon: BrainCircuit, label: "Investigate" },
              { icon: ShieldCheck, label: "Review" },
              { icon: Wallet, label: "Verify" },
              { icon: ScanSearch, label: "Trace" },
            ].map(({ icon: Icon, label }) => (
              <div key={label}>
                <Icon size={21} />
                <span>{label}</span>
              </div>
            ))}
          </div>
        </div>
        <small>AI-powered resolution. Human oversight at every step.</small>
      </div>
      <section className="ops-login-form">
        <div className="ops-login-card">
          <span className="ops-kicker">DEMO WORKSPACE</span>
          <h2>Welcome back</h2>
          <p>Sign in to your operations workspace.</p>
          <form onSubmit={form.handleSubmit(submit)}>
            <label className="ops-field">
              Email
              <input
                type="email"
                autoComplete="username"
                {...form.register("email")}
                aria-invalid={!!form.formState.errors.email}
              />
              {form.formState.errors.email && (
                <small role="alert">
                  {form.formState.errors.email.message}
                </small>
              )}
            </label>
            <label className="ops-field">
              Password
              <span className="ops-password">
                <input
                  type={show ? "text" : "password"}
                  autoComplete="current-password"
                  {...form.register("password")}
                  aria-invalid={!!form.formState.errors.password}
                />
                <button
                  type="button"
                  aria-label={show ? "Hide password" : "Show password"}
                  onClick={() => setShow(!show)}
                >
                  {show ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </span>
              {form.formState.errors.password && (
                <small role="alert">
                  {form.formState.errors.password.message}
                </small>
              )}
            </label>
            {error && (
              <div className="ops-form-error" role="alert">
                {error}
              </div>
            )}
            <Button
              type="submit"
              className="ops-primary ops-login-submit"
              disabled={form.formState.isSubmitting}
            >
              {form.formState.isSubmitting ? "Signing in…" : "Sign in to demo"}
              <ArrowRight size={15} />
            </Button>
          </form>
          <div className="ops-demo-credentials">
            <strong>
              Demo password: <code>demo-only</code>
            </strong>
            <span>
              Use any valid email. This is simulated sign-in, not production
              security.
            </span>
          </div>
        </div>
      </section>
    </main>
  );
}
