import type { ReactNode } from "react";
import Link from "next/link";
import { Noto_Sans_JP } from "next/font/google";

const notoSansJp = Noto_Sans_JP({
  subsets: ["latin"],
  variable: "--font-capture-body",
});

export default function CapturesLayout({ children }: { children: ReactNode }) {
  return (
    <div
      className={`${notoSansJp.variable} relative left-1/2 -my-16 min-h-svh w-screen -translate-x-1/2 bg-[#F4F6F8] text-[#1A1D23] [font-family:var(--font-capture-body),sans-serif]`}
    >
      <header className="sticky top-0 z-30 border-b border-[#D5DCE5] bg-[#F4F6F8]/95 backdrop-blur-md">
        <div className="mx-auto flex h-14 w-full max-w-2xl items-center justify-between px-5 sm:px-8">
          <Link
            href="/captures"
            className="font-sans text-lg font-semibold tracking-[-0.03em] text-[#1A1D23] no-underline outline-none focus-visible:rounded-sm focus-visible:ring-2 focus-visible:ring-[#2F6A4A]"
          >
            Hibi
          </Link>
          <Link
            href="/account"
            className="font-sans text-sm font-medium text-[#4A5870] underline-offset-4 outline-none hover:text-[#1A1D23] hover:underline focus-visible:rounded-sm focus-visible:ring-2 focus-visible:ring-[#2F6A4A]"
          >
            アカウント
          </Link>
        </div>
      </header>

      {children}
    </div>
  );
}
