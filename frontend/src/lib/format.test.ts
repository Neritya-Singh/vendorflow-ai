import { formatDateTime } from "./format";

describe("formatDateTime", () => {
  it("always shows India time with an IST label", () => {
    expect(formatDateTime("2026-11-13T09:34:00Z")).toBe("13 Nov 2026, 3:04 pm IST");
    expect(formatDateTime(null)).toBe("—");
  });
});
