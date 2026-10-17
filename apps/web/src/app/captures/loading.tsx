import { CaptureListSkeleton } from "@/features/capture/capture-list-skeleton";

export default function CapturesLoading() {
  return (
    <section
      className="mx-auto w-full max-w-2xl px-5 pb-32 pt-6 sm:px-8"
    >
      <div className="h-7 w-36 animate-pulse rounded-full bg-[#D5E3D9] motion-reduce:animate-none" />
      <div className="mt-5">
        <CaptureListSkeleton />
      </div>
    </section>
  );
}
