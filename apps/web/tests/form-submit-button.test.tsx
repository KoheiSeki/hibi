import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

vi.mock("react-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-dom")>();
  return {
    ...actual,
    useFormStatus: () => ({
      pending: true,
      data: null,
      method: null,
      action: null,
    }),
  };
});

import { FormSubmitButton } from "@/components/ui/form-submit-button";

describe("FormSubmitButton", () => {
  it("disables the button and shows its pending label while submitting", () => {
    const html = renderToStaticMarkup(
      <FormSubmitButton pendingLabel="ログイン中…">ログイン</FormSubmitButton>,
    );

    expect(html).toContain('disabled=""');
    expect(html).toContain("ログイン中…");
    expect(html).not.toContain(">ログイン</button>");
  });
});
