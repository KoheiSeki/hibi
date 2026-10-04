import type { ComponentProps, ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

type CaptureComposerViewProps = Omit<ComponentProps<"form">, "children"> & {
  defaultValue?: string;
  fieldError?: string;
  message?: ReactNode;
  pending?: boolean;
  submitDisabled?: boolean;
};

export function CaptureComposerView({
  className,
  defaultValue,
  fieldError,
  message,
  pending = false,
  submitDisabled = false,
  ...formProps
}: CaptureComposerViewProps) {
  const errorId = fieldError ? "capture-raw-text-error" : undefined;

  return (
    <form
      className={cn("grid gap-2.5", className)}
      aria-label="新しい記録"
      {...formProps}
    >
      <Label htmlFor="capture-raw-text" className="sr-only">
        何を残しますか
      </Label>
      <Textarea
        id="capture-raw-text"
        name="rawText"
        defaultValue={defaultValue}
        placeholder="何を残しますか"
        maxLength={2000}
        rows={2}
        aria-describedby={errorId}
        aria-invalid={fieldError ? true : undefined}
        className="min-h-20 resize-none rounded-xl border-[#BFC8D3] bg-white px-4 py-3 text-[1.0625rem] leading-7 text-[#1A1D23] shadow-[0_1px_0_rgb(26_29_35/0.03)] placeholder:text-[#697588] focus-visible:border-[#2F6A4A] focus-visible:ring-[#2F6A4A]/20"
      />

      {fieldError ? (
        <p
          id={errorId}
          className="text-sm leading-5 text-destructive"
          role="alert"
        >
          {fieldError}
        </p>
      ) : null}

      {message ? <div className="text-sm text-[#4A5870]">{message}</div> : null}

      <Button
        type="submit"
        disabled={pending || submitDisabled}
        className="h-11 w-full rounded-xl bg-[#2F6A4A] font-sans text-base font-semibold text-white hover:bg-[#285C40] focus-visible:border-[#244F38] focus-visible:ring-[#2F6A4A]/30"
      >
        {pending ? "記録しています" : "記録する"}
      </Button>
    </form>
  );
}
