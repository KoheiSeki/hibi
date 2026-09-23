import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: "Hibi",
  description: "Your everyday copilot",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ja">
      <body>
        <main>{children}</main>
      </body>
    </html>
  );
}
