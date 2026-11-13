import { Inbox, MessageSquareText } from "lucide-react";
import { formatDateTime } from "../lib/format";
import type { VendorMessage } from "../lib/types";
import { Card, CardHeader } from "./ui";

/** The vendor message log (V2_02 §8–9). Shared by the vendor page and the case timeline. */
export function MessageList({ messages, audience }: { messages: VendorMessage[]; audience: "vendor" | "admin" }) {
  if (!messages.length) return <p className="px-5 py-4 text-sm text-slate-500">No messages yet.</p>;
  return (
    <ol className="divide-y divide-slate-100">
      {messages.map((m) => (
        <li key={m.id} className="flex gap-3 px-5 py-3">
          <MessageSquareText className="mt-0.5 size-4 shrink-0 text-navy-600" aria-hidden />
          <div className="min-w-0">
            <p className="text-[13px] font-semibold text-slate-900">
              {m.title}
              <span className="font-normal text-slate-500"> · {formatDateTime(m.at)}</span>
            </p>
            <p className="mt-0.5 text-sm leading-relaxed text-slate-700">{m.text}</p>
            {audience === "admin" ? <p className="mt-0.5 text-xs text-slate-500">{m.source} · {m.delivery}</p> : null}
          </div>
        </li>
      ))}
    </ol>
  );
}

export function MessageLog({ messages }: { messages: VendorMessage[] }) {
  return (
    <Card>
      <CardHeader
        title="Messages from our team"
        description="Newest first. We'll add a message here whenever something changes."
        action={<Inbox className="size-4 text-slate-400" aria-hidden />}
      />
      <MessageList messages={messages} audience="vendor" />
    </Card>
  );
}
