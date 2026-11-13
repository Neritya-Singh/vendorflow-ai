import { checkFile } from "./useSlotReading";

const file = (name: string, size = 10) => new File([new Uint8Array(size)], name);

describe("checkFile", () => {
  it("accepts PDF, JPG and PNG up to the limit", () => {
    for (const name of ["a.pdf", "b.JPG", "c.jpeg", "d.png"]) expect(checkFile(file(name), 100)).toBeNull();
  });
  it("explains other types and sizes", () => {
    expect(checkFile(file("e.heic"), 100)).toBe("Upload a PDF, JPG or PNG file.");
    expect(checkFile(file("f.png", 101), 100)).toMatch(/larger than 5 MB/);
  });
});
