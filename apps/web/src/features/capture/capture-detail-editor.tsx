import type { ComponentProps, ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

type CaptureDetailEditorViewProps = {
  defaultValue: string;
  timeLabel: string;
  fieldError?: string;
  message?: ReactNode;
  updateFormProps?: Omit<ComponentProps<"form">, "children">;
  deleteButtonProps?: Omit<ComponentProps<typeof Button>, "children">;
  updatePending?: boolean;
  deletePending?: boolean;
};

export function CaptureDetailEditorView({
  defaultValue,
  timeLabel,
  fieldError,
  message,
  updateFormProps,
  deleteButtonProps,
  updatePending = false,
  deletePending = false,
}: CaptureDetailEditorViewProps) {
  const errorId = fieldError ? "capture-detail-raw-text-error" : undefined;

  return (
    <article className="px-5 pb-[max(2rem,env(safe-area-inset-bottom))] pt-7 sm:px-8">
      <p className="mb-5 text-sm font-medium tabular-nums text-[#4A5870]">
        {timeLabel}
      </p>

      <form className="grid gap-3" {...updateFormProps}>
        <Label htmlFor="capture-detail-raw-text" className="sr-only">
          記録の本文
        </Label>
        <Textarea
          id="capture-detail-raw-text"
          name="rawText"
          defaultValue={defaultValue}
          maxLength={2000}
          rows={8}
          aria-describedby={errorId}
          aria-invalid={fieldError ? true : undefined}
          className="min-h-56 resize-y rounded-xl border-[#BFC8D3] bg-white px-4 py-4 text-[1.0625rem] leading-[1.7] text-[#1A1D23] focus-visible:border-[#2F6A4A] focus-visible:ring-[#2F6A4A]/20"
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
          disabled={updatePending}
          className="h-11 rounded-xl bg-[#2F6A4A] font-sans text-base font-semibold text-white hover:bg-[#285C40]"
        >
          {updatePending ? "保存しています" : "保存する"}
        </Button>
      </form>

      <div className="mt-10 border-t border-[#D5DCE5] pt-5">
        <Button
          {...deleteButtonProps}
          type="button"
          variant="destructive"
          disabled={deletePending}
          className="h-11 w-full rounded-xl font-sans text-base font-semibold"
        >
          {deletePending ? "削除しています" : "削除する"}
        </Button>
      </div>
    </article>
  );
}
