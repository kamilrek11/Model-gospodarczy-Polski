import { describe, expect, it } from "vitest";
import { fmtDate, fmtMld, fmtPct, fmtSignedMld } from "./format";

describe("pl-PL formatting", () => {
  it("number formatting pl-PL uses decimal comma and sign", () => {
    expect(fmtMld(12345.5)).toBe("12\u00a0345,50");
    expect(fmtSignedMld(2.5)).toBe("+2,50");
    expect(fmtSignedMld(-0.125)).toBe("-0,13");
    expect(fmtPct(2.3148)).toBe("+2,3%");
    expect(fmtPct(-0.04)).toBe("0,0%");
  });
  it("formats dates dd.mm.yyyy", () => {
    expect(fmtDate("2026-10-09T12:00:00Z")).toBe("09.10.2026");
  });
});
