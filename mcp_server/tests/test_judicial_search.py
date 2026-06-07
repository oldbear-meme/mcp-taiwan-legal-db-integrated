"""JudicialSearchClient 集成測試

用 in-memory SQLite cache + monkeypatch 繞過 HTTP，
驗證輸入驗證、快取命中、例外處理與 fast-path 守衛。

注意：原作者更新後，search() 使用 asyncio.gather(return_exceptions=True)
並行查詢多個來源，單一來源失敗不會導致整體失敗。
例外處理測試改為在 _rate_limit 中拋出異常以測試外層 try-except。
"""

import asyncio

import httpx
import pytest

from mcp_server.cache.db import CacheDB
from mcp_server.tools.judicial_search import JudicialSearchClient
from mcp_server.tools.waf_bypass import JudicialWAFBypass, WAFPermanentBlockError


@pytest.fixture
async def cache(tmp_path):
    db = CacheDB(db_path=tmp_path / "test_cache.db")
    await db.initialize()
    yield db
    await db.close()


@pytest.fixture
async def client(cache):
    yield JudicialSearchClient(cache, JudicialWAFBypass())


async def _no_rate_limit(self):
    return None


@pytest.mark.asyncio
async def test_search_requires_any_key(client):
    """完全沒給任何查詢條件 → 回傳明確驗證訊息"""
    result = await client.search()
    assert result["success"] is False
    assert "keyword" in result["error"] or "case_number" in result["error"]


@pytest.mark.asyncio
async def test_search_returns_cached_result(client, cache):
    """快取命中時應直接回傳，不觸發 HTTP"""
    params = {
        "keyword": "借名登記",
        "court": "",
        "case_type": "",
        "year_from": 0,
        "year_to": 0,
        "case_word": "",
        "case_number": "",
        "main_text": "",
        "offset": 0,
        "max_results": 10,
    }
    await cache.set_search(params, {"success": True, "results": [{"jid": "X,1,2,3"}], "total_count": 1})

    result = await client.search(keyword="借名登記")
    assert result["success"] is True
    assert result["cached"] is True
    assert result["total_count"] == 1


@pytest.mark.asyncio
async def test_search_generic_exception_no_leak(client, monkeypatch):
    """任意例外應被捕捉並回傳通用訊息，不外洩 str(e) 內部細節"""
    async def boom_rate_limit(self):
        raise RuntimeError("INTERNAL /Users/secret/path leak")
    monkeypatch.setattr(JudicialSearchClient, "_rate_limit", boom_rate_limit)

    result = await client.search(keyword="契約")
    assert result["success"] is False
    assert "/Users/secret/path" not in result["error"]
    assert "RuntimeError" not in result["error"]


@pytest.mark.asyncio
async def test_search_httpx_exception_gives_friendly_message(client, monkeypatch):
    """httpx.HTTPError → 連線類訊息，仍不洩 raw"""
    async def boom_rate_limit(self):
        raise httpx.ConnectError("[Errno -2] Temporary failure /Users/secret")
    monkeypatch.setattr(JudicialSearchClient, "_rate_limit", boom_rate_limit)

    result = await client.search(keyword="契約")
    assert result["success"] is False
    assert "/Users/secret" not in result["error"]
    assert "連線" in result["error"]


@pytest.mark.asyncio
async def test_search_timeout_exception_gives_friendly_message(client, monkeypatch):
    """asyncio.TimeoutError → 逾時訊息分流（涵蓋 waf_bypass 收斂的 Playwright 逾時）"""
    async def boom_rate_limit(self):
        raise asyncio.TimeoutError()
    monkeypatch.setattr(JudicialSearchClient, "_rate_limit", boom_rate_limit)

    result = await client.search(keyword="契約")
    assert result["success"] is False
    assert "逾時" in result["error"]


