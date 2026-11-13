import { isTypingTarget } from "./useShortcuts";

describe("isTypingTarget", () => {
  it("ignores shortcuts in text fields but not on checkboxes or the page", () => {
    const text = document.createElement("input");
    const box = document.createElement("input");
    box.type = "checkbox";
    expect(isTypingTarget(text)).toBe(true);
    expect(isTypingTarget(document.createElement("textarea"))).toBe(true);
    expect(isTypingTarget(box)).toBe(false);
    expect(isTypingTarget(document.body)).toBe(false);
  });
});
