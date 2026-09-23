import Link from "next/link";

export default function HomePage() {
  return (
    <section className="card">
      <p>毎日を、少し軽やかに。</p>
      <h1>Hibi</h1>
      <p>日々の入力を整理するコパイロットの基盤です。</p>
      <Link href="/login">ログイン</Link>
    </section>
  );
}
