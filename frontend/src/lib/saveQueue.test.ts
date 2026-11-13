import { describe, expect, it } from "vitest";
import { createSaveQueue, mergeBodies, type SaveBody } from "./saveQueue";

const contact = (name: string) => ({ name, email: "", phone: "" });

describe("createSaveQueue", () => {
  it("sends the first save at once and merges the ones that pile up behind it", async () => {
    const sent: SaveBody[] = [];
    let release: () => void = () => undefined;
    const queue = createSaveQueue((body) => {
      sent.push(body);
      return sent.length === 1 ? new Promise<void>((r) => (release = r)) : Promise.resolve();
    });
    void queue.push({ contact: contact("A") });
    void queue.push({ contact: contact("AB") });
    void queue.push({ changes: { ifsc: "DEMO0123456" } });
    release();
    await queue.idle();
    expect(sent).toEqual([{ contact: contact("A") }, { contact: contact("AB"), changes: { ifsc: "DEMO0123456" } }]);
  });

  it("keeps a reset and a change of the same field in order", async () => {
    const sent: SaveBody[] = [];
    let release: () => void = () => undefined;
    const queue = createSaveQueue((body) => {
      sent.push(body);
      return sent.length === 1 ? new Promise<void>((r) => (release = r)) : Promise.resolve();
    });
    void queue.push({ contact: contact("A") });
    void queue.push({ changes: { ifsc: "X" } });
    void queue.push({ reset: ["ifsc"] });
    release();
    await queue.idle();
    expect(sent).toEqual([{ contact: contact("A") }, { changes: { ifsc: "X" } }, { reset: ["ifsc"] }]);
  });

  it("idle resolves at once when nothing is queued, and after a failed save", async () => {
    const queue = createSaveQueue(() => Promise.reject(new Error("offline")));
    await queue.idle();
    await queue.push({ contact: contact("A") });
    await queue.idle();
  });

  it("merges changes, resets and the latest contact", () => {
    expect(mergeBodies({ changes: { gstin: "A" }, reset: ["ifsc"] }, { changes: { legal_name: "B" }, contact: contact("C") }))
      .toEqual({ changes: { gstin: "A", legal_name: "B" }, reset: ["ifsc"], contact: contact("C") });
  });
});
