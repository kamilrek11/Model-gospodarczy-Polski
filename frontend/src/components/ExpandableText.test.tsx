import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ExpandableText, SHORT_LIMIT } from "./ExpandableText";

const LONG = `Pierwsze zdanie opisu stałej. ${"Bardzo długi dalszy ciąg uwagi o źródle i założeniach. ".repeat(8)}`;

describe("ExpandableText", () => {
  it("renders a short text as is, without a disclosure", () => {
    const { container } = render(<ExpandableText text="Krótka uwaga." />);
    expect(screen.getByText("Krótka uwaga.")).toBeInTheDocument();
    expect(container.querySelector("details")).toBeNull();
  });

  it("shows a summary and keeps the whole text in the DOM for a long text", async () => {
    const { container } = render(<ExpandableText text={LONG} />);
    const details = container.querySelector("details");
    expect(details).not.toBeNull();
    expect(details).not.toHaveAttribute("open");
    // the visible lead is short, the full text is still there (no content lost)
    const lead = container.querySelector(".expandable-lead")!;
    expect(lead.textContent!.length).toBeLessThanOrEqual(SHORT_LIMIT + 1);
    expect(container.textContent).toContain(LONG.trim().slice(-30));
    await userEvent.click(screen.getByText("Pokaż więcej"));
    expect(details).toHaveAttribute("open");
  });

  it("cuts the lead at the end of the first sentence when it fits", () => {
    const { container } = render(<ExpandableText text={LONG} />);
    expect(container.querySelector(".expandable-lead")!.textContent).toBe("Pierwsze zdanie opisu stałej.");
  });

  it("falls back to a hard cut with an ellipsis when the first sentence is too long", () => {
    const noStop = "x".repeat(SHORT_LIMIT * 2);
    const { container } = render(<ExpandableText text={noStop} />);
    const lead = container.querySelector(".expandable-lead")!.textContent!;
    expect(lead.endsWith("…")).toBe(true);
    expect(lead.length).toBeLessThanOrEqual(SHORT_LIMIT + 1);
  });
});
