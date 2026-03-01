# Oracle

**On-chain and macro data signals for crypto trading — options volatility, exchange flows, prediction markets.**

Version: 0.1.0 (alpha) | Author: forgequant | License: MIT

---

## Overview

Oracle is a Claude Code plugin that surfaces structured volatility signals from crypto options markets. The current implementation focuses on Deribit options data: implied volatility skew, put/call ratio, DVOL index, and term structure shape. Signals are emitted as `signal/v1` JSON to stdout and are designed to compose with other plugins in the forgequant stack.

## Quick Start

Ask Claude about options volatility — the `deribit` skill triggers automatically:

```
What does BTC options skew look like right now?
Is ETH implied volatility in backwardation?
Show me the put/call ratio for BTC.
```

Or invoke directly:

```
/deribit --asset BTC
/deribit --asset ETH
/deribit --asset both
```

## Skills

| Skill | Trigger | Description |
|-------|---------|-------------|
| `deribit` | Options volatility, IV skew, DVOL, put/call ratio | Fetches Deribit options data and computes volatility signals |

## Requirements

- **API keys:** None. Deribit public API is free and unauthenticated.
- **Network:** Yes — connects to the Deribit public API.
- **Runtime:** Python 3.14 via `uv run` (PEP 723 inline dependencies, no manual install needed).

## Signals Computed

| Signal | Formula | Interpretation |
|--------|---------|----------------|
| RR25 (risk reversal) | `call_25d_IV - put_25d_IV` | Positive = calls pricier = bullish skew |
| PCR (put/call ratio) | `put_notional / call_notional` | Low value = bullish positioning |
| DVOL modifier | Volatility regime factor | High DVOL reduces confidence |
| Term structure ratio | `front_ATM_IV / back_ATM_IV` | Backwardation reduces confidence |

Weighted direction score: `0.55 * skew_score + 0.45 * pcr_score`

Confidence formula: `0.40 * strength + 0.25 * agreement + 0.25 * data_quality + 0.10 * liquidity`, scaled by `min(dvol_modifier, ts_modifier)`. Range: [15, 100].

## Output Format

Signal protocol `signal/v1` — JSON to stdout, human summary to stderr:

```json
{
  "schema": "signal/v1",
  "signal": "bullish",
  "confidence": 62,
  "reasoning": "BTC RR25=5.2, PCR=0.85, DVOL=48 — bullish skew with moderate conviction",
  "data": { ... },
  "analytics": { ... }
}
```

## Caching

Snapshots are written atomically to `~/.cache/oracle/deribit/snapshot_{asset}.json`. Freshness decay:

| Age | Quality multiplier |
|-----|-------------------|
| < 5 min | 1.0 |
| < 1 h | 0.7 |
| < 6 h | 0.4 |
| < 24 h | 0.25 |
| Older | 0.15 |

Use `--no-cache` to force a fresh fetch.

## CLI Reference

```bash
uv run skills/deribit/scripts/deribit.py --asset BTC
uv run skills/deribit/scripts/deribit.py --asset both --no-cache
uv run skills/deribit/scripts/deribit.py --asset ETH --verbose --cache-dir /tmp/oracle
```

Options: `--asset BTC|ETH|both`, `--cache-dir PATH`, `--no-cache`, `--verbose`

## Testing

```bash
python3 -m pytest tests/ -v
```

## Status

Alpha. Only the `deribit` skill is implemented. Exchange flows and prediction market integrations are planned for future releases.

---

> This plugin provides data signals for informational purposes only. It does not constitute financial advice. Past performance does not indicate future results. Always do your own research before making trading decisions.
