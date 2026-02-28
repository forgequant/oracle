# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Deribit options volatility — sentiment signal from skew, PCR, DVOL.

Part of the Crucible Oracle plugin.
API: deribit.com/api/v2/public (free, no auth)
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# --- Protocols (inline) ---
@dataclass
class SignalOutput:
    signal: str
    confidence: int
    reasoning: str
    data: dict[str, Any] = field(default_factory=dict)
    analytics: dict[str, Any] = field(default_factory=dict)
    schema: str = "signal/v1"

    def emit(self) -> None:
        print(json.dumps(asdict(self), ensure_ascii=False))

    def summary(self, text: str) -> None:
        print(text, file=sys.stderr)

@dataclass
class ErrorOutput:
    error: str
    details: str = ""
    schema: str = "error/v1"

    def emit(self, exit: bool = True) -> None:
        """Print error JSON. Pass exit=False inside asset loops to avoid killing process.

        BUG FIX: sys.exit(1) raises SystemExit (BaseException, NOT Exception).
        except Exception won't catch it → partial failure in --asset both breaks.
        """
        print(json.dumps(asdict(self), ensure_ascii=False))
        if exit:
            sys.exit(1)

BASE_URL = "https://deribit.com/api/v2"
MAX_RETRIES = 2
TIMEOUT_S = 10


def norm_cdf(x: float) -> float:
    """Cumulative normal distribution via erf approx (A&S 7.1.26). Error < 7.5e-8."""
    if x < -8.0:
        return 0.0
    if x > 8.0:
        return 1.0
    a1, a2, a3, a4, a5 = 0.254829592, -0.284496736, 1.421413741, -1.453152027, 1.061405429
    p = 0.3275911
    sign = 1 if x >= 0 else -1
    z = abs(x) / math.sqrt(2.0)
    t = 1.0 / (1.0 + p * z)
    erf_approx = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * math.exp(-z * z)
    return 0.5 * (1.0 + sign * erf_approx)

def black76_delta(F: float, K: float, T: float, iv: float) -> float:
    """Forward delta for call option (Black-76 model)."""
    if T <= 0:
        raise ValueError(f"T must be positive, got {T}")
    if iv <= 0:
        raise ValueError(f"iv must be positive, got {iv}")
    d1 = (math.log(F / K) + 0.5 * iv**2 * T) / (iv * math.sqrt(T))
    return norm_cdf(d1)

def _fetch_deribit(method: str, params: dict[str, Any] | None = None) -> Any:
    """Fetch from Deribit public API with retry. Returns result from JSON-RPC."""
    qs = "&".join(f"{k}={v}" for k, v in (params or {}).items())
    url = f"{BASE_URL}{method}" + (f"?{qs}" if qs else "")
    last_err: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(url, timeout=TIMEOUT_S) as resp:
                body = json.loads(resp.read())
            if "error" in body:
                raise ConnectionError(f"Deribit API error: {body['error'].get('message', body['error'])}")
            return body["result"]
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
            last_err = e
            if attempt < MAX_RETRIES:
                time.sleep(min(4, 0.3 * 2**attempt + random.uniform(0, 0.1)))
    raise ConnectionError(f"Deribit API failed after {MAX_RETRIES + 1} attempts: {last_err}")


def _filter_options(
    book_entries: list[dict],
    instruments: list[dict],
    min_t_days: float = 1.0,
    max_t_days: float = 180.0,
) -> list[dict]:
    now = time.time()
    inst_map = {i["instrument_name"]: i for i in instruments}
    result = []
    for entry in book_entries:
        name = entry["instrument_name"]
        iv_pct = entry.get("mark_iv")
        if iv_pct is None or iv_pct <= 0:
            continue
        inst = inst_map.get(name)
        if inst is None:
            continue
        expiry_s = inst["expiration_timestamp"] / 1000.0
        t_days = (expiry_s - now) / 86400.0
        if t_days < min_t_days or t_days > max_t_days:
            continue
        option_type = name.rsplit("-", 1)[-1]
        if option_type not in ("C", "P"):
            continue
        result.append({
            "name": name,
            "iv_decimal": iv_pct / 100.0,
            "T": t_days / 365.0,
            "strike": inst["strike"],
            "F": entry["underlying_price"],
            "option_type": option_type,
            "oi": entry["open_interest"],
            "contract_size": inst.get("contract_size", 1.0),
        })
    return result


def _find_25d_iv(
    options: list[dict],
    target_delta: float = 0.25,
    option_type: str = "C",
) -> tuple[float | None, bool]:
    """Find IV at 25-delta via interpolation. Returns (iv, was_interpolated)."""
    if not options:
        return None, False
    typed = [o for o in options if o["option_type"] == option_type]
    if not typed:
        return None, False

    enriched = []
    for o in typed:
        call_d = black76_delta(o["F"], o["strike"], o["T"], o["iv_decimal"])
        delta = abs(call_d - 1.0) if option_type == "P" else call_d
        enriched.append({**o, "_delta": delta})

    enriched.sort(key=lambda o: o["_delta"])

    below = [o for o in enriched if o["_delta"] <= target_delta]
    above = [o for o in enriched if o["_delta"] > target_delta]

    if below and above:
        lo = below[-1]
        hi = above[0]
        frac = (target_delta - lo["_delta"]) / (hi["_delta"] - lo["_delta"])
        iv = lo["iv_decimal"] + frac * (hi["iv_decimal"] - lo["iv_decimal"])
        return iv, True

    closest = min(enriched, key=lambda o: abs(o["_delta"] - target_delta))
    return closest["iv_decimal"], False


def enrich_with_deltas(options: list[dict]) -> list[dict]:
    """Add _delta (call delta magnitude) to each option. Returns NEW list, no mutation."""
    result = []
    for o in options:
        call_d = black76_delta(o["F"], o["strike"], o["T"], o["iv_decimal"])
        delta = abs(call_d - 1.0) if o["option_type"] == "P" else call_d
        result.append({**o, "_delta": delta})
    return result

def compute_rr25(call_25d_iv: float | None, put_25d_iv: float | None) -> float | None:
    if call_25d_iv is None or put_25d_iv is None:
        return None
    return round((call_25d_iv - put_25d_iv) * 100, 2)

def compute_pcr(
    options: list[dict],
    delta_min: float = 0.10,
    delta_max: float = 0.90,
) -> float | None:
    """Notional Put/Call Ratio. Options MUST have _delta key (use enrich_with_deltas first)."""
    filtered = [o for o in options if "_delta" in o and delta_min <= o["_delta"] <= delta_max]
    put_notional = sum(o["oi"] * o["contract_size"] * o["F"] for o in filtered if o["option_type"] == "P")
    call_notional = sum(o["oi"] * o["contract_size"] * o["F"] for o in filtered if o["option_type"] == "C")
    if call_notional == 0:
        return None
    return round(put_notional / call_notional, 4)


def main() -> None:
    ErrorOutput(error="not implemented").emit()

if __name__ == "__main__":
    main()
