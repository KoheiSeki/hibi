import type { ReactNode } from "react";
import Link from "next/link";
import { Noto_Sans_JP, Shippori_Mincho } from "next/font/google";

const notoSansJp = Noto_Sans_JP({
  subsets: ["latin"],
  variable: "--font-capture-body",
});

const shipporiMincho = Shippori_Mincho({
  subsets: ["latin"],
  weight: "500",
  variable: "--font-capture-display",
});

export default function CapturesLayout({ children }: { children: ReactNode }) {
  return (
    <div
      className={`${notoSansJp.variable} ${shipporiMincho.variable} relative left-1/2 -my-16 min-h-svh w-screen -translate-x-1/2 bg-[#EEF3EF] text-[#15201A] [font-family:var(--font-capture-body),sans-serif]`}
    >
      <header className="sticky top-0 z-30 border-b border-[#D5E3D9] bg-[#EEF3EF]/90 backdrop-blur-md">
        <div className="mx-auto flex h-14 w-full max-w-2xl items-center justify-between px-5 sm:px-8">
          <Link
            href="/captures"
            className="text-[1.35rem] font-medium tracking-[0.08em] text-[#15201A] no-underline outline-none [font-family:var(--font-capture-display),serif] focus-visible:rounded-sm focus-visible:ring-2 focus-visible:ring-[#1E6B43]"
          >
            Hibi
          </Link>
          <nav className="flex items-center gap-5">
            <Link
              href="/captures/today"
              className="font-sans text-sm font-medium text-[#5A6A62] underline-offset-4 outline-none hover:text-[#15201A] hover:underline focus-visible:rounded-sm focus-visible:ring-2 focus-visible:ring-[#1E6B43]"
            >
              今日
            </Link>
            <Link
              href="/account"
              className="font-sans text-sm font-medium text-[#5A6A62] underline-offset-4 outline-none hover:text-[#15201A] hover:underline focus-visible:rounded-sm focus-visible:ring-2 focus-visible:ring-[#1E6B43]"
            >
              アカウント
            </Link>
          </nav>
        </div>
      </header>

      {children}
    </div>
  );
}
