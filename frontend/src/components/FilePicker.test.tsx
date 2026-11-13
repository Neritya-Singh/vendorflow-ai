import { validatePdf } from "./FilePicker";

const file = (name: string, size: number, type = "application/pdf") => new File([new Uint8Array(size)], name, { type });

describe("validatePdf", () => {
  it("accepts a normal PDF", () => expect(validatePdf(file("gst.pdf", 1000))).toBeNull());
  it("rejects other extensions", () => expect(validatePdf(file("gst.png", 10, "image/png"))).toMatch(/Only PDF/));
  it("rejects empty files", () => expect(validatePdf(file("gst.pdf", 0))).toMatch(/empty/));
  it("rejects files over 5 MB", () => expect(validatePdf(file("gst.pdf", 5 * 1024 * 1024 + 1))).toMatch(/limit is 5 MB/));
});
