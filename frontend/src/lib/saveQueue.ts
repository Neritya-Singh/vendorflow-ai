import type { Contact, DraftFieldKey } from "./types";

export interface SaveBody {
  changes?: Partial<Record<DraftFieldKey, string>>;
  reset?: DraftFieldKey[];
  contact?: Contact;
  declaration?: boolean;
}

/** Two waiting saves can become one when neither undoes a field the other sets. */
function mergeable(a: SaveBody, b: SaveBody): boolean {
  const aReset = new Set(a.reset ?? []);
  const bReset = new Set(b.reset ?? []);
  return !Object.keys(b.changes ?? {}).some((k) => aReset.has(k as DraftFieldKey))
    && !Object.keys(a.changes ?? {}).some((k) => bReset.has(k as DraftFieldKey));
}

export function mergeBodies(a: SaveBody, b: SaveBody): SaveBody {
  const out: SaveBody = {};
  if (a.changes || b.changes) out.changes = { ...a.changes, ...b.changes };
  if (a.reset || b.reset) out.reset = [...new Set([...(a.reset ?? []), ...(b.reset ?? [])])];
  if (a.contact || b.contact) out.contact = b.contact ?? a.contact; // contact is always sent whole
  if (a.declaration !== undefined || b.declaration !== undefined) out.declaration = b.declaration ?? a.declaration;
  return out;
}

/**
 * Saves run one at a time, in order (a later edit never lands before an earlier one).
 * Every round trip to the server is slow, so saves that pile up while one is in flight
 * are merged into a single request. `idle()` resolves once everything queued is saved.
 */
export function createSaveQueue(send: (body: SaveBody) => Promise<void>) {
  const waiting: SaveBody[] = [];
  let running: Promise<void> | null = null;

  const pump = async () => {
    while (waiting.length) {
      const body = waiting.shift()!;
      await send(body).catch(() => undefined); // the sender reports its own errors
    }
    running = null;
  };

  return {
    push(body: SaveBody): Promise<void> {
      const last = waiting[waiting.length - 1];
      if (last && mergeable(last, body)) waiting[waiting.length - 1] = mergeBodies(last, body);
      else waiting.push(body);
      if (!running) running = pump();
      return running;
    },
    idle(): Promise<void> {
      return running ?? Promise.resolve();
    },
  };
}
