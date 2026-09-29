# Saved-news actual Jev forecast pilot

Problem: the saved Massive news archive has not yet been supplied to Jev for a numerical forecast.
Cause: the previous step only acquired and verified provider data.
Change: restore the existing encrypted archive, select 20 named public dashboard candidates and
20 other liquid price-strength names, and send real article titles/descriptions and 126 daily
bars plus QQQ and available breadth/MC57 state to the existing Jev API. Three genuine runs per
name, ten typed questions (5/10-day close direction, terminal return bin, intraperiod up/down
excursion bins, news effect and driver). No holdings or option inputs.
Impact: new research-only script/workflow; no main/jev-prod updates, no page publishing,
no change to existing Jev question sets, database schema, sell/buy rules or daily automation.
API persist=false allows independent questions; state/raw answers/derived values are preserved
in authenticated encrypted SQLite, saved to Artifact and existing private Drive. This pilot does
NOT claim Neon evaluation persistence. No Massive reacquisition or paid add-on.

This is an uncalibrated initial trial, not the completed six-month rolling evaluation.
Reference is the latest known 2026-09-28 CLOSE, not a simulated fill. News is cut off at
2026-09-29T04:05:21Z. Current article versions were retrieved later and their historical versions
are not verified. All provided article IDs, hashes, truncation and selection counts are kept.
Provider-generated insights are excluded. Input news uses the last 30 days (up to 40 articles)
and up to three deterministic event-keyword matches in each older month within the six months.

Input past-return samples end before the forecast cutoff. Overlapping windows are marked.
A reference expected return is computed only when every bin receiving model mass has an
observed within-bin mean; otherwise it is null. Open tails remain null instead of an invented
finite bound. The reported 80% terminal envelope uses outward bin boundaries from the model
CDF, not a verified 80% coverage claim. 90% path excursion bounds are marginal, not an
independent or guaranteed joint probability. Model probabilities are uncalibrated. Original
probability sums are retained; only <=.051 rounding discrepancy is rescaled for this pilot.

Budget: max 40 requests x3 runs, $0.40 accounting cap, $.008 reservation before each request;
actual known charges replace reservation and unknown charges retain it. No retries are made.
This does not promise the provider's eventual invoice cannot exceed an estimated reservation.
No selection based on user holdings, no auto-trade, no publish, no evidence of forecast accuracy.

Rollback: do not run the dedicated research workflow. No existing production file changed.
