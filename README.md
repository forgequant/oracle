# Oracle

<div align="center">

**Surface volatility signals from crypto options markets**

![Claude Code Plugin](https://img.shields.io/badge/Claude_Code-Plugin-5b21b6?style=flat-square)
![Version](https://img.shields.io/badge/version-0.1.0-5b21b6?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-5b21b6?style=flat-square)

```bash
claude plugin marketplace add heurema/emporium
claude plugin install oracle@emporium
```

</div>

## What it does

Crypto options markets encode trader positioning and volatility expectations, but the raw data requires significant computation to interpret. Oracle fetches Deribit public API data and computes a structured set of volatility signals — IV skew, put/call ratio, DVOL regime, and term structure shape — then emits them as `signal/v1` JSON compatible with the forgequant plugin stack. Unlike generic market data tools, Oracle applies a weighted confidence model that degrades signal quality under high-volatility or low-liquidity conditions.

## Install

<!-- INSTALL:START -->
```bash
claude plugin marketplace add heurema/emporium
claude plugin install oracle@emporium
```
<!-- INSTALL:END -->

<details>
<summary>Manual install from source</summary>

```bash
git clone https://github.com/forgequant/oracle
cd oracle
claude plugin install .
```

Python 3.14 and `uv` are required. Dependencies are declared inline (PEP 723) and resolved automatically by `uv run`.

</details>

## Quick start

Ask Claude about options volatility — the `deribit` command triggers automatically:

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

## Commands

| Command | Trigger | Description |
|---------|---------|-------------|
| `deribit` | Options volatility, IV skew, DVOL, put/call ratio | Fetches Deribit options data and computes volatility signals |

## Features

**Signals computed**

| Signal | Formula | Interpretation |
|--------|---------|----------------|
| RR25 (risk reversal) | `call_25d_IV - put_25d_IV` | Positive = calls pricier = bullish skew |
| PCR (put/call ratio) | `put_notional / call_notional` | Low value = bullish positioning |
| DVOL modifier | Volatility regime factor | High DVOL reduces confidence |
| Term structure ratio | `front_ATM_IV / back_ATM_IV` | Backwardation reduces confidence |

Direction score: `0.55 * skew_score + 0.45 * pcr_score`. Confidence: `0.40 * strength + 0.25 * agreement + 0.25 * data_quality + 0.10 * liquidity`, scaled by `min(dvol_modifier, ts_modifier)`. Range: [15, 100].

**Output format**

Signal protocol `signal/v1` — JSON to stdout, human summary to stderr:

```json
{
  "schema": "signal/v1",
  "signal": "bullish",
  "confidence": 62,
  "reasoning": "BTC RR25=5.2, PCR=0.85, DVOL=48 — bullish skew with moderate conviction",
  "data": { "..." : "..." },
  "analytics": { "..." : "..." }
}
```

**Caching**

Snapshots are written atomically to `~/.cache/oracle/deribit/snapshot_{asset}.json`. Confidence degrades with snapshot age:

| Age | Quality multiplier |
|-----|-------------------|
| < 5 min | 1.0 |
| < 1 h | 0.7 |
| < 6 h | 0.4 |
| < 24 h | 0.25 |
| Older | 0.15 |

Use `--no-cache` to force a fresh fetch.

CLI options: `--asset BTC|ETH|both`, `--cache-dir PATH`, `--no-cache`, `--verbose`.

## Requirements

- No API keys. Deribit public API is free and unauthenticated.
- Network access required — see Privacy.
- Python 3.14 via `uv run` (PEP 723 inline dependencies, no manual install needed).

## Privacy

Oracle makes outbound network requests to `api.deribit.com` each time a signal is computed. No data is sent to any third party other than Deribit. Responses are cached locally at `~/.cache/oracle/`. No telemetry is collected by this plugin.

## See also

- [skill7.dev](https://skill7.dev) — plugin registry and docs
- [emporium](https://github.com/heurema/emporium) — forgequant plugin marketplace
- [sentinel](https://github.com/forgequant/sentinel) — alert plugin, composes with Oracle signals

## License

[MIT](LICENSE)
