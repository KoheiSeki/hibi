"use client";

import "./globals.css";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export default function GlobalError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="ja">
      <body>
        <main className="mx-auto max-w-2xl px-6 py-16">
          <Card>
            <CardHeader>
              <CardTitle>問題が発生しました</CardTitle>
            </CardHeader>
            <CardContent>
              <Button type="button" onClick={reset}>
                再試行
              </Button>
            </CardContent>
          </Card>
        </main>
      </body>
    </html>
  );
}
