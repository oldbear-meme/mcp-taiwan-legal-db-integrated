# -*- coding: utf-8 -*-
"""工程會函釋查詢工具（政府採購法規解釋函令本地快取）

資料來源：行政院公共工程委員會「政府採購法規解釋函令及相關函文」
（planpe.pcc.gov.tw，公開資訊）。由 mcp_server/pcc_updater.py 增量更新，
查詢走本地 SQLite（離線、零延遲）。
"""

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

PCC_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "pcc_letters.db"


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(PCC_DB_PATH))
    c.row_factory = sqlite3.Row
    return c


def db_available() -> bool:
    return PCC_DB_PATH.exists()


def search_pcc_letters(
    keyword: str = "",
    article_no: str = "",
    law_name: str = "",
    letter_no: str = "",
    date_from: str = "",
    date_to: str = "",
    only_active: bool = True,
    max_results: int = 20,
    offset: int = 0,
) -> dict:
    """搜尋工程會函釋，回傳摘要清單（全文用 get_pcc_letter）。"""
    if not db_available():
        return {
            "success": False,
            "error": "pcc_letters.db 不存在；請先執行 python -m mcp_server.pcc_updater 建庫。",
        }
    conn = _conn()
    try:
        where, params = [], []
        if only_active:
            where.append("l.status='active'")
        if article_no:
            where.append(
                "l.letter_id IN (SELECT letter_id FROM pcc_letter_articles WHERE article_no=?)"
            )
            params.append(article_no.replace("之", "-").strip())
        if law_name:
            where.append("l.law_name LIKE ?")
            params.append(f"%{law_name}%")
        if letter_no:
            where.append("l.letter_no LIKE ?")
            params.append(f"%{letter_no}%")
        if date_from:
            where.append("l.issue_date>=?")
            params.append(date_from)
        if date_to:
            where.append("l.issue_date<=?")
            params.append(date_to)
        if keyword:
            where.append("(l.subject LIKE ? OR l.full_text LIKE ?)")
            params.extend([f"%{keyword}%", f"%{keyword}%"])
        wsql = (" WHERE " + " AND ".join(where)) if where else ""
        total = conn.execute(
            f"SELECT COUNT(*) n FROM pcc_letters l{wsql}", params
        ).fetchone()["n"]
        rows = conn.execute(
            f"""SELECT letter_id,letter_no,law_name,subject,issue_date_roc,status
                FROM pcc_letters l{wsql} ORDER BY issue_date DESC LIMIT ? OFFSET ?""",
            params + [max_results, offset],
        ).fetchall()
        results = []
        for r in rows:
            arts = [
                a["article_no"]
                for a in conn.execute(
                    "SELECT article_no FROM pcc_letter_articles WHERE letter_id=? ORDER BY article_no",
                    (r["letter_id"],),
                )
            ]
            results.append(
                dict(
                    letter_id=r["letter_id"],
                    letter_no=r["letter_no"],
                    law_name=r["law_name"],
                    articles=arts,
                    subject=r["subject"],
                    issue_date_roc=r["issue_date_roc"],
                    status=r["status"],
                )
            )
        return {
            "success": True,
            "total": total,
            "returned": len(results),
            "results": results,
        }
    finally:
        conn.close()


def get_pcc_letter(letter_id: str = "", letter_no: str = "") -> dict:
    """取得單一工程會函釋全文。letter_id 與 letter_no 擇一。"""
    if not (letter_id or letter_no):
        return {"success": False, "error": "請提供 letter_id 或 letter_no。"}
    if not db_available():
        return {
            "success": False,
            "error": "pcc_letters.db 不存在；請先執行 python -m mcp_server.pcc_updater 建庫。",
        }
    conn = _conn()
    try:
        if letter_id:
            row = conn.execute(
                "SELECT * FROM pcc_letters WHERE letter_id=?", (letter_id,)
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM pcc_letters WHERE letter_no LIKE ?",
                (f"%{letter_no}%",),
            ).fetchone()
        if not row:
            return {
                "success": False,
                "error": "查無此函釋；可先用 search_pcc_letters 以關鍵字或條號定位。",
            }
        arts = [
            a["article_no"]
            for a in conn.execute(
                "SELECT article_no FROM pcc_letter_articles WHERE letter_id=? ORDER BY article_no",
                (row["letter_id"],),
            )
        ]
        return {
            "success": True,
            "letter_id": row["letter_id"],
            "letter_no": row["letter_no"],
            "law_name": row["law_name"],
            "based_on": row["based_on"],
            "articles": arts,
            "subject": row["subject"],
            "full_text": row["full_text"],
            "issuer": row["issuer"],
            "issue_date_roc": row["issue_date_roc"],
            "issue_date": row["issue_date"],
            "status": row["status"],
            "superseded_by": row["superseded_by"],
            "status_note": row["status_note"],
            "source_url": row["source_url"],
            "fetched_at": row["fetched_at"],
            "_note": "工程會函釋僅供審查參考；條文真義仍應以採購法現行條文及最新函釋為準。",
        }
    finally:
        conn.close()
