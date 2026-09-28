export default async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");
  if (req.method !== "GET") {
    return res.status(405).json({ ok: false, error: "method_not_allowed" });
  }

  return res.status(200).json({
    ok: true,
    service: "jev-investment-engine",
    version: "0.2.1-hardening",
    model: "typesafe-ai/jev",
    aiGatewayConfigured: Boolean(process.env.AI_GATEWAY_API_KEY),
    apiSecretConfigured: Boolean(process.env.JEV_API_SECRET),
    databaseConfigured: Boolean(process.env.DATABASE_URL),
    commitSha: process.env.VERCEL_GIT_COMMIT_SHA || null,
    commitRef: process.env.VERCEL_GIT_COMMIT_REF || null,
    deploymentId: process.env.VERCEL_DEPLOYMENT_ID || null,
    timestamp: new Date().toISOString()
  });
}
