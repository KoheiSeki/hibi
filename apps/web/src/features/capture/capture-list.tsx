import Link from "next/link";

export type CaptureListItemView = {
  id: string;
  href: string;
  rawText: string;
  timeLabel: string;
  dateTime: string;
  dateLabel?: string;
};

type CaptureListProps = {
  items: readonly CaptureListItemView[];
};

export function CaptureList({ items }: CaptureListProps) {
  return (
    <ul className="border-t border-[#D5DCE5]" aria-label="記録の一覧">
      {items.map((item) => (
        <li key={item.id}>
          {item.dateLabel ? (
            <p className="border-b border-[#D5DCE5] pb-2 pt-5 text-xs font-medium tracking-[0.06em] text-[#4A5870]">
              {item.dateLabel}
            </p>
          ) : null}
          <Link
            href={item.href}
            className="group grid min-h-16 grid-cols-[3.75rem_minmax(0,1fr)] items-start gap-3 border-b border-[#D5DCE5] py-4 text-[#1A1D23] no-underline outline-none transition-colors hover:bg-white/60 focus-visible:bg-white focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[#2F6A4A]"
          >
            <time
              dateTime={item.dateTime}
              className="pt-0.5 text-sm font-medium tabular-nums text-[#4A5870]"
            >
              {item.timeLabel}
            </time>
            <span className="line-clamp-2 text-[1.0625rem] leading-7 group-hover:text-black">
              {item.rawText}
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}
