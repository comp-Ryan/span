/**
 * Spectrum bridge: lets the Python backend text through a Photon Spectrum (stable) project.
 *
 *   SPECTRUM_PROJECT_ID / SPECTRUM_PROJECT_SECRET   from the Photon dashboard, Settings → Credentials
 *   BRIDGE_PORT (8071)                               POST /send {"to": "+1…", "text": "…"} → {"message_id","space_id"}
 *   SPAN_INBOUND_URL + PHOTON_WEBHOOK_TOKEN          incoming texts are forwarded to the backend as Photon-style events
 *
 * A shared iMessage line can only answer a phone that texted it first; the DM space is reused.
 */
import { Spectrum } from "spectrum-ts";
import { imessage } from "spectrum-ts/providers/imessage";

const PORT = Number(process.env.BRIDGE_PORT || 8071);
const INBOUND = process.env.SPAN_INBOUND_URL || "http://127.0.0.1:8000/inbound/photon";
const TOKEN = process.env.PHOTON_WEBHOOK_TOKEN || "";

const app = await Spectrum({ providers: [imessage.config()] });
const im = imessage(app);
const spaces = new Map<string, any>();        // phone digits → DM space (a shared line can only answer inside the thread the phone started)
const sent = new Map<string, { to: string; text: string; at: number }>();
let inbound = 0;
const digits = (handle: string) => handle.replace(/\D/g, "");

async function dmFor(to: string) {
  const known = spaces.get(digits(to));
  if (known) return known;
  // No inbound thread yet: ask Spectrum for the DM. On a shared line this is refused ("Target not allowed") until the phone texts the line.
  const user = await im.user(to);
  const space = await im.space.create(user);
  spaces.set(digits(to), space);
  return space;
}

Bun.serve({
  port: PORT,
  hostname: "127.0.0.1",
  async fetch(req) {
    const url = new URL(req.url);
    if (req.method === "GET" && url.pathname === "/health") return Response.json({ ok: true, platform: "imessage", spaces: spaces.size, inbound });
    if (req.method === "POST" && url.pathname === "/send") {
      const body = await req.json().catch(() => ({}));
      const to = String(body.to || "").trim(), text = String(body.text || "");
      if (!/^\+\d{8,15}$/.test(to) || !text) return Response.json({ error: "to must be E.164 and text non-empty" }, { status: 422 });
      try {
        const space = await dmFor(to);
        const result: any = await space.send(text);
        const id = String(result?.id ?? result?.messageId ?? `spectrum-${Date.now()}`);
        sent.set(id, { to, text, at: Date.now() });
        return Response.json({ message_id: id, space_id: String(space.id ?? to), status: "sent" });
      } catch (e) {
        console.error("send failed", e);
        const msg = String((e as Error).message || e);
        const hint = /not allowed/i.test(msg) ? " — shared iMessage line: the phone must text this line first; keep that thread, then retry" : "";
        return Response.json({ error: msg + hint }, { status: 502 });
      }
    }
    return new Response("not found", { status: 404 });
  },
});
console.log(`spectrum bridge on http://127.0.0.1:${PORT} (project ${(process.env.SPECTRUM_PROJECT_ID || "").slice(0, 8)}…)`);

// Replies from the phone go to the backend's inbound webhook in the shape its Photon handler reads.
for await (const [space, message] of app.messages) {
  inbound += 1;
  console.log(`event #${inbound}: platform=${message.platform} type=${message.content?.type} from=${String(message.sender?.id ?? "?")}`);
  if (message.platform !== "imessage" || message.content.type !== "text") continue;
  const handle = String(message.sender?.id ?? "");
  spaces.set(digits(handle) || handle, space);
  console.log(`inbound from ${handle} in space ${String(space.id ?? "?")}`);
  const event = { type: "message.received", data: { id: `spectrum:${message.id}`, space: { id: String(space.id ?? handle) },
    sentBy: { kind: "human", handle }, content: { type: "text", text: message.content.text }, platform: "imessage" } };
  console.log(`[${handle}] ${message.content.text}`);
  if (!TOKEN) continue;
  try {
    const r = await fetch(`${INBOUND}?token=${encodeURIComponent(TOKEN)}`, { method: "POST", headers: { "content-type": "application/json", "x-spectrum-bridge": "1" }, body: JSON.stringify(event) });
    if (!r.ok) console.error("backend refused inbound", r.status, await r.text());
  } catch (e) { console.error("backend unreachable", e); }
}
