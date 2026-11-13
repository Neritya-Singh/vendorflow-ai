import { useRef, useState } from "react";
import type { SlotActivity } from "../components/vendor/DocumentSlot";
import { ApiError, moveDraftFile, uploadDraftFile, type ReadingBase } from "./api";
import type { Credentials, DraftStreamMessage, DraftView, Slot } from "./types";

const SLOTS: Slot[] = ["GST", "BANK"];
const READING_ORDER = ["U1", "U2", "U3"];
const READING_LABEL: Record<string, string> = { U1: "Uploading", U2: "Identifying the document", U3: "Reading the details" };

/** Accepts a PDF up to the size limit; returns the message to show, or null. */
export function checkFile(file: File, maxBytes: number): string | null {
  if (!/\.pdf$/i.test(file.name)) return "Upload a PDF. Photos and scans are supported soon.";
  if (file.size > maxBytes) return "This file is larger than 5 MB. Upload a smaller PDF.";
  return null;
}

/**
 * Per-slot upload, reading progress and "Move it" for the upload-first draft and for
 * the fix page after submit. Every status comes from the server's stage events.
 */
export function useSlotReading<V extends DraftView>({ creds, base, maxBytes, adopt }: {
  creds: Credentials | null;
  base: ReadingBase;
  maxBytes: number;
  adopt: (view: V) => void;
}) {
  const [activity, setActivity] = useState<Partial<Record<Slot, SlotActivity>>>({});
  const [slotErrors, setSlotErrors] = useState<Partial<Record<Slot, string>>>({});
  const lastFiles = useRef<Partial<Record<Slot, File>>>({});

  const handler = (slots: Slot[], filename: (s: Slot) => string) => (m: DraftStreamMessage) => {
    if (m.type === "stage") {
      const at = READING_ORDER.indexOf(m.stage_id);
      const done = m.event !== "STARTED";
      setActivity((a) => {
        const next = { ...a };
        for (const s of slots) {
          next[s] = { filename: filename(s), stage: READING_LABEL[m.stage_id] ?? "Working", progress: Math.round(((at + (done ? 1 : 0.5)) / 3) * 100) };
        }
        return next;
      });
    } else if (m.type === "result") {
      adopt(m.data as V);
    } else if (m.type === "error") {
      setSlotErrors((e) => ({ ...e, ...Object.fromEntries(slots.map((s) => [s, m.message])) }));
    }
  };

  const finish = (slots: Slot[]) =>
    setActivity((a) => {
      const next = { ...a };
      for (const s of slots) delete next[s];
      return next;
    });

  const upload = async (slot: Slot, file: File) => {
    if (!creds) return;
    setSlotErrors((e) => ({ ...e, [slot]: undefined }));
    const problem = checkFile(file, maxBytes);
    if (problem) {
      setSlotErrors((e) => ({ ...e, [slot]: problem }));
      return;
    }
    lastFiles.current[slot] = file;
    setActivity((a) => ({ ...a, [slot]: { filename: file.name, stage: "Uploading", progress: 8 } }));
    try {
      await uploadDraftFile(creds, slot, file, handler([slot], () => file.name), base);
    } catch (e) {
      setSlotErrors((x) => ({ ...x, [slot]: e instanceof ApiError && e.status ? e.message : "The upload didn't finish. Check your connection and try again." }));
    } finally {
      finish([slot]);
    }
  };

  const move = async (slot: Slot, view: DraftView) => {
    if (!creds) return;
    const other: Slot = slot === "GST" ? "BANK" : "GST";
    // The file in `slot` goes to `other`; a file already in `other` comes back to `slot`.
    const landing: Partial<Record<Slot, string>> = { [other]: view.files[slot]?.filename ?? "" };
    if (view.files[other]) landing[slot] = view.files[other]!.filename;
    const slots = Object.keys(landing) as Slot[];
    setSlotErrors({});
    try {
      await moveDraftFile(creds, slot, handler(slots, (s) => landing[s] ?? ""), base);
    } catch (e) {
      setSlotErrors({ [slot]: e instanceof Error ? e.message : "Couldn't move the file." });
    } finally {
      finish(SLOTS);
    }
  };

  const retry = (slot: Slot) => (lastFiles.current[slot] ? () => void upload(slot, lastFiles.current[slot]!) : null);
  return { activity, slotErrors, upload, move, retry, busy: Object.keys(activity).length > 0 };
}
