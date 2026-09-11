"""Unit tests for calculate_price_change() (utils/scheduler.py)."""
import pytest
from utils.scheduler import calculate_price_change


def test_gain():
    assert calculate_price_change(100.0, 105.0) == pytest.approx(5.0)


def test_loss_is_absolute():
    assert calculate_price_change(100.0, 95.0) == pytest.approx(5.0)


def test_no_change():
    assert calculate_price_change(100.0, 100.0) == pytest.approx(0.0)


def test_zero_old_price():
    assert calculate_price_change(0, 5.0) == 100.0


def test_none_old_price():
    assert calculate_price_change(None, 5.0) == 100.0


def test_small_change_threshold_boundary():
    # 0.01% e'lon chegarasi atrofida aniqlik
    assert calculate_price_change(10000.0, 10001.0) == pytest.approx(0.01)
