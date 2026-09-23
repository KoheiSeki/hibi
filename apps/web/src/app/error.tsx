"use client";
export default function ErrorPage({
  reset,
}: {
  error: Error;
  reset: () => void;
}) {
  return (
    <section className="card">
      <h1>問題が発生しました</h1>
      <button onClick={reset}>再試行</button>
    </section>
  );
}