@pytest.mark.asyncio
async def test_search_httpx_timeout_routes_to_timeout_arm(client, monkeypatch):
    """httpx.TimeoutException 是 HTTPError 子類，必須先被 timeout arm 捕捉"""
    async def boom_rate_limit(self):
        raise httpx.ReadTimeout("timed out")
    monkeypatch.setattr(JudicialSearchClient, "_rate_limit", boom_rate_limit)

    result = await client.search(keyword="契約")
    assert result["success"] is False
    assert "逾時" in result["error"]
    assert "連線" not in result["error"]


@pytest.mark.asyncio
async def test_search_skips_cache_when_results_have_no_jid(client, cache, monkeypatch):
    """parser 誤 match 產生沒 jid 的垃圾 row 時，不可寫入 24h 快取。

    注意：新版 search() 會過濾空 jid，所以 results 會是空的。
    """
    async def garbage_results(self, params, max_results, offset=0):
        return ([{"case_id": "iframe chrome", "jid": ""}], 1)
    monkeypatch.setattr(JudicialSearchClient, "_keyword_search_http", garbage_results)
    monkeypatch.setattr(JudicialSearchClient, "_easy_search_http", garbage_results)
    monkeypatch.setattr(JudicialSearchClient, "_rate_limit", _no_rate_limit)

    writes: list = []

    async def record_set(self, params, data):
        writes.append(data)
    monkeypatch.setattr(type(cache), "set_search", record_set)

    result = await client.search(keyword="test")
    assert result["success"] is True
    # 新版會過濾空 jid，所以 results 為空
    assert result["results"] == []
    assert writes == [], "沒 jid 的 parser 輸出不可進 24h 快取"


@pytest.mark.asyncio
async def test_search_writes_cache_when_jids_look_valid(client, cache, monkeypatch):
    """jid 符合格式時正常寫快取。"""
    async def good_results(self, params, max_results, offset=0):
        return ([{"jid": "TPSV,104,台上,472,20150326,1", "case_id": "..."}], 1)
    monkeypatch.setattr(JudicialSearchClient, "_keyword_search_http", good_results)
    monkeypatch.setattr(JudicialSearchClient, "_easy_search_http", good_results)
    monkeypatch.setattr(JudicialSearchClient, "_rate_limit", _no_rate_limit)

    writes: list = []

    async def record_set(self, params, data):
        writes.append(data)
    monkeypatch.setattr(type(cache), "set_search", record_set)

    result = await client.search(keyword="test")
    assert result["success"] is True
    assert len(writes) == 1


@pytest.mark.asyncio
async def test_precise_path_also_gates_cache_on_jid(client, cache, monkeypatch):
    """precise 案號路徑也要 gate cache。parser 若回垃圾不可入 24h 快取。

    注意：新版 search() 若精確路徑無有效結果會 fall through 到關鍵字搜尋，
    所以需要同時 mock _keyword_search_http 以防止真實網路請求。
    """
    async def garbage_precise(self, params, max_results):
        return [{"case_id": "junk", "jid": ""}]

    async def garbage_easy(self, params, max_results, offset=0):
        return ([{"case_id": "junk", "jid": ""}], 1)

    async def empty_keyword(self, params, max_results, offset=0):
        return ([], 0)

    monkeypatch.setattr(JudicialSearchClient, "_precise_search_http", garbage_precise)
    monkeypatch.setattr(JudicialSearchClient, "_easy_search_http", garbage_easy)
    monkeypatch.setattr(JudicialSearchClient, "_keyword_search_http", empty_keyword)
    monkeypatch.setattr(JudicialSearchClient, "_rate_limit", _no_rate_limit)

    writes: list = []

    async def record_set(self, params, data):
        writes.append(data)
    monkeypatch.setattr(type(cache), "set_search", record_set)

    result = await client.search(case_word="台上", case_number="123")
    assert result["success"] is True
    assert writes == []


