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
      connectionTimeoutMillis: 10000
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
  for (const key of ["probability", "noul", "confidence"]) {
    if (typeof answer[key] === "number" && Number.isFinite(answer[key])) return answer[key];
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
    if (row.question_type === "choice") q.options = row.options_json || {};
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

async function persistEvaluation({
  state,
  questions,
  runs,
  results,
  aggregate,
  durationMs,
  ticker,
  asofTimestamp,
  questionSetVersion,
  sourceDocumentId
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
      if (row.question_type === "choice" && !sameJson(requestQuestion.options, row.options_json)) {
        throw new Error(`Question options mismatch for ${row.question_id}`);
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

    const statePayload = typeof state === "string" ? { text: state } : state;
    const stateHash = sha256Canonical(statePayload);
    const asof = asofTimestamp ? new Date(asofTimestamp) : new Date();
    if (Number.isNaN(asof.getTime())) throw new Error("Invalid asofTimestamp");

    const dedupeKey = sha256Canonical({
      asof_timestamp: asof.toISOString(),
      question_set_version: questionSetVersion,
      requested_model: MODEL,
      source_document_id: sourceDocumentId ?? null,
      state_text_hash: stateHash,
      ticker: ticker ? String(ticker).trim().toUpperCase() : null
    });

    const evalResult = await client.query(
      `INSERT INTO jev_evaluations
        (dedupe_key, ticker, asof_timestamp, source_document_id, question_set_id,
         model_version_id, requested_model, response_model, model_revision,
         state_payload, state_text_hash, hash_canonicalization_version,
         run_count, duration_ms, aggregate_json, status)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb,$11,$12,$13,$14,$15::jsonb,'success')
       RETURNING id`,
      [
        dedupeKey,
        ticker ? String(ticker).trim().toUpperCase() : null,
        asof.toISOString(),
        sourceDocumentId ?? null,
        qset.id,
        modelVersion.id,
        MODEL,
        responseModel,
        modelRevision,
        JSON.stringify(statePayload),
        stateHash,
        CANON_VERSION,
        runs,
        durationMs,
        JSON.stringify(aggregate)
      ]
    );
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
        const binaryDisagreementRate = majorityDisagreement(labels);

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
            binaryDisagreementRate,
            JSON.stringify(feature.rawAnswers)
          ]
        );
      } else if (row.question_type === "choice") {
        const choices = feature.rawAnswers.map(getChoice).filter((v) => typeof v === "string");
        const probs = feature.rawAnswers.map(getProbability).filter((v) => typeof v === "number");
        if (choices.length !== runs || probs.length !== runs) {
          throw new Error(`Missing choice values/probabilities for ${row.question_id}`);
        }
        const distribution = feature.choiceDistribution || {};

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
            JSON.stringify(distribution),
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
      evaluationId: String(evaluationId),
      stateTextHash: stateHash,
      modelVersionKey,
      questionSetVersion,
      canonicalizationVersion: CANON_VERSION
    };
  } catch (error) {
    await client.query("ROLLBACK");
    throw error;
  } finally {
    client.release();
  }
}

export default async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");

  if (req.method === "GET") {
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
        usage: "Omit questions and provide questionSetVersion to load all active questions from Neon"
      },
      input: {
        state: "string | object | array",
        questions: "optional object; omit to auto-load full question set from Neon",
        runs: "optional integer 1..5; defaults to question-set default or 3",
        persist: "optional boolean, default false",
        ticker: "recommended for ticker-specific evaluations",
        questionSetVersion: "required for persistence or full-set auto-load",
        asofTimestamp: "optional ISO-8601 timestamp"
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
  const { state } = body;
  const persist = body.persist === true;

  if (state === undefined || state === null) {
    return res.status(400).json({ ok: false, error: "state_required" });
  }

  if (persist && !body.questionSetVersion) {
    return res.status(400).json({ ok: false, error: "questionSetVersion_required_when_persisting" });
  }

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

    const runs = Number.isInteger(body.runs)
      ? body.runs
      : (loadedQuestionSet?.defaultRuns || 3);

    if (runs < 1 || runs > 5) {
      return res.status(400).json({ ok: false, error: "runs_must_be_between_1_and_5" });
    }

    const startedAt = Date.now();
    const results = await Promise.all(
      Array.from({ length: runs }, () => evaluateOnce(state, questions))
    );
    const durationMs = Date.now() - startedAt;
    const aggregate = aggregateRuns(results);

    let persistence = { saved: false };
    if (persist) {
      persistence = await persistEvaluation({
        state,
        questions,
        runs,
        results,
        aggregate,
        durationMs,
        ticker: body.ticker || null,
        asofTimestamp: body.asofTimestamp || null,
        questionSetVersion: body.questionSetVersion,
        sourceDocumentId: body.sourceDocumentId || null
      });
    }

    return res.status(200).json({
      ok: true,
      model: MODEL,
      runs,
      questionSource,
      questionCount: Object.keys(questions).length,
      durationMs,
      gatewayCostUsd: gatewayCostUsd(results),
      aggregate,
      rawRuns: results,
      persistence
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
