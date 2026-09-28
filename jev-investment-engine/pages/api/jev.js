import crypto from "crypto";
import pg from "pg";

const { Pool } = pg;
const GATEWAY_URL = "https://ai-gateway.vercel.sh/v1/evaluate";
const MODEL = "typesafe-ai/jev";
const CANON_VERSION = "canon-v1";

let pool;

function getPool() {
  if (!process.env.DATABASE_URL) {
    const error = new Error("DATABASE_URL is not configured");
    error.statusCode = 503;
    throw error;
  }
  if (!pool) {
    pool = new Pool({
      connectionString: process.env.DATABASE_URL,
      max: 3,
      idleTimeoutMillis: 10000,
      connectionTimeoutMillis: 10000,
      statement_timeout: 15000,
      query_timeout: 15000
    });
  }
  return pool;
}

function normalizeCanonical(value) {
  if (typeof value === "string") return value.normalize("NFC");
  if (Array.isArray(value)) return value.map(normalizeCanonical);
  if (value && typeof value === "object") {
    return Object.keys(value).sort().reduce((acc, key) => {
      acc[key] = normalizeCanonical(value[key]);
      return acc;
    }, {});
  }
  return value;
}

function canonicalJson(value) {
  return JSON.stringify(normalizeCanonical(value));
}

function sha256Canonical(value) {
  return crypto.createHash("sha256").update(canonicalJson(value), "utf8").digest("hex");
}

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

function getProbability(answer) {
  if (typeof answer === "number" && Number.isFinite(answer)) return answer;
  if (!answer || typeof answer !== "object") return null;

  for (const key of ["probability", "noul"]) {
    if (typeof answer[key] === "number" && Number.isFinite(answer[key])) return answer[key];
  }

  const choice = getChoice(answer);
  const distribution = getChoiceDistribution(answer);
  if (
    choice &&
    distribution &&
    typeof distribution[choice] === "number" &&
    Number.isFinite(distribution[choice])
  ) {
    return distribution[choice];
  }

  return null;
}

function getScore(answer) {
  if (!answer || typeof answer !== "object") return null;
  if (typeof answer.score === "number" && Number.isFinite(answer.score)) return answer.score;
  return null;
}

function getChoice(answer) {
  if (!answer || typeof answer !== "object") return null;
  if (typeof answer.choice === "string") return answer.choice;
  if (typeof answer.value === "string") return answer.value;
  return null;
}

function getChoiceDistribution(answer) {
  if (!answer || typeof answer !== "object") return null;
  for (const key of ["probabilities", "distribution", "choices"]) {
    const value = answer[key];
    if (value && typeof value === "object" && !Array.isArray(value)) return value;
  }
  return null;
}

function aggregateChoiceDistributions(distributions) {
  const valid = distributions.filter(Boolean);
  if (!valid.length) return null;
  const keys = new Set(valid.flatMap((d) => Object.keys(d)));
  const out = {};
  for (const key of keys) {
    const vals = valid
      .map((d) => d[key])
      .filter((v) => typeof v === "number" && Number.isFinite(v));
    if (vals.length) out[key] = mean(vals);
  }
  return out;
}

function majorityDisagreement(values) {
  if (!values.length) return 0;
  const counts = {};
  for (const value of values) counts[value] = (counts[value] || 0) + 1;
  const max = Math.max(...Object.values(counts));
  return 1 - max / values.length;
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
    const probabilities = answers.map(getProbability).filter((v) => typeof v === "number");
    const scores = answers.map(getScore).filter((v) => typeof v === "number");
    const choices = answers.map(getChoice).filter((v) => typeof v === "string");

    aggregate[id] = {
      probabilityMean: probabilities.length ? mean(probabilities) : null,
      probabilityStd: probabilities.length ? std(probabilities) : null,
      scoreMean: scores.length ? mean(scores) : null,
      scoreStd: scores.length ? std(scores) : null,
      majorityChoice: choices.length
        ? Object.entries(choices.reduce((acc, c) => {
            acc[c] = (acc[c] || 0) + 1;
            return acc;
          }, {})).sort((a, b) => b[1] - a[1])[0][0]
        : null,
      choiceDisagreementRate: choices.length ? majorityDisagreement(choices) : null,
      choiceDistribution: aggregateChoiceDistributions(answers.map(getChoiceDistribution)),
      rawAnswers: answers
    };
  }
  return aggregate;
}

