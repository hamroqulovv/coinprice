"""Unit tests for format_price() (utils.format) across currencies and edges."""
import math

from utils.format import format_alert_block, format_price


def test_usd_large():
    assert format_price(77821.34, "USD") == "$77,821.34"


def test_usd_medium():
    assert format_price(0.0847, "USD") == "$0.0847"


def test_usd_small():
    assert format_price(0.00000515, "USD") == "$0.00000515"


def test_usd_zero():
    assert format_price(0, "USD") == "$0.00000000"


def test_rub_large():
    assert format_price(6564292.28, "RUB") == "6,564,292.28 \u20bd"


def test_rub_small():
    assert format_price(0.0004, "RUB") == "0.000400 \u20bd"


def test_uzs_large_thousands_separator():
    assert format_price(1234567, "UZS") == "1,234,567 so'm"


def test_uzs_large_realistic():
    assert format_price(917005425.25, "UZS") == "917,005,425 so'm"


def test_uzs_small():
    assert format_price(5.04, "UZS") == "5.04 so'm"


def test_uzs_zero():
    assert format_price(0, "UZS") == "0.0000 so'm"


def test_uzs_negative():
    assert format_price(-1234567, "UZS") == "-1,234,567 so'm"


def test_invalid_value():
    assert format_price("abc", "USD") == "N/A"


def test_none_value():
    assert format_price(None, "USD") == "N/A"


def test_unknown_currency():
    assert format_price(5, "EUR") == "5"


def test_boundaries():
    assert format_price(1, "USD") == "$1.00"
    assert format_price(0.01, "USD") == "$0.0100"
    assert format_price(0.0001, "USD") == "$0.000100"
    assert format_price(1000, "UZS") == "1,000 so'm"
    assert format_price(1, "RUB") == "1.00 \u20bd"


def test_inf_nan():
    assert format_price(math.inf, "USD") == "$inf"
    assert format_price(math.nan, "USD") == "$nan"


def test_alert_block():
    line = {"coin": "BTC", "emoji": "📈",
            "price": {"usd": 77821.34, "rub": 6564292.28, "uzs": 917005425.25},
            "change": 1.234, "diff": 950.0, "sign": "+"}
    block = format_alert_block(line)
    assert "📈 <b>BTC</b>" in block
    assert "$77,821.34" in block
    assert "+1.23%" in block
    assert "917,005,425 so'm" in block


def test_alert_block_first_time_no_change():
    line = {"coin": "TON", "emoji": "💰",
            "price": {"usd": 1.37, "rub": 115.0, "uzs": 16142.0, "name": "Toncoin"},
            "change": None, "diff": None, "sign": ""}
    block = format_alert_block(line)
    assert "(Toncoin)" in block
    assert "📊" not in block
