import { formatAge, formatDateTime } from "./format";

describe("formatDateTime", () => {
  it("always shows India time with an IST label", () => {
    expect(formatDateTime("2026-11-13T09:34:00Z")).toBe("13 Nov 2026, 3:04 pm IST");
    expect(formatDateTime(null)).toBe("—");
  });
});

describe("formatAge", () => {
  it("says how long a case has waited in plain words", () => {
    const now = Date.parse("2026-11-13T12:00:00Z");
    expect(formatAge("2026-11-13T11:40:00Z", now)).toBe("20 min");
    expect(formatAge("2026-11-13T09:00:00Z", now)).toBe("3 hours");
    expect(formatAge("2026-11-11T12:00:00Z", now)).toBe("2 days");
    expect(formatAge(null, now)).toBe("—");
  });
});
