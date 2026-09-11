"""Unit tests for format_price() (main.py) across currencies and edges."""
from main import format_price


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
