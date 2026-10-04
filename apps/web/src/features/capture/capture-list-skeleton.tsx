export function CaptureListSkeleton() {
  return (
    <div aria-busy="true" aria-label="記録を読み込んでいます">
      <div
        className="border-t border-[#D5DCE5]"
        aria-hidden="true"
      >
        {[0, 1, 2, 3].map((item) => (
          <div
            key={item}
            className="grid min-h-16 grid-cols-[3.75rem_minmax(0,1fr)] gap-3 border-b border-[#D5DCE5] py-4"
          >
            <div className="mt-1 h-3 w-10 animate-pulse rounded-full bg-[#D5DCE5] motion-reduce:animate-none" />
            <div className="space-y-2">
              <div className="h-4 w-full animate-pulse rounded-full bg-[#D5DCE5] motion-reduce:animate-none" />
              <div className="h-4 w-2/3 animate-pulse rounded-full bg-[#D5DCE5] motion-reduce:animate-none" />
            </div>
          </div>
        ))}
      </div>
      <span className="sr-only">記録を読み込んでいます</span>
    </div>
  );
}
