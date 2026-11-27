"use client";

import { useFormStatus } from "react-dom";
import type { VariantProps } from "class-variance-authority";
import { Button, buttonVariants } from "@/components/ui/button";

type FormSubmitButtonProps = React.ComponentProps<"button"> &
	VariantProps<typeof buttonVariants> & {
		/** 送信中に表示するラベル。未指定のときは children のまま */
		pendingLabel?: React.ReactNode;
	};

export function FormSubmitButton({
	pendingLabel,
	children,
	...props
}: FormSubmitButtonProps) {
	const { pending } = useFormStatus();
	return (
		<Button {...props} type="submit" disabled={pending}>
			{pending && pendingLabel != null ? pendingLabel : children}
		</Button>
	);
}
