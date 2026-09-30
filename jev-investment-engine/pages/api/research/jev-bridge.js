export default async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");
  if (process.env.VERCEL_ENV !== "preview") {
    return res.status(404).json({ ok: false, error: "preview_only" });
  }
  if (req.method !== "POST") {
    return res.status(405).json({ ok: false, error: "method_not_allowed" });
  }
  if (req.headers["x-research-bridge"] !== "stage4-20260930") {
    return res.status(403).json({ ok: false, error: "bridge_header_required" });
  }
  const secret = process.env.JEV_API_SECRET;
  if (!secret) {
    return res.status(503).json({ ok: false, error: "jev_secret_unavailable" });
  }
  const body = req.body || {};
  const questions = body.questions;
  const state = body.state;
  const runs = body.runs === 1 ? 1 : 3;
  if (state === undefined || !questions || typeof questions !== "object" || Array.isArray(questions)) {
    return res.status(400).json({ ok: false, error: "state_and_questions_required" });
  }
  const raw = JSON.stringify({ state, questions, runs, persist: false });
  if (Buffer.byteLength(raw, "utf8") > 140000) {
    return res.status(413).json({ ok: false, error: "research_payload_too_large" });
  }
  try {
    const upstream = await fetch("https://jev-investment-engine.vercel.app/api/jev", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${secret}`,
        "Content-Type": "application/json"
      },
      body: raw
    });
    const text = await upstream.text();
    res.status(upstream.status);
    res.setHeader("Content-Type", upstream.headers.get("content-type") || "application/json; charset=utf-8");
    return res.send(text);
  } catch {
    return res.status(502).json({ ok: false, error: "jev_proxy_failed" });
  }
}
