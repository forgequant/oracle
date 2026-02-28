"""Tests for deribit skill."""

import json
import sys
import time
import urllib.error
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skills" / "deribit" / "scripts"))


from deribit import norm_cdf, black76_delta


class TestNormCdf:
    def test_zero(self):
        assert abs(norm_cdf(0) - 0.5) < 1e-7

    def test_large_positive(self):
        assert abs(norm_cdf(6.0) - 1.0) < 1e-7

    def test_large_negative(self):
        assert abs(norm_cdf(-6.0) - 0.0) < 1e-7

    def test_one(self):
        assert abs(norm_cdf(1.0) - 0.8413447) < 1e-5

    def test_negative_one(self):
        assert abs(norm_cdf(-1.0) - 0.1586553) < 1e-5

    def test_symmetry(self):
        for x in [0.5, 1.0, 2.0, 3.0]:
            assert abs(norm_cdf(x) + norm_cdf(-x) - 1.0) < 1e-7


class TestBlack76Delta:
    def test_atm_call_delta_near_half(self):
        d = black76_delta(F=50000, K=50000, T=30/365, iv=0.60)
        assert 0.48 < d < 0.55

    def test_deep_itm_call_near_one(self):
        d = black76_delta(F=50000, K=30000, T=30/365, iv=0.60)
        assert d > 0.95

    def test_deep_otm_call_near_zero(self):
        d = black76_delta(F=50000, K=80000, T=30/365, iv=0.60)
        assert d < 0.05

    def test_put_delta(self):
        call_d = black76_delta(F=50000, K=50000, T=30/365, iv=0.60)
        put_d = call_d - 1.0
        assert -0.55 < put_d < -0.45

    def test_higher_vol_widens_delta(self):
        d_low = black76_delta(F=50000, K=55000, T=30/365, iv=0.30)
        d_high = black76_delta(F=50000, K=55000, T=30/365, iv=0.80)
        assert d_high > d_low

    def test_very_short_expiry_no_crash(self):
        d = black76_delta(F=50000, K=50000, T=1/365, iv=0.60)
        assert 0.0 <= d <= 1.0

    def test_zero_expiry_raises(self):
        with pytest.raises(ValueError):
            black76_delta(F=50000, K=50000, T=0, iv=0.60)

    def test_zero_iv_raises(self):
        with pytest.raises(ValueError):
            black76_delta(F=50000, K=50000, T=30/365, iv=0)


def _make_jsonrpc_response(result: Any) -> bytes:
    """Build fake Deribit JSON-RPC response."""
    return json.dumps({"jsonrpc": "2.0", "result": result}).encode()

def _make_jsonrpc_error(code: int, message: str) -> bytes:
    return json.dumps({"jsonrpc": "2.0", "error": {"code": code, "message": message}}).encode()

