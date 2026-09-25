import Link from "next/link";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export default function NotFound() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>ページが見つかりません</CardTitle>
        <CardDescription>
          リンクが古いか、URL が間違っている可能性があります。
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Button asChild variant="outline">
          <Link href="/">トップへ戻る</Link>
        </Button>
      </CardContent>
    </Card>
  );
}
