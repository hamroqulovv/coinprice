"""Unit tests for scheduler alert helpers (pure functions, no network/DB)."""
from utils.scheduler import _split_alerts, calculate_price_change


def _line(coin="BTC", usd=77821.34):
    return {"coin": coin, "emoji": "📈",
            "price": {"usd": usd, "rub": 1.0, "uzs": 1000.0},
            "change": 1.5, "diff": 1.0, "sign": "+"}


def test_single_chunk_small():
    chunks = _split_alerts([_line()], 10)
    assert len(chunks) == 1
    assert "Narx o'zgarishlari" in chunks[0]
    assert "Keyingi tekshirish: 10s" in chunks[0]


def test_chunks_respect_limit():
    lines = [_line(coin="C%03d" % i, usd=100.0 + i) for i in range(60)]
    chunks = _split_alerts(lines, 10)
    assert len(chunks) > 1
    assert all(len(c) <= 4096 for c in chunks)
    joined = "\n".join(chunks)
    assert "C000" in joined and "C059" in joined


def test_change_gate_boundary():
    assert calculate_price_change(10000.0, 10001.0) >= 0.01
    assert calculate_price_change(10000.0, 10000.5) < 0.01
