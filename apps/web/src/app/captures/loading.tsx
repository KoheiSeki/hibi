import { CaptureListSkeleton } from "@/features/capture/capture-list-skeleton";

export default function CapturesLoading() {
  return (
    <section
      className="mx-auto w-full max-w-2xl px-5 pb-32 pt-6 sm:px-8"
    >
      <div className="h-4 w-24 animate-pulse rounded-full bg-[#D5DCE5] motion-reduce:animate-none" />
      <div className="mt-5">
        <CaptureListSkeleton />
      </div>
    </section>
  );
}
