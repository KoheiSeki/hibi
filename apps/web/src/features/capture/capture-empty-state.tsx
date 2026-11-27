export function CaptureEmptyState() {
  return (
    <div className="flex min-h-56 items-center px-2">
      <div className="grid grid-cols-[1.15rem_minmax(0,1fr)] items-start gap-3">
        <span
          aria-hidden="true"
          className="mt-1.5 size-2.5 justify-self-center rounded-full bg-[#1E6B43] ring-4 ring-[#EEF3EF]"
        />
        <div>
          <p className="text-base font-semibold text-[#15201A]">
            最初の一文を書いてください
          </p>
          <p className="mt-2 text-sm leading-6 text-[#5A6A62]">
            予定でも、気づきでも。整理はあとからで大丈夫です。
          </p>
        </div>
      </div>
    </div>
  );
}
