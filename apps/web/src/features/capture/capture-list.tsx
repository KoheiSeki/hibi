import Link from "next/link";

import { captureStatusMessage } from "./capture-processing-status";

export type CaptureListItemView = {
  id: string;
  href: string;
  rawText: string;
  status: string;
  timeLabel: string;
  dateTime: string;
  dateLabel?: string;
};

type CaptureListProps = {
  items: readonly CaptureListItemView[];
};

export function CaptureList({ items }: CaptureListProps) {
  return (
    <ul className="relative" aria-label="記録の一覧">
      {items.map((item) => {
        const statusMessage = captureStatusMessage(item.status);
        return (
          <li key={item.id} className="relative">
          {item.dateLabel ? (
            <p className="pb-2 pt-6 text-xs font-medium tracking-[0.08em] text-[#5A6A62]">
              {item.dateLabel}
            </p>
          ) : null}
          <span
            aria-hidden="true"
            className="absolute bottom-0 left-[0.42rem] top-0 w-px bg-[#D5E3D9]"
          />
          <Link
            href={item.href}
            className="group grid min-h-16 grid-cols-[1.15rem_3.4rem_minmax(0,1fr)] items-start gap-3 py-4 text-[#15201A] no-underline outline-none"
          >
            <span
              aria-hidden="true"
              className="relative z-10 mt-1.5 size-2.5 justify-self-center rounded-full bg-[#1E6B43] ring-4 ring-[#EEF3EF] transition-transform group-hover:scale-125"
            />
            <time
              dateTime={item.dateTime}
              className="pt-0.5 text-sm font-medium tabular-nums text-[#5A6A62]"
            >
              {item.timeLabel}
            </time>
            <span>
              <span className="line-clamp-2 text-[1.0625rem] leading-7 group-hover:text-[#1E6B43] group-focus-visible:rounded-md group-focus-visible:ring-2 group-focus-visible:ring-[#1E6B43]">
                {item.rawText}
              </span>
              {statusMessage ? (
                <span
                  className="mt-1 block text-sm text-[#5A6A62]"
                  aria-live="polite"
                >
                  {statusMessage}
                </span>
              ) : null}
            </span>
          </Link>
          </li>
        );
      })}
    </ul>
  );
}
