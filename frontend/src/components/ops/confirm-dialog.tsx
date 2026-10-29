"use client";
import { useState } from "react";
import { Dialog } from "radix-ui";
import { X } from "lucide-react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
export function ConfirmDialog({
  label,
  title,
  description,
  onConfirm,
  reasonRequired = false,
  destructive = false,
  disabled = false,
}: {
  label: string;
  title: string;
  description: string;
  onConfirm: (reason: string) => Promise<unknown>;
  reasonRequired?: boolean;
  destructive?: boolean;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false),
    [error, setError] = useState("");
  const form = useForm<{ reason: string }>({
    resolver: zodResolver(
      z.object({
        reason: z
          .string()
          .trim()
          .min(
            reasonRequired ? 3 : 0,
            "Enter a reason of at least 3 characters.",
          )
          .max(1000),
      }),
    ),
    defaultValues: { reason: "" },
  });
  async function submit({ reason }: { reason: string }) {
    try {
      setError("");
      await onConfirm(reason);
      setOpen(false);
      form.reset();
    } catch (error) {
      setError(
        error instanceof Error ? error.message : "Unable to complete action.",
      );
    }
  }
  return (
    <Dialog.Root
      open={open}
      onOpenChange={(value) => {
        if (!form.formState.isSubmitting) {
          setOpen(value);
          setError("");
        }
      }}
    >
      <Dialog.Trigger asChild>
        <Button
          variant={destructive ? "destructive" : "outline"}
          className={destructive ? "" : "ops-primary"}
          disabled={disabled}
        >
          {label}
        </Button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="ops-dialog-overlay" />
        <Dialog.Content className="ops-dialog">
          <Dialog.Title>{title}</Dialog.Title>
          <Dialog.Description>{description}</Dialog.Description>
          <Dialog.Close asChild>
            <Button
              variant="ghost"
              size="icon-sm"
              className="ops-dialog-close"
              aria-label="Close confirmation"
              disabled={form.formState.isSubmitting}
            >
              <X size={16} />
            </Button>
          </Dialog.Close>
          <form onSubmit={form.handleSubmit(submit)}>
            {reasonRequired && (
              <label className="ops-field">
                Decision reason
                <Textarea
                  {...form.register("reason")}
                  placeholder="Explain your decision"
                  aria-invalid={!!form.formState.errors.reason}
                />
                {form.formState.errors.reason && (
                  <small role="alert">
                    {form.formState.errors.reason.message}
                  </small>
                )}
              </label>
            )}
            {error && (
              <p className="ops-form-error" role="alert">
                {error}
              </p>
            )}
            <div className="ops-dialog-actions">
              <Dialog.Close asChild>
                <Button
                  variant="outline"
                  type="button"
                  disabled={form.formState.isSubmitting}
                >
                  Cancel
                </Button>
              </Dialog.Close>
              <Button
                type="submit"
                variant={destructive ? "destructive" : "default"}
                className={destructive ? "" : "ops-primary"}
                disabled={form.formState.isSubmitting}
              >
                {form.formState.isSubmitting ? "Saving…" : label}
              </Button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
