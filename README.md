# Oracle

On-chain and macro data signals for crypto trading.

Part of the [Crucible](https://github.com/forgequant) plugin collection.

## Skills

| Skill | Source | Cost |
|-------|--------|------|
| deribit | Deribit public API | Free |

## Usage

```bash
# Single asset
uv run skills/deribit/scripts/deribit.py --asset BTC

# Both assets
uv run skills/deribit/scripts/deribit.py --asset both

# Skip cache
uv run skills/deribit/scripts/deribit.py --asset ETH --no-cache
```

## Output

Signal/v1 JSON to stdout, human summary to stderr:

```json
{
  "schema": "signal/v1",
  "signal": "bullish",
  "confidence": 62,
  "reasoning": "BTC RR25=5.2, PCR=0.85, DVOL=48 → bullish"
}
```

## Testing

```bash
python3 -m pytest tests/ -v
```
