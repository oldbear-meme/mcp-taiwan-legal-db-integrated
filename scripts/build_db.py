#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 Console 抓下來的 pcc_letters.json（或 pcc_test.json）建成 pcc_letters.db。
用法：python build_db.py pcc_letters.json
此檔需要 Python；若機器沒有 Python，可把 json 交給 AI 助手（如 Claude）代為建庫。"""
import json, sys, importlib.util
from pathlib import Path

here = Path(__file__).parent
spec = importlib.util.spec_from_file_location("crawler", here / "crawler.py")
cr = importlib.util.module_from_spec(spec); spec.loader.exec_module(cr)

def main(src):
    cr.DB_PATH = str(here / "pcc_letters.db")
    if Path(cr.DB_PATH).exists():
        Path(cr.DB_PATH).unlink()
    cr.init_db()
    conn = cr.get_db()
    data = json.load(open(src, encoding="utf-8"))
    ok = 0
    for row in data:
        if not row.get("html"):
            continue
        rec = cr.parse_detail(row["html"], pk=row["pk"])
        cr.save_letter(conn, rec,
            f"https://planpe.pcc.gov.tw/prms/explainLetter/readPrmsExplainLetterContentDetail?pkPrmsRuleContent={row['pk']}")
        ok += 1
    n = conn.execute("SELECT COUNT(*) FROM pcc_letters").fetchone()[0]
    a = conn.execute("SELECT COUNT(*) FROM pcc_letter_articles").fetchone()[0]
    print(f"完成：解析 {ok} 則，入庫 {n} 則，條號索引 {a} 筆 → {cr.DB_PATH}")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "pcc_letters.json")
