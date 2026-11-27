// @vitest-environment jsdom

import type { CaptureResponse } from "@hibi/api-client";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { markScenarioDoneActionMock } = vi.hoisted(() => ({
  markScenarioDoneActionMock: vi.fn(),
}));

vi.mock("@/features/capture/actions", () => ({
  markScenarioDoneAction: markScenarioDoneActionMock,
}));

import { TodayList } from "@/features/capture/today-list";

function todayCapture(id: string, title: string): CaptureResponse {
  return {
    id,
    rawText: title,
    status: "completed",
    createdAt: "2026-11-10T05:00:00Z",
    updatedAt: "2026-11-10T05:00:00Z",
    scenario: {
      route: "shopping",
      status: "proposed",
      title,
      policyVersion: "capture-scenario-v1",
      dueAt: null,
      doneAt: null,
    },
  };
}

const milk = todayCapture("capture-1", "牛乳");
const eggs = todayCapture("capture-2", "卵");

async function clickDone(index: number) {
  const button = screen.getAllByRole("button", { name: "完了にする" })[index];
  if (!button) {
    throw new Error(`done button ${index} not found`);
  }
  await act(async () => {
    fireEvent.click(button);
  });
  // 行は畳む動きのあとに外れる
  await act(async () => {
    vi.advanceTimersByTime(250);
  });
}

describe("TodayList", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    cleanup();
  });

  it("renders a row with a done button for each capture", () => {
    render(<TodayList items={[milk, eggs]} />);

    expect(screen.getByText("牛乳")).toBeTruthy();
    expect(screen.getByText("卵")).toBeTruthy();
    expect(screen.getAllByRole("button", { name: "完了にする" })).toHaveLength(
      2,
    );
  });

  it("shows the date for a due time that is not today and a label when there is none", () => {
    vi.setSystemTime(new Date("2026-11-10T06:00:00Z"));
    const overdue: CaptureResponse = {
      ...todayCapture("capture-3", "提出"),
      scenario: {
        ...(milk.scenario as NonNullable<CaptureResponse["scenario"]>),
        title: "提出",
        dueAt: "2026-11-09T00:00:00Z",
      },
    };
    const dueToday: CaptureResponse = {
      ...overdue,
      id: "capture-4",
      scenario: {
        ...(overdue.scenario as NonNullable<CaptureResponse["scenario"]>),
        title: "電話",
        dueAt: "2026-11-10T00:30:00Z",
      },
    };
    render(<TodayList items={[overdue, dueToday, milk]} />);

    expect(screen.getByText("昨日 09:00")).toBeTruthy();
    expect(screen.getByText("09:30")).toBeTruthy();
    expect(screen.getByText("期限なし")).toBeTruthy();
  });

  it("marks the clicked capture as done and removes only that row", async () => {
    markScenarioDoneActionMock.mockResolvedValue({
      status: "success",
      data: milk,
    });
    render(<TodayList items={[milk, eggs]} />);

    await clickDone(0);

    expect(markScenarioDoneActionMock).toHaveBeenCalledWith("capture-1");
    expect(screen.queryByText("牛乳")).toBeNull();
    expect(screen.getByText("卵")).toBeTruthy();
  });

  it("keeps the row and shows the failure in an alert", async () => {
    markScenarioDoneActionMock.mockResolvedValue({
      status: "error",
      message: "完了にできませんでした。",
    });
    render(<TodayList items={[milk, eggs]} />);

    await clickDone(0);

    expect(screen.getByRole("alert").textContent).toContain(
      "完了にできませんでした。",
    );
    expect(screen.getByText("牛乳")).toBeTruthy();
    expect(screen.getByText("卵")).toBeTruthy();
  });

  it("shows the empty state after the last row is done", async () => {
    markScenarioDoneActionMock.mockResolvedValue({
      status: "success",
      data: milk,
    });
    render(<TodayList items={[milk]} />);

    await clickDone(0);

    expect(screen.getByText("今日やることはありません")).toBeTruthy();
  });
});
