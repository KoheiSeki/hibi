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
      <header className="px-5 pb-2 pt-7 sm:px-8">
        <p className="text-[1.65rem] font-medium leading-none tracking-[0.04em] text-[#15201A] [font-family:var(--font-capture-display),serif]">
          {dateLabel}
        </p>
      </header>

      <div className="flex-1 px-5 pb-40 sm:px-8">{children}</div>

      <div
        data-slot="capture-composer-region"
        className="sticky bottom-0 z-20 bg-[#EEF3EF]/80 px-4 pb-[max(0.85rem,env(safe-area-inset-bottom))] pt-2 backdrop-blur-xl sm:px-6"
      >
        <div className="mx-auto w-full max-w-2xl">{composer}</div>
      </div>
    </section>
  );
}