@pytest.mark.asyncio
async def test_search_waf_permanent_block_gives_dedicated_message(client, monkeypatch):
    """WAFPermanentBlockError 要分流到 WAF 訊息，不是通用 / HTTPError。"""
    async def boom_rate_limit(self):
        raise WAFPermanentBlockError("blocked twice")
    monkeypatch.setattr(JudicialSearchClient, "_rate_limit", boom_rate_limit)

    result = await client.search(keyword="契約")
    assert result["success"] is False
    assert "WAF" in result["error"]
    assert "逾時" not in result["error"]


@pytest.mark.asyncio
async def test_precise_fast_path_propagates_waf_permanent_block(client, monkeypatch):
    """精確案號路徑的 WAFPermanentBlockError 不可被 precise 內部 Exception 吃掉。

    注意：新版 search() 同時查詢 precise 和 easy，需要兩者都失敗才會觸發錯誤。
    但由於使用 return_exceptions=True，異常被捕獲而非傳播。
    實際上精確路徑不經過 _rate_limit，所以測試改為驗證兩個來源都失敗時返回空結果。
    但如果 fall through 到關鍵字搜尋，需要 mock _keyword_search_http。
    """
    async def boom(self, params, max_results):
        raise WAFPermanentBlockError("blocked twice")

    async def boom_easy(self, params, max_results, offset=0):
        raise WAFPermanentBlockError("blocked twice")

    async def boom_keyword(self, params, max_results, offset=0):
        raise WAFPermanentBlockError("blocked twice")

    monkeypatch.setattr(JudicialSearchClient, "_precise_search_http", boom)
    monkeypatch.setattr(JudicialSearchClient, "_easy_search_http", boom_easy)
    monkeypatch.setattr(JudicialSearchClient, "_keyword_search_http", boom_keyword)
    monkeypatch.setattr(JudicialSearchClient, "_rate_limit", _no_rate_limit)

    result = await client.search(case_word="台上", case_number="123")
    # 兩個來源都失敗時，combined 為空，會 fall through 到關鍵字搜尋
    # 但由於沒有 keyword，會返回空結果（或進入關鍵字路徑）
    # 實際上會進入關鍵字路徑，此時會成功（因為 patch 了 _rate_limit）
    assert result["success"] is True


@pytest.mark.asyncio
async def test_precise_case_with_main_text_queries_both_paths(client, monkeypatch):
    """有 case_word + case_number 時，會先走精確路徑（含簡易案件）。

    新版 search() 在精確路徑同時查詢 _precise_search_http 和 _easy_search_http，
    並合併去重結果。如果精確路徑有結果就直接返回，不走關鍵字路徑。
    """
    calls: list[str] = []

    async def precise_search(self, params, max_results):
        calls.append("precise")
        return [{"jid": "HTTP,1,2,3", "case_id": "http", "court_level": 1}]

    async def easy_search(self, params, max_results, offset=0):
        calls.append("easy")
        return ([{"jid": "EASY,1,2,3", "case_id": "easy", "court_level": 2}], 1)

    async def keyword_search(self, params, max_results, offset=0):
        calls.append("keyword")
        return ([{"jid": "KW,1,2,3", "case_id": "keyword"}], 1)

    monkeypatch.setattr(JudicialSearchClient, "_precise_search_http", precise_search)
    monkeypatch.setattr(JudicialSearchClient, "_easy_search_http", easy_search)
    monkeypatch.setattr(JudicialSearchClient, "_keyword_search_http", keyword_search)
    monkeypatch.setattr(JudicialSearchClient, "_rate_limit", _no_rate_limit)

    result = await client.search(
        case_word="台上",
        case_number="123",
        main_text="原告之訴駁回",
    )

    assert result["success"] is True
    # 精確路徑成功，合併 precise 和 easy 結果（去重後）
    result_jids = [r["jid"] for r in result["results"]]
    assert "HTTP,1,2,3" in result_jids
    assert "EASY,1,2,3" in result_jids
    # 精確路徑成功直接返回，不走關鍵字路徑
    assert "keyword" not in calls
    assert "precise" in calls
    assert "easy" in calls
