export default function CaptureDetailLoading() {
  return (
    <section
      className="mx-auto w-full max-w-2xl px-5 pb-8 pt-7 sm:px-8"
      aria-busy="true"
      aria-label="記録を読み込んでいます"
    >
      <div className="h-4 w-32 animate-pulse rounded-full bg-[#D5DCE5] motion-reduce:animate-none" />
      <div className="mt-5 h-56 animate-pulse rounded-xl border border-[#D5DCE5] bg-white/70 motion-reduce:animate-none" />
      <div className="mt-3 h-11 animate-pulse rounded-xl bg-[#B9C9BF] motion-reduce:animate-none" />
      <span className="sr-only">読み込み中…</span>
    </section>
  );
}
