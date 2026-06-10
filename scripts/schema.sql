-- 工程會函釋本地快取 schema（v2，依 planpe 實際結構）
-- letter_id 直接採用系統的 pkPrmsRuleContent（穩定唯一），不再用字號正規化。

CREATE TABLE IF NOT EXISTS pcc_letters (
    letter_id      TEXT PRIMARY KEY,   -- pkPrmsRuleContent（例：75005000）
    letter_no      TEXT,               -- 發文字號（例：工程企字第11500052701號）
    law_name       TEXT,               -- 法規名稱（例：機關委託技術服務廠商評選及計費辦法 / 政府採購法）
    based_on       TEXT,               -- 「根據」原文（法規+條項款）
    subject        TEXT,               -- 主旨
    full_text      TEXT,               -- 主旨＋說明＋正副本全文
    issuer         TEXT,               -- 上網公告者（例：企劃處 4科 劉）
    issue_date     TEXT,               -- 發文日期（西元 ISO，例：2026-04-29）
    issue_date_roc TEXT,               -- 發文日期（民國原文，例：115.04.29）
    status         TEXT DEFAULT 'active',  -- active / superseded(停止適用) / partial / unknown
    superseded_by  TEXT,
    status_note    TEXT,
    source_url     TEXT,
    fetched_at     TEXT
);

-- 一函釋對多條號（含法規名稱，方便連同子法一起查）
CREATE TABLE IF NOT EXISTS pcc_letter_articles (
    letter_id  TEXT NOT NULL,
    law_name   TEXT,
    article_no TEXT NOT NULL,          -- 正規化條號（例：29、22、105、22-1）
    PRIMARY KEY (letter_id, article_no),
    FOREIGN KEY (letter_id) REFERENCES pcc_letters(letter_id)
);

CREATE INDEX IF NOT EXISTS idx_pcc_status ON pcc_letters(status);
CREATE INDEX IF NOT EXISTS idx_pcc_date   ON pcc_letters(issue_date);
CREATE INDEX IF NOT EXISTS idx_pcc_law    ON pcc_letters(law_name);
CREATE INDEX IF NOT EXISTS idx_pcc_art    ON pcc_letter_articles(article_no);

CREATE TABLE IF NOT EXISTS crawl_checkpoint (key TEXT PRIMARY KEY, value TEXT);
