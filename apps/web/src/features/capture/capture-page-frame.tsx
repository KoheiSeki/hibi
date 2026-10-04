import type { ReactNode } from "react";

type CapturePageFrameProps = {
  dateLabel: string;
  children: ReactNode;
  composer: ReactNode;
};

export function CapturePageFrame({
  dateLabel,
  children,
  composer,
}: CapturePageFrameProps) {
  return (
    <section className="mx-auto flex min-h-[calc(100svh-3.5rem)] w-full max-w-2xl flex-col">
      <header className="px-5 pb-3 pt-6 sm:px-8">
        <p className="text-[0.8125rem] font-medium tracking-[0.04em] text-[#4A5870]">
          {dateLabel}
        </p>
      </header>

      <div className="flex-1 px-5 pb-36 sm:px-8">{children}</div>

      <div
        data-slot="capture-composer-region"
        className="sticky bottom-0 z-20 border-t border-[#D5DCE5] bg-[#F4F6F8]/95 px-5 pb-[max(1rem,env(safe-area-inset-bottom))] pt-3 backdrop-blur-md sm:px-8"
      >
        <div className="mx-auto w-full max-w-2xl">{composer}</div>
      </div>
    </section>
  );
}
