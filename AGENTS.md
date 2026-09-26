# Codex project instructions

## Jev

This repository includes a direct Codex -> Jev MCP integration.

- Use the MCP tool `jev_evaluate` when a task benefits from a bounded probabilistic decision, classification, score, selection, or verification.
- Jev is not a prose model. Give it structured state and explicit typed questions, then use its returned answers/probabilities as evidence for the next step.
- Supported Jev question types are `noul`, `choice`, and `score`. The local MCP adapter also accepts `boolean` and maps it to `noul`.
- Do not print, echo, log, or commit `AI_GATEWAY_API_KEY` or `JEV_API_KEY`.
- If the Jev tool reports a missing key, the Codex environment needs either `AI_GATEWAY_API_KEY` or `JEV_API_KEY`.
- The default endpoint is Vercel AI Gateway's TypeSafe-compatible Jev System One endpoint. `JEV_ENDPOINT` may override it when intentionally configured.
- Do not change MC57, V38, Massive, FRED, or publication logic merely to use Jev.
