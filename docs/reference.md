# Oracle — Reference

## Skill: deribit

### Auto-trigger Phrases

The `deribit` skill activates automatically when you ask Claude about:

- Options volatility, implied volatility (IV)
- Implied volatility skew
- Put/call ratio
- DVOL index
- Deribit options data
- Risk reversal

### CLI Usage

```bash
# Single asset
uv run skills/deribit/scripts/deribit.py --asset BTC

# Both assets
uv run skills/deribit/scripts/deribit.py --asset both

# Force fresh data (bypass cache)
uv run skills/deribit/scripts/deribit.py --asset ETH --no-cache

# Custom cache directory
uv run skills/deribit/scripts/deribit.py --asset BTC --cache-dir /tmp/oracle-cache

# Verbose output (debug information to stderr)
uv run skills/deribit/scripts/deribit.py --asset BTC --verbose
```

### Options

| Option | Values | Default | Description |
|--------|--------|---------|-------------|
| `--asset` | `BTC`, `ETH`, `both` | `BTC` | Asset(s) to analyze |
| `--cache-dir` | Path | `~/.cache/oracle/deribit/` | Cache directory |
| `--no-cache` | flag | off | Skip cache, always fetch fresh |
| `--verbose` | flag | off | Print debug info to stderr |

## Output Format

### stdout — signal/v1 JSON

```json
{
  "schema": "signal/v1",
  "signal": "bullish",
  "confidence": 67,
  "reasoning": "BTC: RR25=+4.8 (bullish skew), PCR=0.79 (bullish positioning), DVOL=52 (moderate vol regime)",
  "data": {
    "asset": "BTC",
    "rr25": 4.8,
    "pcr": 0.79,
    "dvol": 52.1,
    "term_structure_ratio": 0.93,
    "front_atm_iv": 61.2,
    "back_atm_iv": 65.8,
    "call_25d_iv": 68.4,
    "put_25d_iv": 63.6,
    "total_call_notional": 1240000000,
    "total_put_notional": 978000000,
    "snapshot_age_seconds": 142
  },
  "analytics": {
    "direction_score": 0.48,
    "skew_score": 0.52,
    "pcr_score": 0.43,
    "strength": 0.48,
    "agreement": 0.72,
    "data_quality": 0.97,
    "liquidity": 0.81,
    "dvol_modifier": 0.88,
    "ts_modifier": 1.0
  }
}
```

### stderr — Human Summary

```
[oracle/deribit] BTC options signal: BULLISH (confidence: 67)
  RR25: +4.8 (calls 4.8 vol pts pricier than puts — bullish skew)
  PCR:   0.79 (more notional in calls — bullish positioning)
  DVOL:  52.1 (moderate volatility regime, small confidence penalty)
  Term:  contango (no penalty)
  Cache: 2m 22s old
```

### Signal Values

| `signal` | Meaning |
|----------|---------|
| `bullish` | Options market tilted toward upside |
| `bearish` | Options market tilted toward downside |
| `neutral` | No clear directional skew |

### Confidence Scale

| Range | Interpretation |
|-------|---------------|
| 80-100 | Strong signal, high data quality, aligned indicators |
| 60-79 | Moderate signal, indicators mostly agree |
| 40-59 | Weak signal, mixed indicators or stale data |
| 15-39 | Very low conviction — treat as noise |

## Cache Files

| Path | Contents |
|------|---------|
| `~/.cache/oracle/deribit/snapshot_BTC.json` | Last BTC fetch with metadata |
| `~/.cache/oracle/deribit/snapshot_ETH.json` | Last ETH fetch with metadata |

Cache files are JSON. Delete to force a full reset, or use `--no-cache` for a one-time bypass.

## Troubleshooting

### No output / script hangs

The Deribit API may be temporarily unavailable. Check https://www.deribit.com/api/v2/public/test. If the API is up, try `--no-cache --verbose` to see what the script is doing.

### Stale data warning in output

The snapshot on disk is older than 1 hour. The signal is still computed but `data_quality` is penalized, reducing confidence. Run with `--no-cache` to refresh.

### `uv` not found

Install `uv`: `curl -LsSf https://astral.sh/uv/install.sh | sh`. Oracle scripts use PEP 723 inline deps and require `uv run` — standard `python` invocation will fail due to missing dependencies.

### Low confidence on both assets

This can occur when:
- DVOL is very high (>80), indicating a high-volatility regime
- Term structure is in strong backwardation (ratio > 1.2)
- Options chain has thin open interest (low liquidity)
- Cached data is older than 6 hours

Run with `--verbose` to see which factor is suppressing confidence.

### PCR or RR25 shows None

The options chain for that expiry may not have enough strikes to interpolate 25-delta. This can happen around expiry rollover when only near-dated contracts have open interest. Try again after the expiry rolls.

## Composing with Other Plugins

Oracle outputs `signal/v1` JSON, the same schema used by the sentinel plugin. You can pipe or combine both in a Claude conversation:

```
Oracle says BTC is bullish (confidence 67).
Sentinel's fear & greed is 28 (extreme fear, contrarian bullish).
Combined view: two independent sources align — conviction increases.
```

No programmatic aggregation is needed — Claude synthesizes both signal outputs in context.
