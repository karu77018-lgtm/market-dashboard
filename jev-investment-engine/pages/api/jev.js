const GATEWAY_URL = "https://ai-gateway.vercel.sh/v1/evaluate";
const MODEL = "typesafe-ai/jev";

function mean(values) {
  if (!values.length) return null;
  return values.reduce((a, b) => a + b, 0) / values.length;
}

function std(values) {
  if (values.length < 2) return 0;
  const m = mean(values);
  const variance = values.reduce((sum, value) => sum + (value - m) ** 2, 0) / values.length;
  return Math.sqrt(variance);
}

function getNumeric(answer) {
  if (typeof answer === "number" && Number.isFinite(answer)) return answer;
  if (!answer || typeof answer !== "object") return null;
  for (const key of ["probability", "noul", "score", "confidence"]) {
    if (typeof answer[key] === "number" && Number.isFinite(answer[key])) return answer[key];
  }
  return null;
}

function getChoice(answer) {
  if (!answer || typeof answer !== "object") return null;
  if (typeof answer.choice === "string") return answer.choice;
  if (typeof answer.value === "string") return answer.value;
  return null;
}

function aggregateRuns(runs) {
  const questionIds = new Set();
  for (const run of runs) {
    const answers = run?.answers;
    if (!answers || typeof answers !== "object") continue;
    Object.keys(answers).forEach((id) => questionIds.add(id));
  }

  const aggregate = {};
  for (const id of questionIds) {
    const answers = runs.map((run) => run?.answers?.[id]).filter((a) => a !== undefined);
    const numeric = answers.map(getNumeric).filter((v) => typeof v === "number" && Number.isFinite(v));
    const choices = answers.map(getChoice).filter((v) => typeof v === "string");

    const counts = {};
    for (const c of choices) counts[c] = (counts[c] || 0) + 1;
    const majorityChoice = Object.entries(counts).sort((a, b) => b[1] - a[1])[0]?.[0] ?? null;
    const disagreementRate = choices.length > 1
      ? 1 - ((counts[majorityChoice] || 0) / choices.length)
      : 0;

    aggregate[id] = {
      mean: numeric.length ? mean(numeric) : null,
      std: numeric.length ? std(numeric) : null,
      majorityChoice,
      disagreementRate,
      rawAnswers: answers
    };
  }
  return aggregate;
}

function isAuthorized(req) {
  const expected = process.env.JEV_API_SECRET;
  if (!expected) return true;
  return (req.headers.authorization || "") === `Bearer ${expected}`;
}

async function evaluateOnce(state, questions) {
  const apiKey = process.env.AI_GATEWAY_API_KEY;
  if (!apiKey) {
    const error = new Error("AI_GATEWAY_API_KEY is not configured");
    error.statusCode = 503;
    throw error;
  }

  const response = await fetch(GATEWAY_URL, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      model: MODEL,
      state,
      questions
    }),
    signal: AbortSignal.timeout(20000)
  });

  const text = await response.text();
  let body;
  try { body = text ? JSON.parse(text) : {}; }
  catch { body = { raw: text }; }

  if (!response.ok) {
    const error = new Error(`Jev gateway error: ${response.status}`);
    error.statusCode = response.status;
    error.details = body;
    throw error;
  }
  return body;
}

export default async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");

  if (req.method === "GET") {
    return res.status(200).json({
      ok: true,
      endpoint: "/api/jev",
      model: MODEL,
      method: "POST",
      input: {
        state: "string | object | array",
        questions: "object",
        runs: "optional integer 1..5, default 3"
      }
    });
  }

  if (req.method !== "POST") {
    return res.status(405).json({ ok: false, error: "method_not_allowed" });
  }

  if (!isAuthorized(req)) {
    return res.status(401).json({ ok: false, error: "unauthorized" });
  }

  const body = req.body || {};
  const { state, questions } = body;
  const runs = Number.isInteger(body.runs) ? body.runs : 3;

  if (state === undefined || state === null) {
    return res.status(400).json({ ok: false, error: "state_required" });
  }

  if (!questions || typeof questions !== "object" || Array.isArray(questions) || !Object.keys(questions).length) {
    return res.status(400).json({ ok: false, error: "questions_required" });
  }

  if (runs < 1 || runs > 5) {
    return res.status(400).json({ ok: false, error: "runs_must_be_between_1_and_5" });
  }

  const startedAt = Date.now();

  try {
    const results = await Promise.all(
      Array.from({ length: runs }, () => evaluateOnce(state, questions))
    );

    return res.status(200).json({
      ok: true,
      model: MODEL,
      runs,
      durationMs: Date.now() - startedAt,
      aggregate: aggregateRuns(results),
      rawRuns: results
    });
  } catch (error) {
    console.error("jev_evaluate_failed", {
      message: error?.message,
      statusCode: error?.statusCode,
      details: error?.details
    });

    return res.status(error?.statusCode || 500).json({
      ok: false,
      error: "jev_evaluate_failed",
      message: error?.message || "Unknown error",
      details: error?.details || null
    });
  }
}
