# Oracle — How It Works

## Architecture

Oracle is structured as a single-skill plugin at v0.1.0. The plugin directory contains:

```
oracle/
  skills/
    deribit/
      scripts/
        deribit.py      # PEP 723 self-contained script, run via uv run
  lib/
    protocols.py        # signal/v1 schema and output helpers
```

All network I/O, computation, and output happen inside `deribit.py`. The `protocols.py` library defines the shared `signal/v1` JSON schema used across the forgequant plugin ecosystem.

## Data Flow

```
Deribit Public API
      |
      v
  HTTP fetch (options chain for BTC/ETH)
      |
      v
  Strike filtering + delta computation
  (Black-76 model, custom norm_cdf)
      |
      v
  Signal computation
  (RR25, PCR, DVOL modifier, term structure)
      |
      v
  Confidence scoring
      |
      v
  Cache write (atomic, ~/.cache/oracle/)
      |
      v
  signal/v1 JSON → stdout
  Human summary   → stderr
```

## Components

### Deribit Skill (`skills/deribit/scripts/deribit.py`)

The script is PEP 723 compliant: dependencies are declared inline and resolved by `uv run` without a separate install step.

It fetches the full options chain from the Deribit public API for the requested asset(s) and processes the data in several stages.

**Stage 1 — Delta Computation (Black-76 model)**

Delta is computed using the Black-76 pricing model, which is standard for futures-settled options. The normal CDF is approximated using the Abramowitz & Stegun `erf` approximation with an error bound below 7.5e-8. This avoids a `scipy` dependency while maintaining sufficient precision for strike interpolation.

For each expiry, the script identifies the 25-delta call and 25-delta put strikes by interpolating between the two nearest available strikes by delta value.

**Stage 2 — Signal Computation**

Four signals are derived from the options chain:

- **RR25 (25-delta risk reversal):** `call_25d_IV - put_25d_IV`. A positive value means calls carry higher implied volatility than puts, indicating the market is pricing upside risk more expensively — a bullish skew.

- **PCR (notional put/call ratio):** `put_notional / call_notional`, where notional = open interest * strike price. A low PCR indicates more capital is positioned in calls relative to puts — bullish.

- **DVOL modifier:** Deribit's proprietary volatility index for BTC and ETH, analogous to the CBOE VIX. A high DVOL value means the market is in a high-volatility regime. The modifier reduces signal confidence proportionally when DVOL is elevated, because directional signals are less reliable in turbulent markets.

- **Term structure ratio:** The ratio of front-month ATM implied volatility to back-month ATM implied volatility. A ratio above 1.0 indicates backwardation (near-term options are more expensive), which is associated with near-term uncertainty. The script applies a confidence penalty in backwardation.

**Stage 3 — Direction Score**

The two primary signals are combined into a weighted direction score:

```
direction_score = 0.55 * skew_score + 0.45 * pcr_score
```

Skew and PCR scores are individually normalized to [-1, 1] before weighting.

**Stage 4 — Confidence Scoring**

Confidence is a multi-factor weighted score:

```
raw_confidence = (0.40 * strength
                + 0.25 * agreement
                + 0.25 * data_quality
                + 0.10 * liquidity)

confidence = raw_confidence * min(dvol_modifier, ts_modifier)
```

- `strength`: magnitude of the direction score
- `agreement`: degree to which RR25 and PCR point in the same direction
- `data_quality`: reflects cache freshness decay (1.0 → 0.15 based on age)
- `liquidity`: based on open interest across the options chain
- `dvol_modifier` and `ts_modifier`: regime penalties (both in [0, 1])

The final confidence is clamped to [15, 100].

### Cache Layer

Results are written atomically to `~/.cache/oracle/deribit/snapshot_{asset}.json` using a write-to-temp-then-rename pattern to prevent partial reads. On subsequent calls, the script reads the snapshot and applies a freshness multiplier to `data_quality`:

| Age | Multiplier |
|-----|-----------|
| < 5 min | 1.0 |
| < 1 h | 0.7 |
| < 6 h | 0.4 |
| < 24 h | 0.25 |
| Older | 0.15 |

### Protocols Library (`lib/protocols.py`)

Defines the `signal/v1` JSON schema and output helpers. All forgequant plugins emit the same schema, enabling downstream composition — e.g., a meta-signal aggregator can consume oracle and sentinel outputs together.

## Trust Boundaries

- Oracle makes outbound HTTPS requests to the Deribit public API. No authentication is required. Deribit's API is free for market data.
- No user data, portfolio information, or private keys are ever transmitted.
- All computation happens locally. The only local writes are the cache files under `~/.cache/oracle/`.
- The plugin does not execute trades and has no connection to any exchange account.

## Limitations

- **Alpha status:** Only the `deribit` skill is implemented. Exchange flow signals and prediction market integrations are planned.
- **Options-only view:** Deribit signals reflect the derivatives market. Spot market dynamics, on-chain flows, and macro factors are not captured in this version.
- **Public API rate limits:** Deribit's public API has rate limits. The cache layer reduces API calls, but heavy use or `--no-cache` on tight loops may hit limits.
- **Delta interpolation accuracy:** Delta is interpolated between available strikes. Sparse strike grids (e.g., small altcoins) reduce precision. BTC and ETH have dense strike grids and are the intended assets.
- **Model assumptions:** Black-76 assumes log-normal returns and constant volatility. Real options markets exhibit skew and term structure that the model approximates but does not capture perfectly.
