"use client";

import type { CaptureResponse } from "@hibi/api-client";
import Link from "next/link";
import { useEffect, useRef, useState, useTransition } from "react";

import { Button } from "@/components/ui/button";
import { formatJstDueLabel } from "@/lib/date-time";

import { markScenarioDoneAction } from "./actions";
import { TodayEmptyState } from "./today-empty-state";

const LEAVE_DURATION_MS = 200;

function prefersReducedMotion(): boolean {
  return (
    window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false
  );
}

type TodayListProps = {
  items: readonly CaptureResponse[];
};

/**
 * 今日やることを、糸と節の一覧で出し、行ごとに完了にできるようにする。
 *
 * 完了にした行は、API が成功を返したあとに、短く畳んでから一覧から外す。動きを
 * 減らす設定のときは、すぐに外す。失敗したときは行を残し、
 * 一覧の下にエラーを出す。サーバー側のデータが変わったときは、呼び出し側が
 * `key` を変えて、この state を作り直す。
 *
 * @param props.items - 優先度の高い順の記録。シナリオを含む。
 */
export function TodayList({ items: initialItems }: TodayListProps) {
  const [items, setItems] = useState<readonly CaptureResponse[]>(initialItems);
  const [error, setError] = useState<string | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [leavingId, setLeavingId] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const leaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (leaveTimer.current !== null) {
        clearTimeout(leaveTimer.current);
      }
    },
    [],
  );

  function handleDone(captureId: string) {
    if (pending) {
      return;
    }

    setError(null);
    setPendingId(captureId);
    startTransition(async () => {
      const result = await markScenarioDoneAction(captureId);
      setPendingId(null);
      if (result.status === "error") {
        setError(result.message);
        return;
      }
      const removeRow = () => {
        setItems((current) => current.filter(({ id }) => id !== captureId));
        setLeavingId(null);
      };
      if (prefersReducedMotion()) {
        removeRow();
        return;
      }
      setLeavingId(captureId);
      leaveTimer.current = setTimeout(removeRow, LEAVE_DURATION_MS);
    });
  }

  if (items.length === 0) {
    return <TodayEmptyState />;
  }

  return (
    <div>
      <ul className="relative" aria-label="今日やること">
        {items.map((item, index) => {
          const dueAt = item.scenario?.dueAt;
          const isLeaving = leavingId === item.id;
          const threadClass =
            items.length === 1
              ? "hidden"
              : index === 0
                ? "top-8 bottom-0"
                : index === items.length - 1
                  ? "top-0 h-8"
                  : "top-0 bottom-0";
          return (
            <li
              key={item.id}
              className={`grid transition-[grid-template-rows,opacity] duration-200 ease-out motion-reduce:transition-none ${
                isLeaving
                  ? "grid-rows-[0fr] opacity-0"
                  : "grid-rows-[1fr] opacity-100"
              }`}
            >
              <div className="relative min-h-0 overflow-hidden">
                <span
                  aria-hidden="true"
                  className={`absolute left-[0.42rem] w-px bg-[#D5E3D9] ${threadClass}`}
                />
                <div className="grid min-h-16 grid-cols-[minmax(0,1fr)_auto] items-start gap-3 py-4">
                  <Link
                    href={`/captures/${item.id}`}
                    className="group grid grid-cols-[1.15rem_4.6rem_minmax(0,1fr)] items-start gap-3 text-[#15201A] no-underline outline-none"
                  >
                    <span
                      aria-hidden="true"
                      className="relative z-10 mt-1.5 size-2.5 justify-self-center rounded-full bg-[#1E6B43] ring-4 ring-[#EEF3EF] transition-transform group-hover:scale-125"
                    />
                    {dueAt ? (
                      <time
                        dateTime={dueAt}
                        className="pt-0.5 text-sm font-medium tabular-nums text-[#5A6A62]"
                      >
                        {formatJstDueLabel(dueAt)}
                      </time>
                    ) : (
                      <span className="pt-0.5 text-sm text-[#5A6A62]">
                        期限なし
                      </span>
                    )}
                    <span className="line-clamp-2 text-[1.0625rem] leading-7 group-hover:text-[#1E6B43] group-focus-visible:rounded-md group-focus-visible:ring-2 group-focus-visible:ring-[#1E6B43]">
                      {item.scenario?.title ?? item.rawText}
                    </span>
                  </Link>
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() => handleDone(item.id)}
                    disabled={pending}
                    className="h-8 rounded-full px-3 text-sm text-[#1E6B43] hover:bg-[#F7FBF8] hover:text-[#1E6B43]"
                  >
                    {pendingId === item.id ? "完了しています" : "完了にする"}
                  </Button>
                </div>
              </div>
            </li>
          );
        })}
      </ul>

      {error ? (
        <p className="mt-4 text-center text-sm text-destructive" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
