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

type AuthFrameProps = {
	title: string;
	description?: string;
	children: ReactNode;
};

export function AuthFrame({ title, description, children }: AuthFrameProps) {
	return (
		<div
			className={`${notoSansJp.variable} ${shipporiMincho.variable} relative left-1/2 -my-16 min-h-svh w-screen -translate-x-1/2 bg-[#EEF3EF] text-[#15201A] [font-family:var(--font-capture-body),sans-serif]`}
		>
			<header className="mx-auto flex h-14 w-full max-w-md items-center px-5">
				<Link
					href="/"
					className="text-[1.35rem] font-medium tracking-[0.08em] text-[#15201A] no-underline outline-none [font-family:var(--font-capture-display),serif] focus-visible:rounded-sm focus-visible:ring-2 focus-visible:ring-[#1E6B43]"
				>
					Hibi
				</Link>
			</header>
			<main className="mx-auto w-full max-w-md px-5 pb-16 pt-8">
				<span
					aria-hidden="true"
					className="mb-5 block size-2.5 rounded-full bg-[#1E6B43] ring-4 ring-[#D5E3D9]"
				/>
				<h1 className="text-[1.65rem] font-medium leading-none tracking-[0.04em] [font-family:var(--font-capture-display),serif]">
					{title}
				</h1>
				{description ? (
					<p className="mt-3 text-sm leading-6 text-[#5A6A62]">{description}</p>
				) : null}
				<div className="mt-8 rounded-[1.4rem] border border-[#D5E3D9] bg-[#F7FBF8] p-5 shadow-[0_16px_40px_rgb(21_32_26/0.08)]">
					{children}
				</div>
			</main>
		</div>
	);
}
