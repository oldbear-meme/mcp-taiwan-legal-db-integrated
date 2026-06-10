#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工程會函釋全量爬蟲 v2（依 planpe 實際請求結構，本機執行）
============================================================
流程（已依您提供的 request.txt / 明細頁.html 對準）：
  1. GET  /prms/explainLetter/readPrmsExplainLetterSearch  → 取得 session 與 XSRF-TOKEN
  2. POST /prms/explainLetter/readPrmsExplainLetter         → 依 paginationPage 逐頁取清單
                                                              （帶 _csrf、pageSize=100）
  3. 從每頁清單 harvest 所有 pkPrmsRuleContent
  4. GET  /prms/explainLetter/printPrmsExplainLetterContentDetail?pkPrmsRuleContent=<pk>
                                                              → 抓單則全文並解析入庫
  5. 斷點續抓：以「已抓 pk 集合」判斷，重跑自動跳過。

用法：
  python crawler.py probe          # 端到端探測：抓第1頁、存 list_response.html、印出 harvest 到的 pk 與一則解析結果（不大量入庫）
  python crawler.py crawl          # 全量抓取（可 Ctrl-C，下次接續）
  python crawler.py crawl --max 30 # 只抓 30 則（測試）

注意：請維持禮貌頻率（REQUEST_DELAY 勿調低）；函釋屬公開法令資訊，供機關內部審查為正當使用。
"""

import argparse
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ──────────── CONFIG ────────────
BASE = "https://planpe.pcc.gov.tw"
SEARCH_PAGE = BASE + "/prms/explainLetter/readPrmsExplainLetterSearch"
LIST_POST   = BASE + "/prms/explainLetter/readPrmsExplainLetter"
DETAIL_GET  = BASE + "/prms/explainLetter/readPrmsExplainLetterContentDetail"  # GET ?pkPrmsRuleContent=&_csrf=

REQUEST_DELAY = 1.5      # 秒，禮貌間隔（勿調低）
TIMEOUT = 30
MAX_RETRIES = 3
PAGE_SIZE = 100
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36")

DB_PATH = str(Path(__file__).with_name("pcc_letters.db"))
SCHEMA_PATH = str(Path(__file__).with_name("schema.sql"))

# 抓 pk：清單頁的「檢視」會夾帶 pkPrmsRuleContent；用多重樣式 harvest
PK_PATTERNS = [
    re.compile(r"readExplainLetter\((\d+)\)"),                 # 清單頁「檢視」按鈕（已驗證）
    re.compile(r"pkPrmsRuleContent['\"=:\s,()]*?(\d{5,})"),    # 後備
]


# ──────────── DB ────────────
def get_db():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    if not Path(DB_PATH).exists():
        get_db().executescript(Path(SCHEMA_PATH).read_text(encoding="utf-8"))
        print(f"[init] 建庫完成 → {DB_PATH}")
    else:
        # 確保表存在（不覆蓋資料）
        get_db().executescript(Path(SCHEMA_PATH).read_text(encoding="utf-8"))


def already_have(conn, pk):
    return conn.execute("SELECT 1 FROM pcc_letters WHERE letter_id=?", (pk,)).fetchone() is not None


# ──────────── HTTP ────────────
def make_session():
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "zh-TW,zh;q=0.9"})
    return s


def polite(session, method, url, **kw):
    delay = REQUEST_DELAY
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            time.sleep(delay)
            r = session.request(method, url, timeout=TIMEOUT, **kw)
            r.raise_for_status()
            r.encoding = "UTF-8"
            return r
        except requests.RequestException as e:
            print(f"  [retry {attempt}/{MAX_RETRIES}] {method} {url} -> {e}")
            delay *= 2
    raise RuntimeError(f"請求失敗：{method} {url}")


def bootstrap(session):
    """GET 查詢頁，取得 session cookie 與 XSRF-TOKEN（作為 _csrf）。"""
    polite(session, "GET", SEARCH_PAGE)
    csrf = session.cookies.get("XSRF-TOKEN") or session.cookies.get("XSRF-TOKEN", domain="planpe.pcc.gov.tw")
    if not csrf:
        print("  [warn] 未取得 XSRF-TOKEN cookie；_csrf 將留空，若 POST 失敗請回報。")
    return csrf or ""


def list_payload(csrf, page, keyword=""):
    """完全比照實際 request 的 form data（含 4 個重複的 date= 與各日期欄）。"""
    return [
        ("_csrf", csrf), ("pkPrmsRuleType", ""),
        ("article", ""), ("article2", ""), ("paragraph", ""), ("item", ""),
        ("keyword1", keyword), ("links", "and"), ("keyword2", ""),
        ("explainNumberNo", ""),
        ("date", ""), ("date", ""), ("date", ""), ("date", ""),
        ("sorts", "createDate"), ("pageSize", str(PAGE_SIZE)),
        ("startDate", ""), ("endDate", ""), ("startNetDate", ""), ("endNetDate", ""),
        ("paginationPage", str(page)),
    ]


def harvest_pks(html):
    seen, out = set(), []
    for pat in PK_PATTERNS:
        for m in pat.findall(html):
            if m not in seen:
                seen.add(m); out.append(m)
    return out


# ──────────── 解析（已用真實明細頁驗證）────────────
def parse_detail(html, pk=""):
    soup = BeautifulSoup(html, "html.parser")
    box = soup.select_one("#printExplain") or soup
    text = box.get_text("\n", strip=True).replace("\u00a0", " ")

    def grab(pat, s=text, flags=0):
        m = re.search(pat, s, flags)
        return m.group(1).strip() if m else ""

    issue_roc = ""
    m = re.search(r"發文日期[:：]\s*中華民國\s*(\d+)\s*年\s*(\d+)\s*月\s*(\d+)\s*日", text)
    if m:
        issue_roc = f"{int(m.group(1))}.{int(m.group(2)):02d}.{int(m.group(3)):02d}"

    letter_no = grab(r"發文字號[:：]\s*(\S+?號)")
    based_on  = grab(r"根據\s*([^\n]+)")
    issuer    = grab(r"本解釋函上網公告者[:：]\s*([^\n]+)")

    law_name, articles = "", []
    if based_on:
        mm = re.search(r"第\s*\d", based_on)
        law_name = based_on[:mm.start()].strip() if mm else based_on
        law_name = re.sub(r"其[他它]$", "", law_name).strip()
        if law_name.startswith("政府採購法"):
            law_name = "政府採購法"   # 綜合/其他/綜合：綜合 等歸併
        articles = sorted(set(a.replace("之", "-")
                              for a in re.findall(r"第\s*(\d+(?:[-之]\d+)?)\s*條", based_on)))

    subject = grab(r"主旨[:：]\s*(.+?)(?:說明[:：]|$)", text, re.S).replace("\n", "")
    fm = re.search(r"(主旨[:：].+)", text, re.S)
    full_text = fm.group(1).strip() if fm else text
    if not subject:  # 法規發布令等無「主旨」者，取內容首行當主旨
        for line in text.split("\n"):
            ln = line.strip()
            if (ln and len(ln) > 6
                    and not re.match(r"(發文|根據|本解釋函|附件)", ln)
                    and not re.search(r"\.(pdf|odt|docx?|xlsx?|zip)$", ln)):
                subject = ln[:120]; break
    # 內文若引用「採購法第N條／本法第N條」，一併納入條號索引（便於以採購法條號查得）
    body_arts = set(a.replace("之", "-")
                    for a in re.findall(r"(?:採購法|本法)第\s*(\d+(?:[-之]\d+)?)\s*條", full_text))
    articles = sorted(set(articles) | body_arts)

    if not pk:
        pk = grab(r"pkPrmsRuleContent=(\d+)", html)

    status, note = "active", None
    if any(k in text for k in ["停止適用", "不再援用", "業經廢止", "自即日起停止"]):
        status, note = "superseded", "內文含停用字樣，請人工複核"

    return dict(letter_id=pk, letter_no=letter_no, law_name=law_name, based_on=based_on,
                articles=articles, subject=subject, full_text=full_text, issuer=issuer,
                issue_date_roc=issue_roc, status=status, status_note=note)


def roc_to_iso(roc):
    m = re.match(r"(\d+)[.\-/](\d+)[.\-/](\d+)", roc or "")
    if not m:
        return None
    return f"{int(m.group(1))+1911:04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"


def save_letter(conn, rec, source_url):
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
        (lid, rec["letter_no"], rec["law_name"], rec["based_on"], rec["subject"], rec["full_text"],
         rec["issuer"], roc_to_iso(rec["issue_date_roc"]), rec["issue_date_roc"],
         rec["status"], rec.get("superseded_by"), rec["status_note"], source_url,
         datetime.now(timezone.utc).isoformat()),
    )
    conn.execute("DELETE FROM pcc_letter_articles WHERE letter_id=?", (lid,))
    for art in rec["articles"]:
        conn.execute("INSERT OR IGNORE INTO pcc_letter_articles(letter_id,law_name,article_no) VALUES(?,?,?)",
                     (lid, rec["law_name"], art))
    conn.commit()


# ──────────── 流程 ────────────
def fetch_and_save(conn, session, pk, csrf=""):
    url = f"{DETAIL_GET}?pkPrmsRuleContent={pk}&_csrf={csrf}"
    r = polite(session, "GET", url)
    rec = parse_detail(r.text, pk=pk)
    if not rec["letter_no"] and not rec["subject"]:
        print(f"   ! pk={pk} 解析不到內容（detail 端點或格式異常），略過")
        return False
    save_letter(conn, rec, url)
    print(f"   ✓ {pk}  {rec['letter_no']}  [{rec['status']}]  {rec['law_name']} {rec['articles']}")
    return True


def probe():
    s = make_session()
    csrf = bootstrap(s)
    print(f"[probe] XSRF-TOKEN = {csrf or '(空)'}")
    r = polite(s, "POST", LIST_POST,
               data=list_payload(csrf, 0, keyword=""),
               headers={"Content-Type": "application/x-www-form-urlencoded",
                        "Origin": BASE, "Referer": SEARCH_PAGE})
    Path(DB_PATH).with_name("list_response.html").write_text(r.text, encoding="utf-8")
    pks = harvest_pks(r.text)
    print(f"[probe] 第1頁 harvest 到 {len(pks)} 個 pk；前幾個：{pks[:8]}")
    print("[probe] 清單原始 HTML 已存 list_response.html")
    if pks:
        init_db()
        conn = get_db()
        print("[probe] 試抓第一則明細並解析：")
        fetch_and_save(conn, s, pks[0], csrf)
    else:
        print("[probe] ⚠ 沒 harvest 到 pk —— 請把 list_response.html 回貼給我，我據實修 harvest 規則。")


def crawl(max_items=None):
    init_db()
    conn = get_db()
    s = make_session()
    csrf = bootstrap(s)
    page, count, empty_streak = 0, 0, 0
    while True:
        print(f"[crawl] 清單第 {page} 頁（paginationPage={page}）")
        r = polite(s, "POST", LIST_POST,
                   data=list_payload(csrf, page, keyword=""),
                   headers={"Content-Type": "application/x-www-form-urlencoded",
                            "Origin": BASE, "Referer": SEARCH_PAGE})
        pks = harvest_pks(r.text)
        new = [p for p in pks if not already_have(conn, p)]
        if not pks:
            empty_streak += 1
            if empty_streak >= 2:
                print("[crawl] 連續空頁，視為結束。")
                break
        else:
            empty_streak = 0
        for pk in new:
            if fetch_and_save(conn, s, pk, csrf):
                count += 1
            if max_items and count >= max_items:
                print(f"[crawl] 達 --max {max_items}，停止（已入庫 {count} 則）。")
                return
        page += 1
    print(f"[crawl] 完成，本次新入庫 {count} 則。")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["probe", "init", "crawl"])
    ap.add_argument("--max", type=int, default=None)
    a = ap.parse_args()
    if a.cmd == "init":
        init_db()
    elif a.cmd == "probe":
        probe()
    else:
        crawl(max_items=a.max)


if __name__ == "__main__":
    main()
