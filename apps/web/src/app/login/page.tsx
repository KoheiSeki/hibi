import { signInAction } from "./actions";

export default function LoginPage() {
  return (
    <section className="card">
      <h1>ログイン</h1>
      <form action={signInAction}>
        <label>
          メール
          <input name="email" type="email" autoComplete="email" required />
        </label>
        <label>
          パスワード
          <input
            name="password"
            type="password"
            autoComplete="current-password"
            required
          />
        </label>
        <button type="submit">ログイン</button>
      </form>
    </section>
  );
}