function authStatus(req) {
  const expected = process.env.JEV_API_SECRET;
  if (!expected) return { ok: false, statusCode: 503, error: "JEV_API_SECRET_not_configured" };
  const actual = req.headers.authorization || "";
  if (actual !== `Bearer ${expected}`) {
    return { ok: false, statusCode: 401, error: "unauthorized" };
  }
  return { ok: true };
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
    signal: AbortSignal.timeout(45000)
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

function sameJson(a, b) {
  return canonicalJson(a ?? null) === canonicalJson(b ?? null);
}

async function loadQuestionSet(questionSetVersion) {
  const db = getPool();
  const result = await db.query(
    `SELECT qs.id AS question_set_id, qs.version, qs.default_runs,
            q.question_id, q.question_type, q.instructions, q.options_json,
            q.binary_threshold, q.score_scale_min, q.score_scale_max, q.ordinal
     FROM question_sets qs
     JOIN questions q ON q.question_set_id = qs.id
     WHERE qs.version = $1
       AND qs.status IN ('shadow','validation','production')
       AND q.active = true
     ORDER BY q.ordinal`,
    [questionSetVersion]
  );

  if (!result.rowCount) {
    const error = new Error(`Unknown or inactive question set: ${questionSetVersion}`);
    error.statusCode = 400;
    throw error;
  }

  const questions = {};
  for (const row of result.rows) {
    const q = {
      type: row.question_type,
      instructions: row.instructions
    };
    if (row.question_type === "choice") q.criteria = row.options_json || {};
    questions[row.question_id] = q;
  }

  return {
    id: result.rows[0].question_set_id,
    version: result.rows[0].version,
    defaultRuns: result.rows[0].default_runs || 3,
    questions
  };
}

function gatewayCostUsd(results) {
  return results.reduce((sum, run) => {
    const gateway = run?.providerMetadata?.gateway || {};
    const raw = gateway.cost ?? gateway.gatewayCost ?? gateway.inferenceCost ?? 0;
    const value = Number(raw);
    return sum + (Number.isFinite(value) ? value : 0);
  }, 0);
}

function usageTotals(results) {
  return results.reduce((acc, run) => {
    const gateway = run?.providerMetadata?.gateway || {};
    const rawCost = gateway.cost ?? gateway.gatewayCost ?? gateway.inferenceCost ?? 0;
    const cost = Number(rawCost);
    acc.gatewayCostUsd += Number.isFinite(cost) ? cost : 0;
    acc.inputTokens += Number(run?.usage?.inputTokens || 0);
    acc.outputTokens += Number(run?.usage?.outputTokens || 0);
    return acc;
  }, { gatewayCostUsd: 0, inputTokens: 0, outputTokens: 0 });
}

function normalizeTicker(value) {
  if (typeof value !== "string") return null;
  const ticker = value.trim().toUpperCase();
  return ticker || null;
}

function parseAsofTimestamp(value) {
  if (typeof value !== "string" || !/([zZ]|[+-]\d{2}:\d{2})$/.test(value)) {
    const error = new Error("asofTimestamp must be timezone-aware ISO-8601");
    error.statusCode = 400;
    error.errorCode = "invalid_asofTimestamp";
    throw error;
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    const error = new Error("Invalid asofTimestamp");
    error.statusCode = 400;
    error.errorCode = "invalid_asofTimestamp";
    throw error;
  }
  if (date.getTime() > Date.now()) {
    const error = new Error("asofTimestamp cannot be in the future");
    error.statusCode = 400;
    error.errorCode = "future_asofTimestamp";
    throw error;
  }
  return date.toISOString();
}

function buildIdentity({ state, asofIso, questionSetVersion, sourceDocumentId, ticker }) {
  const statePayload = typeof state === "string" ? { text: state } : state;
  const stateTextHash = sha256Canonical(statePayload);
  const dedupeKey = sha256Canonical({
    asof_timestamp: asofIso,
    question_set_version: questionSetVersion,
    requested_model: MODEL,
    source_document_id: sourceDocumentId ?? null,
    state_text_hash: stateTextHash,
    ticker
  });
  return { statePayload, stateTextHash, dedupeKey };
}

async function findExistingEvaluation(dedupeKey) {
  const result = await getPool().query(
    `SELECT id, ticker, asof_timestamp, evaluation_kind, validation_eligible, run_count, status
     FROM jev_evaluations
     WHERE dedupe_key = $1
     LIMIT 1`,
    [dedupeKey]
  );
  return result.rows[0] || null;
}

async function startAttempt({
  ticker,
  asofIso,
  questionSetId,
  evaluationKind,
  sourceDocumentId,
  stateTextHash,
  dedupeKey
}) {
  const result = await getPool().query(
    `INSERT INTO jev_attempts
      (ticker, asof_timestamp, question_set_id, evaluation_kind, source_document_id,
       state_text_hash, dedupe_key, run_count, status)
     VALUES ($1,$2,$3,$4,$5,$6,$7,3,'started')
     RETURNING id, started_at`,
    [ticker, asofIso, questionSetId, evaluationKind, sourceDocumentId ?? null, stateTextHash, dedupeKey]
  );
  return result.rows[0];
}

async function finishAttempt(attemptId, {
  status,
  startedAt,
  httpStatus = null,
  errorCode = null,
  errorMessage = null,
  successfulRuns = 0,
  results = [],
  evaluationId = null,
  metadata = {}
}) {
  const totals = usageTotals(results);
  const durationMs = Math.max(0, Date.now() - new Date(startedAt).getTime());
  const result = await getPool().query(
    `UPDATE jev_attempts
     SET status=$2, completed_at=now(), duration_ms=$3, http_status=$4,
         error_code=$5, error_message=$6, successful_runs=$7,
         gateway_cost_usd=$8, input_tokens=$9, output_tokens=$10,
         evaluation_id=$11, metadata=$12::jsonb
     WHERE id=$1 AND status='started' AND completed_at IS NULL
     RETURNING id`,
    [
      attemptId,
      status,
      durationMs,
      httpStatus,
      errorCode,
      errorMessage,
      successfulRuns,
      totals.gatewayCostUsd,
      totals.inputTokens,
      totals.outputTokens,
      evaluationId,
      JSON.stringify(metadata || {})
    ]
  );
  return result.rowCount === 1;
}

function classifyRunFailure(reason) {
  const name = reason?.name || "";
  const message = reason?.message || "";
  if (name === "TimeoutError" || name === "AbortError" || /timeout|aborted/i.test(message)) {
    return { status: "timeout", httpStatus: 504, errorCode: "jev_timeout" };
  }
  return {
    status: "gateway_error",
    httpStatus: reason?.statusCode || 502,
    errorCode: "jev_gateway_error"
  };
}

function summaryText({
  ticker,
  asofIso,
  questionCount,
  runs,
  evaluationId,
  durationMs,
  gatewayCostUsd,
  duplicate = false,
  attemptId = null
}) {
  return [
    duplicate ? "Jev DUPLICATE" : "Jev OK",
    `Ticker: ${ticker}`,
    `As-of: ${asofIso}`,
    `Questions: ${questionCount}`,
    `Runs: ${runs}`,
    `Evaluation: #${evaluationId}`,
    `Attempt: ${attemptId ? "#" + attemptId : "-"}`,
    `Duration: ${durationMs} ms`,
    `Cost: $${Number(gatewayCostUsd || 0).toFixed(6)}`
  ].join("\n");
}

async function persistEvaluation({
  statePayload,
  stateTextHash,
  dedupeKey,
  questions,
  runs,
  results,
  aggregate,
  durationMs,
  ticker,
  asofIso,
  questionSetVersion,
  sourceDocumentId,
  evaluationKind,
  validationEligible
}) {
  const db = getPool();
  const client = await db.connect();

  try {
    await client.query("BEGIN");

    const qsetResult = await client.query(
      `SELECT id, version, requested_model, model_revision, default_runs
       FROM question_sets
       WHERE version = $1 AND status IN ('shadow','validation','production')`,
      [questionSetVersion]
    );
    if (qsetResult.rowCount !== 1) {
      throw new Error(`Unknown or inactive question set: ${questionSetVersion}`);
    }
    const qset = qsetResult.rows[0];

    const requestIds = Object.keys(questions);
    const qResult = await client.query(
      `SELECT id, question_id, question_type, instructions, options_json,
              binary_threshold, score_scale_min, score_scale_max
       FROM questions
       WHERE question_set_id = $1 AND question_id = ANY($2::text[]) AND active = true
       ORDER BY ordinal`,
      [qset.id, requestIds]
    );

    if (qResult.rowCount !== requestIds.length) {
      const found = new Set(qResult.rows.map((r) => r.question_id));
      const missing = requestIds.filter((id) => !found.has(id));
      throw new Error(`Questions are not part of ${questionSetVersion}: ${missing.join(", ")}`);
    }

    for (const row of qResult.rows) {
      const requestQuestion = questions[row.question_id] || {};
      if (requestQuestion.type !== row.question_type) {
        throw new Error(`Question type mismatch for ${row.question_id}`);
      }
      if (requestQuestion.instructions !== row.instructions) {
        throw new Error(`Question instructions mismatch for ${row.question_id}`);
      }
      if (
        row.question_type === "choice" &&
        !sameJson(requestQuestion.criteria ?? requestQuestion.options, row.options_json)
      ) {
        throw new Error(`Question criteria mismatch for ${row.question_id}`);
      }
    }

    const responseModel = results.find((r) => typeof r?.model === "string")?.model || null;
    const gatewayMeta = results.find((r) => r?.providerMetadata?.gateway)?.providerMetadata?.gateway || {};
    const provider = gatewayMeta?.routing?.finalProvider || null;
    const modelRevision = results.find((r) => typeof r?.model_revision === "string")?.model_revision || null;

    const modelVersionKey = sha256Canonical({
      model_revision: modelRevision,
      requested_model: MODEL,
      response_model: responseModel
    });

    const mvResult = await client.query(
      `INSERT INTO model_versions
        (model_version_key, requested_model, response_model, model_revision, provider,
         hash_canonicalization_version, metadata, last_seen_at)
       VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb,now())
       ON CONFLICT (model_version_key)
       DO UPDATE SET response_model=EXCLUDED.response_model,
                     model_revision=EXCLUDED.model_revision,
                     provider=EXCLUDED.provider,
                     metadata=EXCLUDED.metadata,
                     last_seen_at=now()
       RETURNING id, model_version_key`,
      [
        modelVersionKey,
        MODEL,
        responseModel,
        modelRevision,
        provider,
        CANON_VERSION,
        JSON.stringify({ gateway: gatewayMeta })
      ]
    );
    const modelVersion = mvResult.rows[0];

    const evalResult = await client.query(
      `INSERT INTO jev_evaluations
        (dedupe_key, ticker, asof_timestamp, source_document_id, question_set_id,
         model_version_id, requested_model, response_model, model_revision,
         state_payload, state_text_hash, hash_canonicalization_version,
         run_count, duration_ms, aggregate_json, status, evaluation_kind, validation_eligible)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb,$11,$12,$13,$14,$15::jsonb,'success',$16,$17)
       ON CONFLICT (dedupe_key) DO NOTHING
       RETURNING id`,
      [
        dedupeKey,
        ticker,
        asofIso,
        sourceDocumentId ?? null,
        qset.id,
        modelVersion.id,
        MODEL,
        responseModel,
        modelRevision,
        JSON.stringify(statePayload),
        stateTextHash,
        CANON_VERSION,
        runs,
        durationMs,
        JSON.stringify(aggregate),
        evaluationKind,
        Boolean(validationEligible)
      ]
    );

    if (evalResult.rowCount !== 1) {
      await client.query("ROLLBACK");
      const existing = await findExistingEvaluation(dedupeKey);
      return {
        saved: false,
        duplicateRace: true,
        evaluationId: existing ? String(existing.id) : null,
        existingKind: existing?.evaluation_kind || null,
        stateTextHash,
        modelVersionKey,
        questionSetVersion,
        canonicalizationVersion: CANON_VERSION
      };
    }

    const evaluationId = evalResult.rows[0].id;

    for (let i = 0; i < results.length; i++) {
      const run = results[i];
      const gm = run?.providerMetadata?.gateway || {};
      await client.query(
        `INSERT INTO jev_runs
          (evaluation_id, run_no, raw_response, provider_metadata, input_tokens,
           output_tokens, inference_cost_usd, generation_id)
         VALUES ($1,$2,$3::jsonb,$4::jsonb,$5,$6,$7,$8)`,
        [
          evaluationId,
          i + 1,
          JSON.stringify(run),
          JSON.stringify(run?.providerMetadata || {}),
          run?.usage?.inputTokens ?? null,
          run?.usage?.outputTokens ?? null,
          gm?.inferenceCost ?? gm?.cost ?? null,
          gm?.generationId ?? null
        ]
      );
    }

    for (const row of qResult.rows) {
      const feature = aggregate[row.question_id];
      if (!feature) throw new Error(`Missing aggregate for ${row.question_id}`);

      if (row.question_type === "boolean") {
        const probs = feature.rawAnswers.map(getProbability).filter((v) => typeof v === "number");
        if (probs.length !== runs) throw new Error(`Missing boolean probabilities for ${row.question_id}`);
        const labels = probs.map((p) => p >= row.binary_threshold ? "1" : "0");
        await client.query(
          `INSERT INTO jev_text_features
            (evaluation_id, question_id, answer_type, probability_mean, probability_std,
             binary_threshold_used, binary_disagreement_rate, raw_answers)
           VALUES ($1,$2,'boolean',$3,$4,$5,$6,$7::jsonb)`,
          [
            evaluationId,
            row.id,
            mean(probs),
            std(probs),
            row.binary_threshold,
            majorityDisagreement(labels),
            JSON.stringify(feature.rawAnswers)
          ]
        );
      } else if (row.question_type === "choice") {
        const choices = feature.rawAnswers.map(getChoice).filter((v) => typeof v === "string");
        const probs = feature.rawAnswers.map(getProbability).filter((v) => typeof v === "number");
        if (choices.length !== runs || probs.length !== runs) {
          throw new Error(`Missing choice values/probabilities for ${row.question_id}`);
        }
        await client.query(
          `INSERT INTO jev_text_features
            (evaluation_id, question_id, answer_type, probability_mean, probability_std,
             majority_choice, choice_distribution, choice_disagreement_rate, raw_answers)
           VALUES ($1,$2,'choice',$3,$4,$5,$6::jsonb,$7,$8::jsonb)`,
          [
            evaluationId,
            row.id,
            mean(probs),
            std(probs),
            feature.majorityChoice,
            JSON.stringify(feature.choiceDistribution || {}),
            feature.choiceDisagreementRate ?? 0,
            JSON.stringify(feature.rawAnswers)
          ]
        );
      } else if (row.question_type === "score") {
        const scores = feature.rawAnswers.map(getScore).filter((v) => typeof v === "number");
        if (scores.length !== runs) throw new Error(`Missing scores for ${row.question_id}`);
        await client.query(
          `INSERT INTO jev_text_features
            (evaluation_id, question_id, answer_type, score_mean, score_std,
             score_scale_min, score_scale_max, raw_answers)
           VALUES ($1,$2,'score',$3,$4,$5,$6,$7::jsonb)`,
          [
            evaluationId,
            row.id,
            mean(scores),
            std(scores),
            row.score_scale_min,
            row.score_scale_max,
            JSON.stringify(feature.rawAnswers)
          ]
        );
      }
    }

    await client.query("COMMIT");
    return {
      saved: true,
      duplicateRace: false,
      evaluationId: String(evaluationId),
      stateTextHash,
      modelVersionKey,
      questionSetVersion,
      canonicalizationVersion: CANON_VERSION
    };
  } catch (error) {
    try { await client.query("ROLLBACK"); } catch {}
    throw error;
  } finally {
    client.release();
  }
}

export default async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");

  if (req.method === "GET") {
    let questionSet = null;
    const inspectVersion =
      typeof req.query?.inspectQuestionSet === "string"
        ? req.query.inspectQuestionSet
        : null;

    if (inspectVersion) {
      try {
        const loaded = await loadQuestionSet(inspectVersion);
        questionSet = {
          version: loaded.version,
          questionCount: Object.keys(loaded.questions).length,
          defaultRuns: loaded.defaultRuns
        };
      } catch (error) {
        return res.status(error?.statusCode || 500).json({
          ok: false,
          error: "question_set_inspection_failed",
          message: error?.message || "Unknown error"
        });
      }
    }

    return res.status(200).json({
      ok: true,
      endpoint: "/api/jev",
      model: MODEL,
      method: "POST",
      persistence: {
        supported: Boolean(process.env.DATABASE_URL),
        enabledWhen: "persist === true"
      },
      fullSetMode: {
        supported: Boolean(process.env.DATABASE_URL),
        usage: "For persisted evaluations, omit questions and provide questionSetVersion"
      },
      questionSet,
      input: {
        state: "string | object | array",
        questions: "allowed only when persist=false",
        runs: "persist=true requires exactly 3; otherwise 1..5",
        persist: "optional boolean, default false",
        ticker: "required when persist=true",
        questionSetVersion: "required when persist=true or auto-loading a question set",
        asofTimestamp: "required timezone-aware ISO-8601 when persist=true",
        evaluationKind: "required when persist=true: smoke|manual_shadow|backfill|live",
        validationEligible: "optional boolean; DB only permits true for eligible sourced backfill/live rows",
        responseMode: "optional: summary"
      }
    });
  }

  if (req.method !== "POST") {
    return res.status(405).json({ ok: false, error: "method_not_allowed" });
  }

  const auth = authStatus(req);
  if (!auth.ok) {
    return res.status(auth.statusCode).json({ ok: false, error: auth.error });
  }

  const body = req.body || {};
  const { state } = body;
  const persist = body.persist === true;
  const responseMode = body.responseMode === "summary" ? "summary" : "json";

  if (state === undefined || state === null) {
    return res.status(400).json({ ok: false, error: "state_required" });
  }

  if (persist) {
    if (!body.questionSetVersion) {
      return res.status(400).json({ ok: false, error: "questionSetVersion_required_when_persisting" });
    }
    if (body.questions !== undefined) {
      return res.status(400).json({ ok: false, error: "questions_forbidden_when_persisting" });
    }
    if (!normalizeTicker(body.ticker)) {
      return res.status(400).json({ ok: false, error: "ticker_required_when_persisting" });
    }
    if (!body.asofTimestamp) {
      return res.status(400).json({ ok: false, error: "asofTimestamp_required_when_persisting" });
    }
    if (!["smoke","manual_shadow","backfill","live"].includes(body.evaluationKind)) {
      return res.status(400).json({ ok: false, error: "evaluationKind_required_when_persisting" });
    }
    if (body.runs !== undefined && body.runs !== 3) {
      return res.status(400).json({ ok: false, error: "persisted_runs_must_equal_3" });
    }
  }

  let attempt = null;
  let fulfilledResults = [];

  try {
    let questions = body.questions;
    let questionSource = "request";
    let loadedQuestionSet = null;

    const hasRequestQuestions =
      questions &&
      typeof questions === "object" &&
      !Array.isArray(questions) &&
      Object.keys(questions).length > 0;

    if (!hasRequestQuestions) {
      if (!body.questionSetVersion) {
        return res.status(400).json({
          ok: false,
          error: "questions_or_questionSetVersion_required"
        });
      }
      loadedQuestionSet = await loadQuestionSet(body.questionSetVersion);
      questions = loadedQuestionSet.questions;
      questionSource = "neon";
    }

    const runs = persist
      ? 3
      : (Number.isInteger(body.runs) ? body.runs : (loadedQuestionSet?.defaultRuns || 3));

    if (runs < 1 || runs > 5) {
      return res.status(400).json({ ok: false, error: "runs_must_be_between_1_and_5" });
    }

    if (!persist) {
      const startedAt = Date.now();
      const results = await Promise.all(
        Array.from({ length: runs }, () => evaluateOnce(state, questions))
      );
      const durationMs = Date.now() - startedAt;
      return res.status(200).json({
        ok: true,
        model: MODEL,
        runs,
        questionSource,
        questionCount: Object.keys(questions).length,
        durationMs,
        gatewayCostUsd: gatewayCostUsd(results),
        aggregate: aggregateRuns(results),
        rawRuns: results,
        persistence: { saved: false }
      });
    }

    const ticker = normalizeTicker(body.ticker);
    const asofIso = parseAsofTimestamp(body.asofTimestamp);
    const evaluationKind = body.evaluationKind;
    const sourceDocumentId = body.sourceDocumentId ?? null;
    const validationEligible = body.validationEligible === true;

    if (
      validationEligible &&
      (!["backfill","live"].includes(evaluationKind) || sourceDocumentId === null)
    ) {
      return res.status(400).json({ ok: false, error: "validationEligible_requires_sourced_backfill_or_live" });
    }

    const identity = buildIdentity({
      state,
      asofIso,
      questionSetVersion: body.questionSetVersion,
      sourceDocumentId,
      ticker
    });

    try {
      attempt = await startAttempt({
        ticker,
        asofIso,
        questionSetId: loadedQuestionSet.id,
        evaluationKind,
        sourceDocumentId,
        stateTextHash: identity.stateTextHash,
        dedupeKey: identity.dedupeKey
      });
    } catch (error) {
      console.error("jev_attempt_start_failed", { message: error?.message });
      return res.status(503).json({ ok: false, error: "attempt_log_unavailable" });
    }

    const existing = await findExistingEvaluation(identity.dedupeKey);
    if (existing) {
      if (existing.evaluation_kind !== evaluationKind) {
        await finishAttempt(attempt.id, {
          status: "duplicate",
          startedAt: attempt.started_at,
          httpStatus: 409,
          errorCode: "dedupe_kind_conflict",
          errorMessage: `Existing evaluation kind is ${existing.evaluation_kind || "null"}`,
          evaluationId: existing.id,
          metadata: { requestedKind: evaluationKind, existingKind: existing.evaluation_kind || null }
        });
        return res.status(409).json({
          ok: false,
          error: "dedupe_kind_conflict",
          existingEvaluationId: String(existing.id),
          existingKind: existing.evaluation_kind || null
        });
      }

      await finishAttempt(attempt.id, {
        status: "duplicate",
        startedAt: attempt.started_at,
        httpStatus: 200,
        evaluationId: existing.id
      });

      const duplicatePayload = {
        ok: true,
        duplicate: true,
        ticker,
        asofTimestamp: asofIso,
        questionCount: Object.keys(questions).length,
        runs: 3,
        evaluationId: String(existing.id),
        durationMs: 0,
        gatewayCostUsd: 0,
        attemptId: String(attempt.id)
      };

      if (responseMode === "summary") {
        res.setHeader("Content-Type", "text/plain; charset=utf-8");
        return res.status(200).send(summaryText({ ...duplicatePayload, asofIso }));
      }
      return res.status(200).json(duplicatePayload);
    }

    const startedAt = Date.now();
    const settled = await Promise.allSettled(
      Array.from({ length: 3 }, () => evaluateOnce(state, questions))
    );
    const durationMs = Date.now() - startedAt;
    fulfilledResults = settled
      .filter((item) => item.status === "fulfilled")
      .map((item) => item.value);

    const rejected = settled.filter((item) => item.status === "rejected");
    if (rejected.length) {
      const firstFailure = classifyRunFailure(rejected[0].reason);
      const terminalStatus = fulfilledResults.length > 0 ? "partial" : firstFailure.status;
      await finishAttempt(attempt.id, {
        status: terminalStatus,
        startedAt: attempt.started_at,
        httpStatus: firstFailure.httpStatus,
        errorCode: firstFailure.errorCode,
        errorMessage: rejected[0].reason?.message || "Jev run failed",
        successfulRuns: fulfilledResults.length,
        results: fulfilledResults,
        metadata: { failedRuns: rejected.length }
      });
      return res.status(firstFailure.httpStatus).json({
        ok: false,
        error: terminalStatus,
        successfulRuns: fulfilledResults.length,
        failedRuns: rejected.length
      });
    }

    const aggregate = aggregateRuns(fulfilledResults);
    const questionIds = Object.keys(questions);
    if (
      Object.keys(aggregate).length !== questionIds.length ||
      questionIds.some((id) => !aggregate[id] || aggregate[id].rawAnswers.length !== 3)
    ) {
      await finishAttempt(attempt.id, {
        status: "partial",
        startedAt: attempt.started_at,
        httpStatus: 502,
        errorCode: "incomplete_question_set",
        errorMessage: "Not all questions returned three answers",
        successfulRuns: 3,
        results: fulfilledResults
      });
      return res.status(502).json({ ok: false, error: "incomplete_question_set" });
    }

    const persistence = await persistEvaluation({
      statePayload: identity.statePayload,
      stateTextHash: identity.stateTextHash,
      dedupeKey: identity.dedupeKey,
      questions,
      runs: 3,
      results: fulfilledResults,
      aggregate,
      durationMs,
      ticker,
      asofIso,
      questionSetVersion: body.questionSetVersion,
      sourceDocumentId,
      evaluationKind,
      validationEligible
    });

    if (persistence.duplicateRace) {
      if (persistence.existingKind !== evaluationKind) {
        await finishAttempt(attempt.id, {
          status: "duplicate",
          startedAt: attempt.started_at,
          httpStatus: 409,
          errorCode: "dedupe_kind_conflict",
          errorMessage: `Existing evaluation kind is ${persistence.existingKind || "null"}`,
          successfulRuns: 3,
          results: fulfilledResults,
          evaluationId: persistence.evaluationId
        });
        return res.status(409).json({
          ok: false,
          error: "dedupe_kind_conflict",
          existingEvaluationId: persistence.evaluationId,
          existingKind: persistence.existingKind
        });
      }

      await finishAttempt(attempt.id, {
        status: "duplicate",
        startedAt: attempt.started_at,
        httpStatus: 200,
        successfulRuns: 3,
        results: fulfilledResults,
        evaluationId: persistence.evaluationId,
        metadata: { concurrentDuplicate: true }
      });

      const totals = usageTotals(fulfilledResults);
      const duplicatePayload = {
        ok: true,
        duplicate: true,
        ticker,
        asofTimestamp: asofIso,
        questionCount: Object.keys(questions).length,
        runs: 3,
        evaluationId: persistence.evaluationId,
        durationMs,
        gatewayCostUsd: totals.gatewayCostUsd,
        attemptId: String(attempt.id)
      };
      if (responseMode === "summary") {
        res.setHeader("Content-Type", "text/plain; charset=utf-8");
        return res.status(200).send(summaryText({ ...duplicatePayload, asofIso }));
      }
      return res.status(200).json(duplicatePayload);
    }

    let attemptFinalized = true;
    try {
      attemptFinalized = await finishAttempt(attempt.id, {
        status: "success",
        startedAt: attempt.started_at,
        httpStatus: 200,
        successfulRuns: 3,
        results: fulfilledResults,
        evaluationId: persistence.evaluationId
      });
    } catch (error) {
      attemptFinalized = false;
      console.error("jev_attempt_finalize_failed", { message: error?.message, attemptId: attempt.id });
    }

    const totals = usageTotals(fulfilledResults);
    const payload = {
      ok: true,
      duplicate: false,
      model: MODEL,
      ticker,
      asofTimestamp: asofIso,
      runs: 3,
      questionSource,
      questionCount: Object.keys(questions).length,
      durationMs,
      gatewayCostUsd: totals.gatewayCostUsd,
      evaluationId: persistence.evaluationId,
      attemptId: String(attempt.id),
      attemptFinalized,
      persistence,
      aggregate,
      rawRuns: fulfilledResults
    };

    if (responseMode === "summary") {
      res.setHeader("Content-Type", "text/plain; charset=utf-8");
      return res.status(200).send(summaryText({
        ticker,
        asofIso,
        questionCount: payload.questionCount,
        runs: 3,
        evaluationId: payload.evaluationId,
        durationMs,
        gatewayCostUsd: totals.gatewayCostUsd,
        attemptId: payload.attemptId
      }));
    }

    return res.status(200).json(payload);
  } catch (error) {
    console.error("jev_evaluate_failed", {
      message: error?.message,
      statusCode: error?.statusCode,
      errorCode: error?.errorCode
    });

    if (attempt) {
      try {
        await finishAttempt(attempt.id, {
          status: "db_error",
          startedAt: attempt.started_at,
          httpStatus: error?.statusCode || 500,
          errorCode: error?.errorCode || "jev_evaluate_failed",
          errorMessage: error?.message || "Unknown error",
          successfulRuns: fulfilledResults.length,
          results: fulfilledResults
        });
      } catch (attemptError) {
        console.error("jev_attempt_finalize_failed", {
          message: attemptError?.message,
          attemptId: attempt.id
        });
      }
    }

    return res.status(error?.statusCode || 500).json({
      ok: false,
      error: error?.errorCode || "jev_evaluate_failed",
      message: error?.message || "Unknown error"
    });
  }
}
