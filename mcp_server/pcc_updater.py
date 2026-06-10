# -*- coding: utf-8 -*-
"""工程會函釋增量更新器

從行政院公共工程委員會「政府採購法規解釋函令」公開查詢系統
（planpe.pcc.gov.tw）增量抓取新函釋進 mcp_server/data/pcc_letters.db。

設計：
  - 清單依 createDate 由新到舊排序；逐頁抓取，遇到「整頁都已入庫」即停
    （增量早停），全量重建時則跑到連續空頁為止。
  - 伺服器啟動時由 server.py 以背景工作呼叫 maybe_update()，預設每 7 天
    檢查一次；失敗只記警告，不影響查詢（查的是本地快取）。
  - 禮貌頻率 1.5 秒/請求，勿調低；函釋屬公開法令資訊。

手動執行：
  python -m mcp_server.pcc_updater            # 增量更新
  python -m mcp_server.pcc_updater --full     # 全量補抓（仍跳過已入庫）
  python -m mcp_server.pcc_updater --max 30   # 最多新增 30 則（測試）
"""

import argparse
import logging
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

from mcp_server.ssl_setup import inject_os_trust_store

inject_os_trust_store()

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

PCC_DB_PATH = Path(__file__).resolve().parent / "data" / "pcc_letters.db"

BASE = "https://planpe.pcc.gov.tw"
SEARCH_PAGE = BASE + "/prms/explainLetter/readPrmsExplainLetterSearch"
LIST_POST = BASE + "/prms/explainLetter/readPrmsExplainLetter"
DETAIL_GET = BASE + "/prms/explainLetter/readPrmsExplainLetterContentDetail"

REQUEST_DELAY = 1.5  # 秒，禮貌間隔（勿調低）
TIMEOUT = 30.0
MAX_RETRIES = 3
PAGE_SIZE = 100
UPDATE_INTERVAL_DAYS = 7  # 啟動時自動檢查的最小間隔

