# Oracle — Agent Instructions

## What
On-chain and macro data signals for crypto trading. Part of the crucible plugin collection.

## Skills
| Skill | API | Cost | Status |
|-------|-----|------|--------|
| deribit | Deribit v2 public | Free | v1 |

## Signal Protocol
All skills output SignalOutput v1 to stdout:
```json
{
  "schema": "signal/v1",
  "signal": "bullish|bearish|neutral",
  "confidence": 0-100,
  "reasoning": "brief explanation",
  "data": { ... },
  "analytics": { ... }
}
```
Human-readable summary goes to stderr.

## Skill Scripts
- Location: `skills/<name>/scripts/<name>.py`
- Run via: `uv run skills/<name>/scripts/<name>.py [args]`
- PEP 723 inline dependencies
- Shared code: `lib/protocols.py`

## Conventions
- No API keys in code — env vars only
- Graceful degradation when optional keys are missing
- Free path (all current skills) must work standalone