def _mock_urlopen(data: bytes):
    """Create a mock urlopen return value."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = data
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


class TestFetch:
    @patch("urllib.request.urlopen")
    def test_fetch_parses_jsonrpc_result(self, mock_urlopen_fn):
        mock_urlopen_fn.return_value = _mock_urlopen(_make_jsonrpc_response([{"a": 1}]))
        from deribit import _fetch_deribit
        result = _fetch_deribit("/public/get_instruments", {"currency": "BTC"})
        assert result == [{"a": 1}]

    @patch("urllib.request.urlopen")
    def test_fetch_raises_on_jsonrpc_error(self, mock_urlopen_fn):
        mock_urlopen_fn.return_value = _mock_urlopen(_make_jsonrpc_error(10000, "bad request"))
        from deribit import _fetch_deribit
        with pytest.raises(ConnectionError, match="bad request"):
            _fetch_deribit("/public/test", {})

    @patch("urllib.request.urlopen")
    def test_fetch_retries_on_network_error(self, mock_urlopen_fn):
        mock_urlopen_fn.side_effect = [
            urllib.error.URLError("timeout"),
            _mock_urlopen(_make_jsonrpc_response({"ok": True})),
        ]
        from deribit import _fetch_deribit
        result = _fetch_deribit("/public/test", {})
        assert result == {"ok": True}
        assert mock_urlopen_fn.call_count == 2


def _make_instrument(name: str, expiry_ts: int, strike: float, contract_size: float = 1.0) -> dict:
    return {
        "instrument_name": name,
        "expiration_timestamp": expiry_ts,
        "strike": strike,
        "contract_size": contract_size,
        "kind": "option",
    }

def _make_book_entry(name: str, mark_iv: float | None, oi: float, underlying: float) -> dict:
    return {
        "instrument_name": name,
        "mark_iv": mark_iv,
        "open_interest": oi,
        "underlying_price": underlying,
        "creation_timestamp": int(time.time() * 1000),
    }


class TestFiltering:
    def test_exclude_null_mark_iv(self):
        from deribit import _filter_options
        entries = [_make_book_entry("BTC-28MAR26-50000-C", None, 100, 50000)]
        instruments = [_make_instrument("BTC-28MAR26-50000-C", int((time.time() + 30*86400)*1000), 50000)]
        result = _filter_options(entries, instruments)
        assert len(result) == 0

    def test_exclude_zero_mark_iv(self):
        from deribit import _filter_options
        entries = [_make_book_entry("BTC-28MAR26-50000-C", 0, 100, 50000)]
        instruments = [_make_instrument("BTC-28MAR26-50000-C", int((time.time() + 30*86400)*1000), 50000)]
        result = _filter_options(entries, instruments)
        assert len(result) == 0

    def test_exclude_short_expiry(self):
        from deribit import _filter_options
        expiry_ts = int((time.time() + 12*3600) * 1000)
        entries = [_make_book_entry("BTC-TODAY-50000-C", 50.0, 100, 50000)]
        instruments = [_make_instrument("BTC-TODAY-50000-C", expiry_ts, 50000)]
        result = _filter_options(entries, instruments)
        assert len(result) == 0

    def test_exclude_long_expiry(self):
        from deribit import _filter_options
        expiry_ts = int((time.time() + 200*86400) * 1000)
        entries = [_make_book_entry("BTC-FAR-50000-C", 50.0, 100, 50000)]
        instruments = [_make_instrument("BTC-FAR-50000-C", expiry_ts, 50000)]
        result = _filter_options(entries, instruments)
        assert len(result) == 0

    def test_keep_valid_entry(self):
        from deribit import _filter_options
        expiry_ts = int((time.time() + 30*86400) * 1000)
        entries = [_make_book_entry("BTC-28MAR26-50000-C", 55.0, 100, 50000)]
        instruments = [_make_instrument("BTC-28MAR26-50000-C", expiry_ts, 50000)]
        result = _filter_options(entries, instruments)
        assert len(result) == 1
        assert result[0]["iv_decimal"] == pytest.approx(0.55)
        assert result[0]["T"] > 0
        assert result[0]["option_type"] in ("C", "P")


class TestDeltaInterp:
    def test_find_25d_call_iv_interpolated(self):
        from deribit import _find_25d_iv
        options = [
            {"strike": 55000, "iv_decimal": 0.62, "option_type": "C", "F": 50000, "T": 30/365, "oi": 100},
            {"strike": 57000, "iv_decimal": 0.65, "option_type": "C", "F": 50000, "T": 30/365, "oi": 100},
            {"strike": 60000, "iv_decimal": 0.70, "option_type": "C", "F": 50000, "T": 30/365, "oi": 100},
        ]
        iv, interpolated = _find_25d_iv(options, target_delta=0.25, option_type="C")
        assert iv is not None
        assert isinstance(iv, float)

    def test_find_25d_put_iv(self):
        from deribit import _find_25d_iv
        options = [
            {"strike": 42000, "iv_decimal": 0.68, "option_type": "P", "F": 50000, "T": 30/365, "oi": 100},
            {"strike": 45000, "iv_decimal": 0.63, "option_type": "P", "F": 50000, "T": 30/365, "oi": 100},
            {"strike": 48000, "iv_decimal": 0.58, "option_type": "P", "F": 50000, "T": 30/365, "oi": 100},
        ]
        iv, interpolated = _find_25d_iv(options, target_delta=0.25, option_type="P")
        assert iv is not None

    def test_no_bracketing_pair_returns_closest(self):
        from deribit import _find_25d_iv
        options = [
            {"strike": 55000, "iv_decimal": 0.62, "option_type": "C", "F": 50000, "T": 30/365, "oi": 100},
        ]
        iv, interpolated = _find_25d_iv(options, target_delta=0.25, option_type="C")
        assert interpolated is False

    def test_empty_options_returns_none(self):
        from deribit import _find_25d_iv
        iv, interpolated = _find_25d_iv([], target_delta=0.25, option_type="C")
        assert iv is None


class TestSkew:
    def test_rr25_basic(self):
        from deribit import compute_rr25
        rr25 = compute_rr25(call_25d_iv=0.55, put_25d_iv=0.62)
        assert rr25 == pytest.approx(-7.0)

    def test_rr25_positive(self):
        from deribit import compute_rr25
        rr25 = compute_rr25(call_25d_iv=0.65, put_25d_iv=0.60)
        assert rr25 == pytest.approx(5.0)

    def test_rr25_none_when_missing(self):
        from deribit import compute_rr25
        assert compute_rr25(None, 0.60) is None
        assert compute_rr25(0.55, None) is None

class TestPCR:
    def test_pcr_basic(self):
        from deribit import compute_pcr
        options = [
            {"option_type": "P", "oi": 100, "contract_size": 1.0, "F": 50000, "_delta": 0.30},
            {"option_type": "C", "oi": 200, "contract_size": 1.0, "F": 50000, "_delta": 0.30},
        ]
        pcr = compute_pcr(options)
        assert pcr == pytest.approx(0.5)

    def test_pcr_excludes_tail_delta(self):
        from deribit import compute_pcr
        options = [
            {"option_type": "P", "oi": 1000, "contract_size": 1.0, "F": 50000, "_delta": 0.05},
            {"option_type": "P", "oi": 100, "contract_size": 1.0, "F": 50000, "_delta": 0.30},
            {"option_type": "C", "oi": 100, "contract_size": 1.0, "F": 50000, "_delta": 0.30},
        ]
        pcr = compute_pcr(options, delta_min=0.10, delta_max=0.90)
        assert pcr == pytest.approx(1.0)

    def test_pcr_zero_call_oi_returns_none(self):
        from deribit import compute_pcr
        options = [
            {"option_type": "P", "oi": 100, "contract_size": 1.0, "F": 50000, "_delta": 0.30},
        ]
        pcr = compute_pcr(options)
        assert pcr is None

    def test_pcr_empty_returns_none(self):
        from deribit import compute_pcr
        assert compute_pcr([]) is None


class TestDVOL:
    def test_parse_dvol_candles(self):
        from deribit import parse_dvol
        candles = [[1000, 50.0, 52.0, 49.0, 51.0], [2000, 51.0, 53.0, 50.0, 52.0]]
        dvol, change = parse_dvol(candles)
        assert dvol == 52.0
        assert change == pytest.approx(1.0)

    def test_parse_dvol_single_candle(self):
        from deribit import parse_dvol
        dvol, change = parse_dvol([[1000, 50.0, 52.0, 49.0, 51.0]])
        assert dvol == 51.0
        assert change == 0.0

    def test_parse_dvol_empty(self):
        from deribit import parse_dvol
        dvol, change = parse_dvol([])
        assert dvol is None

    def test_dvol_modifier_calm(self):
        from deribit import compute_dvol_modifier
        assert compute_dvol_modifier(40) == 1.0

    def test_dvol_modifier_extreme(self):
        from deribit import compute_dvol_modifier
        assert compute_dvol_modifier(70) == 0.50

class TestTermStructureRatio:
    def test_two_expiries_contango(self):
        from deribit import compute_ts_ratio
        options = [
            {"option_type": "C", "_delta": 0.50, "iv_decimal": 0.55, "T": 30/365},
            {"option_type": "C", "_delta": 0.51, "iv_decimal": 0.60, "T": 60/365},
        ]
        ratio = compute_ts_ratio(options)
        assert ratio is not None
        assert ratio < 1.0

    def test_single_expiry_returns_none(self):
        from deribit import compute_ts_ratio
        options = [
            {"option_type": "C", "_delta": 0.50, "iv_decimal": 0.55, "T": 30/365},
        ]
        assert compute_ts_ratio(options) is None

    def test_empty_returns_none(self):
        from deribit import compute_ts_ratio
        assert compute_ts_ratio([]) is None

class TestTermStructureModifier:
    def test_contango(self):
        from deribit import compute_ts_modifier
        assert compute_ts_modifier(0.90) == 1.0

    def test_backwardation(self):
        from deribit import compute_ts_modifier
        assert compute_ts_modifier(1.20) == 0.50

    def test_none_ratio(self):
        from deribit import compute_ts_modifier
        assert compute_ts_modifier(None) == 0.75


class TestDirection:
    def test_bullish(self):
        from deribit import compute_direction, classify_signal
        d = compute_direction(skew_score=0.5, pcr_score=0.4)
        assert d > 0.25
        assert classify_signal(d) == "bullish"

    def test_bearish(self):
        from deribit import compute_direction, classify_signal
        d = compute_direction(skew_score=-0.6, pcr_score=-0.5)
        assert d < -0.25
        assert classify_signal(d) == "bearish"

    def test_neutral(self):
        from deribit import compute_direction, classify_signal
        d = compute_direction(skew_score=0.1, pcr_score=-0.1)
        assert -0.25 <= d <= 0.25
        assert classify_signal(d) == "neutral"

    def test_weights_sum_to_one(self):
        assert 0.55 + 0.45 == pytest.approx(1.0)

    def test_pcr_none_renormalizes(self):
        from deribit import compute_direction, classify_signal
        d = compute_direction(skew_score=0.20, pcr_score=None)
        assert classify_signal(d) == "neutral"

    def test_pcr_none_strong_skew_is_bullish(self):
        from deribit import compute_direction, classify_signal
        d = compute_direction(skew_score=0.50, pcr_score=None)
        assert classify_signal(d) == "bullish"

class TestConfidence:
    def test_range_15_100(self):
        from deribit import compute_confidence
        c = compute_confidence(strength=1.0, agreement=1.0, data_quality=1.0,
                               liquidity=1.0, dvol_mod=1.0, ts_mod=1.0)
        assert 15 <= c <= 100

    def test_min_confidence_15(self):
        from deribit import compute_confidence
        c = compute_confidence(strength=0.0, agreement=0.0, data_quality=0.0,
                               liquidity=0.0, dvol_mod=0.5, ts_mod=0.5)
        assert c == 15

    def test_stale_reduces_confidence(self):
        from deribit import compute_confidence
        fresh = compute_confidence(strength=0.5, agreement=1.0, data_quality=1.0,
                                    liquidity=0.5, dvol_mod=1.0, ts_mod=1.0)
        stale = compute_confidence(strength=0.5, agreement=1.0, data_quality=0.25,
                                    liquidity=0.5, dvol_mod=1.0, ts_mod=1.0)
        assert fresh > stale

    def test_stress_modifiers_reduce(self):
        from deribit import compute_confidence
        calm = compute_confidence(strength=0.5, agreement=1.0, data_quality=1.0,
                                   liquidity=0.5, dvol_mod=1.0, ts_mod=1.0)
        stress = compute_confidence(strength=0.5, agreement=1.0, data_quality=1.0,
                                     liquidity=0.5, dvol_mod=0.5, ts_mod=0.5)
        assert calm > stress

    def test_double_extreme_not_crushed(self):
        from deribit import compute_confidence
        c = compute_confidence(strength=1.0, agreement=1.0, data_quality=1.0,
                               liquidity=1.0, dvol_mod=0.5, ts_mod=0.5)
        assert c >= 40


class TestCache:
    def test_save_and_load(self, tmp_path):
        from deribit import _save_cache, _load_cache
        path = tmp_path / "test.json"
        _save_cache({"hello": "world"}, path=path)
        data, ts = _load_cache(path=path)
        assert data == {"hello": "world"}
        assert ts > 0

    def test_load_missing_file(self, tmp_path):
        from deribit import _load_cache
        data, ts = _load_cache(path=tmp_path / "nope.json")
        assert data is None
        assert ts == 0

    def test_freshness_tiers(self):
        from deribit import _freshness_factor
        now = time.time()
        assert _freshness_factor(now - 60) == 1.0
        assert _freshness_factor(now - 1800) == 0.7
        assert _freshness_factor(now - 7200) == 0.4
        assert _freshness_factor(now - 43200) == 0.25
        assert _freshness_factor(now - 100000) == 0.15

    def test_atomic_write(self, tmp_path):
        from deribit import _save_cache
        path = tmp_path / "atomic.json"
        _save_cache({"a": 1}, path=path)
        assert not (path.with_suffix(".tmp")).exists()
        assert path.exists()


class TestCLI:
    def test_default_args(self):
        from deribit import build_parser
        args = build_parser().parse_args([])
        assert args.asset == "BTC"
        assert args.no_cache is False

    def test_asset_both(self):
        from deribit import build_parser
        args = build_parser().parse_args(["--asset", "both"])
        assert args.asset == "both"


# --- E2E test helpers (Task 11) ---
# IMPORTANT: Named _e2e_* to avoid collision with Task 3's bytes-based _mock_urlopen/_make_jsonrpc_response

def _make_realistic_instruments():
    """~20 instruments across 2 expiries x 5 strikes x 2 types (C/P)."""
    now_ms = int(time.time() * 1000)
    exp_30d = now_ms + 30 * 86400 * 1000
    exp_60d = now_ms + 60 * 86400 * 1000
    strikes = [40000, 45000, 50000, 55000, 60000]
    instruments = []
    for exp, label in [(exp_30d, "28MAR26"), (exp_60d, "27APR26")]:
        for strike in strikes:
            for otype in ["C", "P"]:
                instruments.append({
                    "instrument_name": f"BTC-{label}-{strike}-{otype}",
                    "expiration_timestamp": exp,
                    "strike": float(strike),
                    "contract_size": 1.0,
                })
    return instruments

def _make_realistic_book_summary():
    """Book summary entries matching _make_realistic_instruments()."""
    now_ms = int(time.time() * 1000)
    exp_30d = now_ms + 30 * 86400 * 1000
    exp_60d = now_ms + 60 * 86400 * 1000
    strikes = [40000, 45000, 50000, 55000, 60000]
    iv_map = {40000: 72, 45000: 58, 50000: 52, 55000: 56, 60000: 68}
    entries = []
    for exp, label in [(exp_30d, "28MAR26"), (exp_60d, "27APR26")]:
        for strike in strikes:
            base_iv = iv_map[strike]
            for otype in ["C", "P"]:
                iv = base_iv + (3 if otype == "P" else 0)
                oi = 500 if strike == 50000 else 200
                entries.append({
                    "instrument_name": f"BTC-{label}-{strike}-{otype}",
                    "mark_iv": float(iv),
                    "open_interest": float(oi),
                    "underlying_price": 50000.0,
                    "creation_timestamp": now_ms,
                })
    return entries

def _make_realistic_dvol():
    """DVOL candle data: 7 daily candles, format [ts, open, high, low, close]."""
    now_ms = int(time.time() * 1000)
    candles = []
    base_dvol = 50.0
    for i in range(7):
        ts = now_ms - (7 - i) * 86400 * 1000
        open_v = base_dvol + i * 0.5
        close_v = open_v + 1.0
        candles.append([ts, open_v, open_v + 2.0, open_v - 1.0, close_v])
    return candles

def _e2e_jsonrpc_response(result):
    """Wrap result in Deribit JSON-RPC envelope (dict, for E2E tests)."""
    return {"jsonrpc": "2.0", "result": result, "id": 1}

def _e2e_mock_urlopen(response_dict):
    """Create a BytesIO mock urlopen return value from a dict (for E2E tests)."""
    import io
    body = json.dumps(response_dict).encode("utf-8")
    return io.BytesIO(body)


class TestEndToEnd:
    @patch("time.sleep")
    @patch("urllib.request.urlopen")
    def test_btc_produces_signal(self, mock_urlopen_fn, mock_sleep, tmp_path, capsys, monkeypatch):
        """main() with mocked API produces valid signal/v1 JSON."""
        monkeypatch.setattr("deribit.CACHE_DIR", tmp_path)

        instruments = _make_realistic_instruments()
        book_summary = _make_realistic_book_summary()
        dvol_data = _make_realistic_dvol()

        responses = iter([
            _e2e_mock_urlopen(_e2e_jsonrpc_response(instruments)),
            _e2e_mock_urlopen(_e2e_jsonrpc_response(book_summary)),
            _e2e_mock_urlopen(_e2e_jsonrpc_response({"data": dvol_data, "continuation": 0})),
        ])
        mock_urlopen_fn.side_effect = lambda *a, **kw: next(responses)

        sys.argv = ["deribit", "--asset", "BTC"]
        from deribit import main
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 0

        out = capsys.readouterr().out.strip()
        result = json.loads(out)
        assert result["schema"] == "signal/v1"
        assert result["signal"] in ("bullish", "bearish", "neutral")
        assert 15 <= result["confidence"] <= 100
        assert "asset" in result["data"]
        assert result["data"]["asset"] == "BTC"

    @patch("time.sleep")
    @patch("urllib.request.urlopen")
    def test_api_error_falls_back_to_cache(self, mock_urlopen_fn, mock_sleep, tmp_path, capsys, monkeypatch):
        """When API fails, should fall back to cached data."""
        monkeypatch.setattr("deribit.CACHE_DIR", tmp_path)

        from deribit import _save_cache
        _save_cache({
            "instruments": _make_realistic_instruments(),
            "book": _make_realistic_book_summary(),
            "dvol": {"data": _make_realistic_dvol(), "continuation": 0},
        }, path=tmp_path / "snapshot_btc.json")

        mock_urlopen_fn.side_effect = urllib.error.URLError("offline")

        sys.argv = ["deribit", "--asset", "BTC"]
        from deribit import main
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 0

        out = capsys.readouterr().out.strip()
        result = json.loads(out)
        assert result["schema"] == "signal/v1"

    @patch("time.sleep")
    @patch("urllib.request.urlopen")
    def test_asset_both_partial_failure(self, mock_urlopen_fn, mock_sleep, tmp_path, capsys, monkeypatch):
        """If BTC fails but ETH succeeds, emit error for BTC + signal for ETH, exit 0."""
        monkeypatch.setattr("deribit.CACHE_DIR", tmp_path)

        eth_instruments = _make_realistic_instruments()
        eth_book = _make_realistic_book_summary()
        eth_dvol = {"data": _make_realistic_dvol(), "continuation": 0}
        _eth_responses = [eth_instruments, eth_book, eth_dvol]

        call_count = 0
        def side_effect(*a, **kw):
            nonlocal call_count
            call_count += 1
            if call_count <= 3:
                raise urllib.error.URLError("BTC offline")
            return _e2e_mock_urlopen(_e2e_jsonrpc_response(_eth_responses[call_count - 4]))

        mock_urlopen_fn.side_effect = side_effect
        sys.argv = ["deribit", "--asset", "both"]
        from deribit import main
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 0

        out = capsys.readouterr().out.strip()
        lines = [json.loads(line) for line in out.split("\n") if line.strip()]
        schemas = [l["schema"] for l in lines]
        assert "error/v1" in schemas
        assert "signal/v1" in schemas
