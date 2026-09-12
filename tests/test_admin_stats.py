"""Unit tests: admin statistika + user helper'lari (main.py).

Throwaway SQLite'da ishlaydi - real main.db'ga tegilmaydi.
"""
import asyncio

import pytest

import main as m
from utils.db_api.sqlite import Database


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def adb(tmp_path, monkeypatch):
    db = Database(path_to_db=str(tmp_path / "admin.db"))
    _run(db.create_tables())
    monkeypatch.setattr(m, "db", db)
    return db


def _add_user(db, uid, name, view=0, daily=0, day=None, month_v=0, month=None):
    _run(db.execute(
        "INSERT INTO Users (id, phone, username, full_name, interval_min, is_premium,"
        " view_count, daily_views, last_view_date, month_views, last_view_month)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (uid, "+998900000000", f"user{uid}", name, 10, False,
         view, daily, day, month_v, month), commit=True))


def test_stats_empty(adb):
    assert _run(m.get_admin_stats()) == {
        "total_users": 0, "today_requests": 0,
        "month_requests": 0, "total_requests": 0,
    }


def test_stats_sums_only_current_day_month(adb):
    today, month = m._today_str(), m._month_str()
    _add_user(adb, 1, "A", view=5, daily=2, day=today, month_v=3, month=month)
    _add_user(adb, 2, "B", view=7, daily=9, day="2000-01-01", month_v=9, month="2000-01")
    s = _run(m.get_admin_stats())
    assert s["total_users"] == 2
    assert s["total_requests"] == 12
    assert s["today_requests"] == 2  # eski kun qo'shilmaydi
    assert s["month_requests"] == 3  # eski oy qo'shilmaydi


def test_bump_counters_same_day_and_rollover(adb):
    today, month = m._today_str(), m._month_str()
    _add_user(adb, 9, "C", view=4, daily=4, day=today, month_v=4, month=month)
    _add_user(adb, 10, "D", view=4, daily=4, day="2000-01-01", month_v=4, month="2000-01")
    _run(m.bump_lookup_counters(9))
    _run(m.bump_lookup_counters(10))
    c9 = _run(m.get_user_card(9))
    assert (c9["view_count"], c9["daily_views"], c9["month_views"]) == (5, 5, 5)
    c10 = _run(m.get_user_card(10))
    assert (c10["view_count"], c10["daily_views"], c10["month_views"]) == (5, 1, 1)


def test_user_page_card_delete(adb):
    for i in range(1, 13):
        _add_user(adb, i, f"User{i}", view=i)
    rows, total, page, pages = _run(m.get_user_page(0))
    assert (total, page, pages, len(rows)) == (12, 0, 2, 10)
    rows2, _, page2, _ = _run(m.get_user_page(99))  # chegaradan tashqarisi clamp
    assert page2 == 1 and len(rows2) == 2
    card = _run(m.get_user_card(3))
    assert card["full_name"] == "User3" and card["view_count"] == 3
    assert card["watch_count"] == 0
    assert _run(m.get_user_card(999)) is None
    assert _run(m.delete_user(3)) is True
    assert _run(m.get_user_card(3)) is None
    assert _run(m.delete_user(3)) is False
