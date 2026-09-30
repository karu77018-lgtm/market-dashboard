# Event Risk architecture v3 — magnitude × embedded expectations

Date: 2026-09-30  
Status: research-only. No MC57/V38 production rule changes.

## 1. Core equation

Event risk is not a binary flag.

```
Pre-event event EV
= P(event within horizon | point-in-time state)
  × E(price impact | event, point-in-time state)
```

After an event is announced, the conditional-impact estimate is updated with the
actual disclosed terms.

```
Post-announcement impact nowcast
= f(actual magnitude, offer discount, financing/market-cap, float shock,
    pre-event run-up, volatility, semantic event quality)
```

Actual future dilution terms must never be used as inputs to the pre-event
occurrence/EV backtest.

## 2. Dilution — two stages

### Stage A: before announcement
Known features only:
- prior dilution history;
- shelf readiness / 424 activity;
- price / liquidity / volatility;
- pre-event run-up;
- market cap;
- future: PIT cash runway / burn when entitlement/source is available.

Outputs:
- 60D dilution probability;
- conditional impact distribution if dilution happens;
- downside / upside-offset / net EV.

### Stage B: after announcement
Newly observed terms:
- Basic Dilution %;
- Fully Diluted Overhang %;
- Financing / Market Cap;
- Offer Discount;
- Float Shock when PIT/current float is valid for the use case.

Outputs:
- updated median / p10 / p90 impact;
- observed-vs-expected severity;
- whether the financing was unusually punitive or benign.

## 3. Earnings — embedded expectations

The target is not "beat/miss -> price direction".

```
Economic surprise
= actual reported/guided information - embedded expectations
```

### Expectation Load Core
Available without paid Benzinga/options snapshot:
- 20D stock run-up;
- 20D excess return vs QQQ;
- RS63 percentile change over 20 sessions;
- distance to 63D high.

Core is fixed. Missing enhanced inputs do not cause silent reweighting.

### Expectation Load Enhanced
Only when source coverage exists:
- ATM straddle Expected Move;
- option skew / IV;
- analyst PT revision momentum;
- EPS/revenue estimate revision momentum;
- analyst disagreement / rating breadth.

## 4. Expected Move

Preferred:
```
Expected Move % = (ATM Call + ATM Put) / stock price
Realized / Expected = abs(realized event move) / Expected Move
```

The IV/Greeks option-chain snapshot is currently not entitled. Historical
contract-reference + historical option-price reconstruction remains a separate
feasibility path and must be entitlement-tested before adoption.

## 5. Jev / Python / Massive responsibilities

### Jev
Semantic extraction only:
- guidance direction;
- result quality;
- demand signal;
- margin signal;
- novelty;
- one-off distortion;
- event polarity/stage/economics where text interpretation is required.

Jev does not forecast stock direction and does not own probability/EV math.

### Python
- point-in-time joins;
- event occurrence models;
- magnitude bins / regressions;
- impact distributions;
- Expected Move math;
- Expectation Load;
- calibration / holdout;
- EV aggregation;
- coverage guards.

### Massive
- 8-K disclosure taxonomy and supporting text;
- historical prices;
- PIT ticker reference fields (share counts / market cap);
- current float;
- option reference/prices if entitlement permits;
- Benzinga analyst/earnings/guidance only when entitled.

## 6. Display contract

Every event family should expose:
- Probability + horizon + calibration source;
- Conditional impact median / p10 / p90;
- Downside EV / upside-offset EV / net EV;
- evidence/sample size and reliability;
- expectation-load fields where relevant;
- missing-data flags.

Do not collapse all of this into one opaque risk score.