PK_PATTERNS = [
    re.compile(r"readExplainLetter\((\d+)\)"),
    re.compile(r"pkPrmsRuleContent['\"=:\s,()]*?(\d{5,})"),
]

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS pcc_letters (
    letter_id      TEXT PRIMARY KEY,
    letter_no      TEXT,
    law_name       TEXT,
    based_on       TEXT,
    subject        TEXT,
    full_text      TEXT,
    issuer         TEXT,
    issue_date     TEXT,
    issue_date_roc TEXT,
    status         TEXT DEFAULT 'active',
    superseded_by  TEXT,
    status_note    TEXT,
    source_url     TEXT,
    fetched_at     TEXT
);
CREATE TABLE IF NOT EXISTS pcc_letter_articles (
    letter_id  TEXT NOT NULL,
    law_name   TEXT,
    article_no TEXT NOT NULL,
    PRIMARY KEY (letter_id, article_no),
    FOREIGN KEY (letter_id) REFERENCES pcc_letters(letter_id)
);
CREATE INDEX IF NOT EXISTS idx_pcc_status ON pcc_letters(status);
CREATE INDEX IF NOT EXISTS idx_pcc_date   ON pcc_letters(issue_date);
CREATE INDEX IF NOT EXISTS idx_pcc_law    ON pcc_letters(law_name);
CREATE INDEX IF NOT EXISTS idx_pcc_art    ON pcc_letter_articles(article_no);
CREATE TABLE IF NOT EXISTS crawl_checkpoint (key TEXT PRIMARY KEY, value TEXT);
"""


# ──────────── DB ────────────
def _get_db() -> sqlite3.Connection:
    PCC_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(PCC_DB_PATH))
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA_SQL)  # 確保表存在（不覆蓋資料）
    return c


def _already_have(conn: sqlite3.Connection, pk: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM pcc_letters WHERE letter_id=?", (pk,)
        ).fetchone()
        is not None
    )


def _get_checkpoint(conn: sqlite3.Connection, key: str) -> str:
    row = conn.execute(
        "SELECT value FROM crawl_checkpoint WHERE key=?", (key,)
    ).fetchone()
    return row["value"] if row else ""


def _set_checkpoint(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO crawl_checkpoint(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    conn.commit()


def should_update(path: Path | None = None) -> tuple[bool, str]:
    """是否該做增量檢查（距上次檢查 >= UPDATE_INTERVAL_DAYS 天）。"""
    db_path = path or PCC_DB_PATH
    if not db_path.exists():
        return True, "pcc_letters.db 不存在，需建庫"
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT value FROM crawl_checkpoint WHERE key='last_check'"
        ).fetchone()
        conn.close()
    except sqlite3.Error as e:
        return True, f"讀取 checkpoint 失敗: {e}"
    if not row or not row["value"]:
        return True, "尚無更新紀錄"
    try:
        last = datetime.fromisoformat(row["value"])
    except ValueError:
        return True, f"無法解析上次檢查時間: {row['value']}"
    age = (datetime.now(timezone.utc) - last).days
    if age >= UPDATE_INTERVAL_DAYS:
        return True, f"距上次檢查已 {age} 天"
    return False, f"距上次檢查 {age} 天，未達 {UPDATE_INTERVAL_DAYS} 天"


# ──────────── HTTP ────────────
def _make_client() -> httpx.Client:
    return httpx.Client(
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "zh-TW,zh;q=0.9",
        },
        timeout=TIMEOUT,
        follow_redirects=True,
        verify=True,
    )


def _polite(client: httpx.Client, method: str, url: str, **kw) -> httpx.Response:
    delay = REQUEST_DELAY
    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            time.sleep(delay)
            r = client.request(method, url, **kw)
            r.raise_for_status()
            return r
        except httpx.HTTPError as e:
            last_error = e
            logger.warning("[retry %d/%d] %s %s -> %s", attempt, MAX_RETRIES, method, url, e)
            delay *= 2
    raise RuntimeError(f"請求失敗：{method} {url}") from last_error


def _bootstrap(client: httpx.Client) -> str:
    """GET 查詢頁，取得 session cookie 與 XSRF-TOKEN（作為 _csrf）。"""
    _polite(client, "GET", SEARCH_PAGE)
    csrf = client.cookies.get("XSRF-TOKEN") or ""
    if not csrf:
        logger.warning("未取得 XSRF-TOKEN cookie；_csrf 將留空")
    return csrf


def _list_payload(csrf: str, page: int) -> list[tuple[str, str]]:
    return [
        ("_csrf", csrf), ("pkPrmsRuleType", ""),
        ("article", ""), ("article2", ""), ("paragraph", ""), ("item", ""),
        ("keyword1", ""), ("links", "and"), ("keyword2", ""),
        ("explainNumberNo", ""),
        ("date", ""), ("date", ""), ("date", ""), ("date", ""),
        ("sorts", "createDate"), ("pageSize", str(PAGE_SIZE)),
        ("startDate", ""), ("endDate", ""), ("startNetDate", ""), ("endNetDate", ""),
        ("paginationPage", str(page)),
    ]


def _harvest_pks(html: str) -> list[str]:
    seen, out = set(), []
    for pat in PK_PATTERNS:
        for m in pat.findall(html):
            if m not in seen:
                seen.add(m)
                out.append(m)
    return out


# ──────────── 解析 ────────────
def _parse_detail(html: str, pk: str = "") -> dict:
    soup = BeautifulSoup(html, "html.parser")
    box = soup.select_one("#printExplain") or soup
    text = box.get_text("\n", strip=True).replace(" ", " ")

    def grab(pat, s=text, flags=0):
        m = re.search(pat, s, flags)
        return m.group(1).strip() if m else ""

    issue_roc = ""
    m = re.search(r"發文日期[:：]\s*中華民國\s*(\d+)\s*年\s*(\d+)\s*月\s*(\d+)\s*日", text)
    if m:
        issue_roc = f"{int(m.group(1))}.{int(m.group(2)):02d}.{int(m.group(3)):02d}"

    letter_no = grab(r"發文字號[:：]\s*(\S+?號)")
    based_on = grab(r"根據\s*([^\n]+)")
    issuer = grab(r"本解釋函上網公告者[:：]\s*([^\n]+)")

    law_name, articles = "", []
    if based_on:
        mm = re.search(r"第\s*\d", based_on)
        law_name = based_on[: mm.start()].strip() if mm else based_on
        law_name = re.sub(r"其[他它]$", "", law_name).strip()
        if law_name.startswith("政府採購法"):
            law_name = "政府採購法"
        articles = sorted(
            set(
                a.replace("之", "-")
                for a in re.findall(r"第\s*(\d+(?:[-之]\d+)?)\s*條", based_on)
            )
        )

    subject = grab(r"主旨[:：]\s*(.+?)(?:說明[:：]|$)", text, re.S).replace("\n", "")
    fm = re.search(r"(主旨[:：].+)", text, re.S)
    full_text = fm.group(1).strip() if fm else text
    if not subject:  # 法規發布令等無「主旨」者，取內容首行當主旨
        for line in text.split("\n"):
            ln = line.strip()
            if (
                ln
                and len(ln) > 6
                and not re.match(r"(發文|根據|本解釋函|附件)", ln)
                and not re.search(r"\.(pdf|odt|docx?|xlsx?|zip)$", ln)
            ):
                subject = ln[:120]
                break
    body_arts = set(
        a.replace("之", "-")
        for a in re.findall(r"(?:採購法|本法)第\s*(\d+(?:[-之]\d+)?)\s*條", full_text)
    )
    articles = sorted(set(articles) | body_arts)

    if not pk:
        pk = grab(r"pkPrmsRuleContent=(\d+)", html)

    status, note = "active", None
    if any(k in text for k in ["停止適用", "不再援用", "業經廢止", "自即日起停止"]):
        status, note = "superseded", "內文含停用字樣，請人工複核"

    return dict(
        letter_id=pk, letter_no=letter_no, law_name=law_name, based_on=based_on,
        articles=articles, subject=subject, full_text=full_text, issuer=issuer,
        issue_date_roc=issue_roc, status=status, status_note=note,
    )


def _roc_to_iso(roc: str) -> str | None:
    m = re.match(r"(\d+)[.\-/](\d+)[.\-/](\d+)", roc or "")
    if not m:
        return None
    return f"{int(m.group(1)) + 1911:04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"


def _save_letter(conn: sqlite3.Connection, rec: dict, source_url: str) -> None:
    lid = rec["letter_id"]
    conn.execute(
        """INSERT INTO pcc_letters
           (letter_id,letter_no,law_name,based_on,subject,full_text,issuer,
            issue_date,issue_date_roc,status,superseded_by,status_note,source_url,fetched_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(letter_id) DO UPDATE SET
             letter_no=excluded.letter_no, law_name=excluded.law_name, based_on=excluded.based_on,
             subject=excluded.subject, full_text=excluded.full_text, issuer=excluded.issuer,
             issue_date=excluded.issue_date, issue_date_roc=excluded.issue_date_roc,
             status=excluded.status, status_note=excluded.status_note, fetched_at=excluded.fetched_at""",
        (
            lid, rec["letter_no"], rec["law_name"], rec["based_on"], rec["subject"],
            rec["full_text"], rec["issuer"], _roc_to_iso(rec["issue_date_roc"]),
            rec["issue_date_roc"], rec["status"], rec.get("superseded_by"),
            rec["status_note"], source_url, datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.execute("DELETE FROM pcc_letter_articles WHERE letter_id=?", (lid,))
    for art in rec["articles"]:
        conn.execute(
            "INSERT OR IGNORE INTO pcc_letter_articles(letter_id,law_name,article_no) VALUES(?,?,?)",
            (lid, rec["law_name"], art),
        )
    conn.commit()


def _fetch_and_save(conn: sqlite3.Connection, client: httpx.Client, pk: str, csrf: str) -> bool:
    url = f"{DETAIL_GET}?pkPrmsRuleContent={pk}&_csrf={csrf}"
    r = _polite(client, "GET", url)
    rec = _parse_detail(r.text, pk=pk)
    if not rec["letter_no"] and not rec["subject"]:
        logger.warning("pk=%s 解析不到內容，略過", pk)
        return False
    _save_letter(conn, rec, url)
    logger.info("✓ %s %s [%s] %s %s", pk, rec["letter_no"], rec["status"],
                rec["law_name"], rec["articles"])
    return True


# ──────────── 主流程 ────────────
def update_pcc_letters(full: bool = False, max_items: int | None = None) -> dict:
    """增量更新函釋庫。

    Args:
        full: True 時掃完整清單（仍跳過已入庫）；False 時遇「整頁無新函釋」即停。
        max_items: 最多新增則數（None = 不限）。

    Returns:
        {"added": 新增則數, "pages": 掃過頁數}
    """
    conn = _get_db()
    added, page, empty_streak = 0, 0, 0
    try:
        with _make_client() as client:
            csrf = _bootstrap(client)
            while True:
                logger.info("清單第 %d 頁", page)
                r = _polite(
                    client, "POST", LIST_POST,
                    content=urlencode(_list_payload(csrf, page)),
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "Origin": BASE,
                        "Referer": SEARCH_PAGE,
                    },
                )
                pks = _harvest_pks(r.text)
                new = [p for p in pks if not _already_have(conn, p)]
                if not pks:
                    empty_streak += 1
                    if empty_streak >= 2:
                        logger.info("連續空頁，結束")
                        break
                else:
                    empty_streak = 0
                    if not new and not full:
                        # 清單由新到舊；整頁皆已入庫 => 後面都是舊資料
                        logger.info("第 %d 頁無新函釋，增量更新結束", page)
                        break
                for pk in new:
                    if _fetch_and_save(conn, client, pk, csrf):
                        added += 1
                    if max_items and added >= max_items:
                        logger.info("達 max_items=%d，停止", max_items)
                        _set_checkpoint(conn, "last_check",
                                        datetime.now(timezone.utc).isoformat())
                        return {"added": added, "pages": page + 1}
                page += 1
        _set_checkpoint(conn, "last_check", datetime.now(timezone.utc).isoformat())
        logger.info("函釋增量更新完成：新增 %d 則（掃 %d 頁）", added, page + 1)
        return {"added": added, "pages": page + 1}
    finally:
        conn.close()


def maybe_update() -> None:
    """供 server.py 啟動背景工作呼叫：到期才更新，失敗只記警告。"""
    should, reason = should_update()
    if not should:
        logger.info("pcc_letters.db %s，略過", reason)
        return
    logger.info("pcc_letters.db %s，觸發增量更新", reason)
    result = update_pcc_letters(full=False)
    logger.info("pcc_letters.db 更新完成：新增 %d 則", result["added"])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="全量補抓（仍跳過已入庫）")
    ap.add_argument("--max", type=int, default=None, help="最多新增則數")
    args = ap.parse_args()
    result = update_pcc_letters(full=args.full, max_items=args.max)
    print(f"完成：新增 {result['added']} 則（掃 {result['pages']} 頁）")
