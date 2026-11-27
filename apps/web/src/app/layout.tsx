import type { Metadata } from "next";
import "./globals.css";
import { Geist } from "next/font/google";
import { cn } from "@/lib/utils";

const geist = Geist({subsets:['latin'],variable:'--font-sans'});

export const metadata: Metadata = {
  title: "Hibi",
  description: "Your everyday copilot",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ja" className={cn("font-sans", geist.variable)}>
      <body>
        <main className="mx-auto max-w-2xl px-6 py-16">{children}</main>
      </body>
    </html>
  );
}
