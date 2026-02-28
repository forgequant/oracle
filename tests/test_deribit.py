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
