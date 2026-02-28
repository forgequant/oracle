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
