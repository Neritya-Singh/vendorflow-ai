import { useRef, useState } from "react";
import type { SlotActivity } from "../components/vendor/DocumentSlot";
import { ApiError, moveDraftFile, uploadDraftFile, type ReadingBase } from "./api";
import type { Credentials, DraftStreamMessage, DraftView, Slot } from "./types";

const SLOTS: Slot[] = ["GST", "BANK"];
const READING_ORDER = ["U1", "U2", "U3"];
const READING_LABEL: Record<string, string> = { U1: "Uploading", U2: "Identifying the document", U3: "Reading the details" };
// A move copies the stored file and reuses its reading: no upload, no new reading.
const MOVING_LABEL: Record<string, string> = { U1: "Moving your file", U2: "Moving your file", U3: "Moving your file" };

/** Storing runs alongside reading, so stages can finish out of order: never move backwards. */
export function nextActivity(current: SlotActivity | undefined, filename: string, stageId: string, event: string,
  labels: Record<string, string> = READING_LABEL): SlotActivity {
  const at = READING_ORDER.indexOf(stageId);
  const progress = Math.round(((at + (event !== "STARTED" ? 1 : 0.5)) / 3) * 100);
  if (current && current.progress >= progress) return current;
  return { filename, stage: labels[stageId] ?? "Working", progress };
}

/** Accepts a PDF, JPG or PNG up to the size limit; returns the message to show, or null. */
export function checkFile(file: File, maxBytes: number): string | null {
  if (!/\.(pdf|jpe?g|png)$/i.test(file.name)) return "Upload a PDF, JPG or PNG file.";
  if (file.size > maxBytes) return "This file is larger than 5 MB. Upload a smaller file or photo.";
  return null;
}

/**
 * Phone photos are often over 5 MB or in a format we don't take (e.g. HEIC). Re-encode
 * such a photo in the browser to a JPEG of at most 3000 px (this also drops its EXIF and
 * location data). PDFs and small JPG/PNG files are sent unchanged.
 */
export async function preparePhoto(file: File, maxBytes: number): Promise<File> {
  const isImage = file.type.startsWith("image/") || /\.(jpe?g|png|heic|heif|webp)$/i.test(file.name);
  const accepted = /\.(jpe?g|png)$/i.test(file.name);
  if (!isImage || (accepted && file.size <= maxBytes) || typeof createImageBitmap !== "function") return file;
  try {
    const bitmap = await createImageBitmap(file);
    const scale = Math.min(1, 3000 / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    canvas.getContext("2d")?.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    for (const quality of [0.88, 0.8, 0.7]) {
      const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/jpeg", quality));
      if (blob && blob.size <= maxBytes) return new File([blob], file.name.replace(/\.[^.]+$/, "") + ".jpg", { type: "image/jpeg" });
    }
  } catch {
    // Not decodable here: send as is; the type/size check explains what to do.
  }
  return file;
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

  const handler = (slots: Slot[], filename: (s: Slot) => string, labels = READING_LABEL) => (m: DraftStreamMessage) => {
    if (m.type === "stage") {
      setActivity((a) => {
        const next = { ...a };
        for (const s of slots) next[s] = nextActivity(a[s], filename(s), m.stage_id, m.event, labels);
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

  const upload = async (slot: Slot, chosen: File) => {
    if (!creds) return;
    setSlotErrors((e) => ({ ...e, [slot]: undefined }));
    const file = await preparePhoto(chosen, maxBytes);
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
    setActivity(Object.fromEntries(slots.map((s) => [s, { filename: landing[s] ?? "", stage: "Moving your file", progress: 10 }])));
    try {
      await moveDraftFile(creds, slot, handler(slots, (s) => landing[s] ?? "", MOVING_LABEL), base);
    } catch (e) {
      setSlotErrors({ [slot]: e instanceof Error ? e.message : "Couldn't move the file." });
    } finally {
      finish(SLOTS);
    }
  };

  const retry = (slot: Slot) => (lastFiles.current[slot] ? () => void upload(slot, lastFiles.current[slot]!) : null);
  return { activity, slotErrors, upload, move, retry, busy: Object.keys(activity).length > 0 };
}
