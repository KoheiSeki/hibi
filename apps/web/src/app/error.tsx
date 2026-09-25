"use client";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export default function ErrorPage({
  reset,
}: {
  error: Error;
  reset: () => void;
}) {
  return (
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
  );
}
