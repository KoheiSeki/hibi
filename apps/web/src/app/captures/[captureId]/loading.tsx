export default function CaptureDetailLoading() {
  return (
    <section
      className="mx-auto w-full max-w-2xl px-5 pb-8 pt-7 sm:px-8"
      aria-busy="true"
      aria-label="記録を読み込んでいます"
    >
      <div className="h-7 w-40 animate-pulse rounded-full bg-[#D5E3D9] motion-reduce:animate-none" />
      <div className="mt-6 h-56 animate-pulse rounded-[1.25rem] border border-[#D5E3D9] bg-white/80 motion-reduce:animate-none" />
      <div className="mt-3 h-11 animate-pulse rounded-2xl bg-[#C9DDD1] motion-reduce:animate-none" />
      <span className="sr-only">読み込み中…</span>
    </section>
  );
}
