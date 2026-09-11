"""Unit tests for Postgres SQL translation (no live DB needed)."""
from utils.db_api.postgres import _translate


def test_placeholders_numbered_in_order():
    assert _translate("SELECT * FROM Users WHERE id=? AND x=?") == \
        "SELECT * FROM Users WHERE id=$1 AND x=$2"


def test_plain_sql_untouched():
    sql = "SELECT COUNT(*) FROM Users"
    assert _translate(sql) == sql


def test_insert_or_ignore_rewritten():
    assert _translate(
        "INSERT OR IGNORE INTO CryptoPreferences (user_id, coin_symbol) VALUES (?, ?)"
    ) == "INSERT INTO CryptoPreferences (user_id, coin_symbol) VALUES ($1, $2) ON CONFLICT DO NOTHING"


def test_limit_offset_params():
    assert _translate(
        "SELECT id FROM Users ORDER BY id LIMIT ? OFFSET ?"
    ) == "SELECT id FROM Users ORDER BY id LIMIT $1 OFFSET $2"
