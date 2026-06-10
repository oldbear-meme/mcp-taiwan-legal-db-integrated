# -*- coding: utf-8 -*-
"""pcc_letters 工具與 pcc_updater 單元測試（不連網）"""

import sqlite3

import pytest

from mcp_server import pcc_updater
from mcp_server.tools import pcc_letters


@pytest.fixture
def pcc_db(tmp_path, monkeypatch):
    """建一個含兩筆函釋的暫存 db，並把模組路徑指過去"""
    db_path = tmp_path / "pcc_letters.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(pcc_updater.SCHEMA_SQL)
    conn.execute(
        """INSERT INTO pcc_letters
           (letter_id,letter_no,law_name,based_on,subject,full_text,issuer,
            issue_date,issue_date_roc,status,source_url,fetched_at)
           VALUES ('10000001','工程企字第10000000001號','政府採購法',
                   '政府採購法第22條','機關首長核定權限疑義',
                   '主旨：機關首長核定權限疑義。說明：……','企劃處',
                   '2020-01-15','109.01.15','active','https://planpe.pcc.gov.tw/x','2026-01-01T00:00:00')"""
    )
    conn.execute(
        """INSERT INTO pcc_letters
           (letter_id,letter_no,law_name,based_on,subject,full_text,issuer,
            issue_date,issue_date_roc,status,source_url,fetched_at)
           VALUES ('10000002','工程企字第10000000002號','政府採購法',
                   '政府採購法第63條','契約變更（已停止適用）',
                   '主旨：契約變更。說明：本函自即日起停止適用。','企劃處',
                   '2015-06-01','104.06.01','superseded','https://planpe.pcc.gov.tw/y','2026-01-01T00:00:00')"""
    )
    conn.execute(
        "INSERT INTO pcc_letter_articles(letter_id,law_name,article_no) VALUES('10000001','政府採購法','22')"
    )
    conn.execute(
        "INSERT INTO pcc_letter_articles(letter_id,law_name,article_no) VALUES('10000002','政府採購法','63')"
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(pcc_letters, "PCC_DB_PATH", db_path)
    return db_path


def test_search_by_keyword(pcc_db):
    r = pcc_letters.search_pcc_letters(keyword="機關首長")
    assert r["success"] is True
    assert r["total"] == 1
    assert r["results"][0]["letter_no"] == "工程企字第10000000001號"
    assert r["results"][0]["articles"] == ["22"]


def test_search_by_article_no(pcc_db):
    r = pcc_letters.search_pcc_letters(article_no="22")
    assert r["total"] == 1
    assert r["results"][0]["letter_id"] == "10000001"


def test_only_active_filters_superseded(pcc_db):
    active = pcc_letters.search_pcc_letters(keyword="契約變更", only_active=True)
    assert active["total"] == 0
    everything = pcc_letters.search_pcc_letters(keyword="契約變更", only_active=False)
    assert everything["total"] == 1
    assert everything["results"][0]["status"] == "superseded"


def test_get_by_letter_no(pcc_db):
    r = pcc_letters.get_pcc_letter(letter_no="10000000001")
    assert r["success"] is True
    assert r["letter_id"] == "10000001"
    assert "full_text" in r and r["full_text"].startswith("主旨")


def test_get_requires_identifier(pcc_db):
    r = pcc_letters.get_pcc_letter()
    assert r["success"] is False


def test_get_not_found(pcc_db):
    r = pcc_letters.get_pcc_letter(letter_id="99999999")
    assert r["success"] is False


def test_missing_db_returns_error(tmp_path, monkeypatch):
    monkeypatch.setattr(pcc_letters, "PCC_DB_PATH", tmp_path / "nope.db")
    r = pcc_letters.search_pcc_letters(keyword="x")
    assert r["success"] is False


def test_roc_to_iso():
    assert pcc_updater._roc_to_iso("115.04.29") == "2026-04-29"
    assert pcc_updater._roc_to_iso("") is None


def test_should_update_fresh_checkpoint(pcc_db, monkeypatch):
    conn = sqlite3.connect(str(pcc_db))
    from datetime import datetime, timezone

    conn.execute(
        "INSERT INTO crawl_checkpoint(key,value) VALUES('last_check',?)",
        (datetime.now(timezone.utc).isoformat(),),
    )
    conn.commit()
    conn.close()
    should, reason = pcc_updater.should_update(pcc_db)
    assert should is False


def test_should_update_no_checkpoint(pcc_db):
    should, reason = pcc_updater.should_update(pcc_db)
    assert should is True
