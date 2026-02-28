---
name: deribit
description: >
  Use when the user asks about options volatility, implied volatility skew,
  put/call ratio, DVOL index, or wants a sentiment read from Deribit options
  data. Fetches BTC/ETH options chain from Deribit public API, computes
  25-delta skew, PCR, term structure, and DVOL regime modifiers.
version: 0.1.0
---

# Deribit Options Volatility

Options-derived sentiment signal from Deribit public API.

## API
- Source: `deribit.com/api/v2/public`
- Auth: None (free, public)
- Rate limit: ~5 req/sec (no auth)
- Endpoints: get_instruments, get_book_summary_by_currency, get_volatility_index_data

## Usage
```bash
uv run skills/deribit/scripts/deribit.py [options]
```

### Options
| Flag | Default | Description |
|------|---------|-------------|
| `--asset` | `BTC` | Asset to analyze: `BTC`, `ETH`, or `both` |
| `--cache-dir` | `~/.cache/oracle/deribit` | Cache directory |
| `--no-cache` | `false` | Skip cache read/write |
| `--verbose` | `false` | Extra logging to stderr |

## Output (SignalOutput v1)
```json
{
  "schema": "signal/v1",
  "signal": "bullish|bearish|neutral",
  "confidence": 15-100,
  "reasoning": "BTC RR25=5.2, PCR=0.85, DVOL=48 → bullish",
  "data": {
    "asset": "BTC",
    "rr25": 5.2,
    "pcr": 0.85,
    "dvol": 48.0,
    "dvol_change": -2.0,
    "ts_ratio": 0.92
  },
  "analytics": {
    "skew_score": 0.65,
    "pcr_score": 0.30,
    "direction": 0.49,
    "dvol_mod": 1.0,
    "ts_mod": 1.0,
    "data_quality": 1.0
  }
}
```

## Analytics
- **skew_score**: Normalized RR25 skew [-1, 1]. Positive = calls expensive = bullish
- **pcr_score**: Normalized PCR [-1, 1]. Low PCR = bullish
- **direction**: Weighted combo of skew + PCR (0.55/0.45)
- **dvol_mod**: DVOL regime modifier [0.5, 1.0]. High vol = lower confidence
- **ts_mod**: Term structure modifier [0.5, 1.0]. Backwardation = lower confidence
- **data_quality**: Freshness factor [0.15, 1.0]. Stale cache = lower confidence
