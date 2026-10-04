import type { ReactNode } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

type CaptureErrorStateProps = {
  title?: string;
  detail: string;
  action?: ReactNode;
};

export function CaptureErrorState({
  title = "記録を読み込めませんでした",
  detail,
  action,
}: CaptureErrorStateProps) {
  return (
    <Alert
      variant="destructive"
      className="rounded-xl border-[#D5DCE5] bg-white px-4 py-4"
    >
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription className="mt-1 leading-6">
        <p>{detail}</p>
        {action ? <div className="mt-4">{action}</div> : null}
      </AlertDescription>
    </Alert>
  );
}
