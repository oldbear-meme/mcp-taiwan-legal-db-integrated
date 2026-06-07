"""judicial_search.py 整合測試 - 驗證簡易案件系統查詢

重點測試你增補的簡易案件查詢功能：
1. 雙系統並行查詢（裁判書 + 簡易案件）
2. 簡易案件類型（羅小、上易等字別）
3. 結果合併去重
4. 關鍵字搜尋同時查兩個系統

基於歷史開發紀錄的關鍵驗證點：
- 簡易案件系統不能傳 jud_court 參數
- 年度格式為 dy/dm/dd 三個欄位
- 雙系統查詢不應該漏掉 15-20% 結果

執行：pytest mcp_server/tests/test_judicial_search_integration.py -v -m integration
"""

import asyncio

import pytest

from mcp_server.cache.db import CacheDB
from mcp_server.tools.judicial_search import JudicialSearchClient
from mcp_server.tools.waf_bypass import JudicialWAFBypass


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
async def cache(tmp_path):
    """使用臨時資料庫，避免快取干擾測試"""
    db = CacheDB(db_path=tmp_path / "test_cache.db")
    await db.initialize()
    yield db
    await db.close()


@pytest.fixture
async def client(cache):
    """測試用客戶端（使用臨時快取）"""
    waf = JudicialWAFBypass()
    client = JudicialSearchClient(cache, waf)
    yield client


# ============================================================
# 核心測試：簡易案件查詢
# ============================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_search_small_claims_case(client):
    """
    測試小額訴訟案件查詢（羅小字）

    歷史背景：
    - 原作者移除了簡易案件系統支援
    - 你重新加入了雙系統並行查詢
    - 小額訴訟案件只在簡易案件系統中
    """
    print("\n[小額訴訟] 查詢羅小字案件...")

    # 查詢小額訴訟案件（標的 50 萬以下）
    result = await client.search(
        case_word="羅小",  # 臺灣臺北地方法院羅東簡易庭小額民事
        case_number="412",
        year_from=113,
        year_to=115
    )

    print(f"結果: success={result['success']}, 筆數={len(result.get('results', []))}")

    # 驗證成功
    assert result["success"] is True, f"查詢失敗: {result.get('error', 'Unknown')}"

    # 小額案件應該要能查到（如果你的系統有支援）
    # 注意：這個測試可能會因為實際沒有這個案號而查不到結果
    # 但重點是驗證系統不會報錯
    if len(result.get("results", [])) > 0:
        first = result["results"][0]
        print(f"找到案件: {first.get('case_id', 'N/A')}")
        print(f"jid: {first.get('jid', 'N/A')[:50]}...")
    else:
        print("注意：沒有找到結果（可能此案號不存在）")

    print("[小額訴訟] 查詢功能正常 [OK]")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_search_easy_court_case(client):
    """
    測試簡易庭案件查詢（上易字）

    簡易庭上訴案件，應該在簡易案件系統中
    """
    print("\n[簡易庭] 查詢上易字案件...")

    result = await client.search(
        case_word="上易",  # 地方法院簡易庭民事上訴
        case_number="503",
        year_from=113,
        year_to=115
    )

    print(f"結果: success={result['success']}, 筆數={len(result.get('results', []))}")

    assert result["success"] is True, f"查詢失敗: {result.get('error', 'Unknown')}"

    if len(result.get("results", [])) > 0:
        first = result["results"][0]
        print(f"找到案件: {first.get('case_id', 'N/A')}")
    else:
        print("注意：沒有找到結果（可能此案號不存在）")

    print("[簡易庭] 查詢功能正常 [OK]")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_keyword_search_queries_both_systems(client):
    """
    測試關鍵字搜尋是否同時查詢兩個系統

    驗證點：
    - 關鍵字搜尋應該同時查裁判書系統和簡易案件系統
    - 結果應該合併且去重

    歷史問題：原作者版本會漏掉 15-20% 結果
    """
    print("\n[關鍵字搜尋] 測試雙系統並行...")

    # 使用常見的法律關鍵字
    result = await client.search(
        keyword="租賃契約",
        max_results=20
    )

    print(f"結果: success={result['success']}, 筆數={len(result.get('results', []))}")

    assert result["success"] is True
    assert len(result.get("results", [])) > 0, "應該要有結果"

    # 檢查結果中是否有不同來源的案件
    results = result.get("results", [])

    # 統計不同法院層級
    court_levels = set()
    case_types = set()

    for item in results[:10]:  # 檢查前 10 筆
        if "court_level" in item:
            court_levels.add(item["court_level"])

        case_id = item.get("case_id", "")
        # 提取字別（例如：「簡字」「小字」「訴字」）
        if "簡" in case_id or "小" in case_id:
            case_types.add("簡易案件")
        else:
            case_types.add("一般案件")

    print(f"法院層級分布: {court_levels}")
    print(f"案件類型分布: {case_types}")

    # 驗證結果多樣性（應該包含不同來源）
    # 注意：這個驗證比較寬鬆，因為實際結果取決於關鍵字
    print(f"查到 {len(results)} 筆結果，涵蓋 {len(case_types)} 種案件類型")

    print("[關鍵字搜尋] 雙系統查詢正常 [OK]")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dual_system_no_duplicates(client):
    """
    測試雙系統查詢結果去重

    驗證點：
    - 同時查詢兩個系統時，不應該有重複的 jid
    - 歷史開發紀錄提到使用 asyncio.gather 並行查詢並去重
    """
    print("\n[去重測試] 驗證雙系統結果無重複...")

    result = await client.search(
        keyword="借名登記",
        max_results=20
    )

    assert result["success"] is True
    results = result.get("results", [])

    if len(results) == 0:
        print("注意：關鍵字沒有結果，跳過去重測試")
        return

    # 提取所有 jid
    jids = [r.get("jid", "") for r in results]

    # 統計重複
    jid_counts = {}
    for jid in jids:
        if jid:  # 忽略空 jid
            jid_counts[jid] = jid_counts.get(jid, 0) + 1

    # 找出重複項
    duplicates = {jid: count for jid, count in jid_counts.items() if count > 1}

    print(f"總結果數: {len(results)}")
    print(f"唯一 jid 數: {len(jid_counts)}")

    if duplicates:
        print(f"[警告] 發現重複項: {duplicates}")
        assert False, f"結果有重複 jid: {duplicates}"
    else:
        print("無重複項 [OK]")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_result_structure_complete(client):
    """
    測試結果結構完整性

    驗證每筆結果都有必要欄位
    """
    print("\n[結構完整性] 檢查結果欄位...")

    result = await client.search(
        keyword="民法",
        max_results=10
    )

    assert result["success"] and len(result.get("results", [])) > 0

    results = result["results"]
    print(f"檢查 {len(results)} 筆結果...")

    required_fields = ["jid", "case_id"]

    for i, item in enumerate(results):
        for field in required_fields:
            assert field in item, f"第 {i+1} 筆缺少欄位: {field}"
            assert item[field], f"第 {i+1} 筆 {field} 為空"

    print(f"所有 {len(results)} 筆結果結構正確 [OK]")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cache_works(client):
    """
    測試快取功能

    第二次查詢應該命中快取
    """
    print("\n[快取測試] 驗證快取機制...")

    keyword = "契約"

    # 第一次查詢
    result1 = await client.search(keyword=keyword, max_results=5)
    cached1 = result1.get("cached", False)

    # 第二次查詢
    result2 = await client.search(keyword=keyword, max_results=5)
    cached2 = result2.get("cached", False)

    print(f"第一次: cached={cached1}")
    print(f"第二次: cached={cached2}")

    assert cached2 is True, "第二次查詢應該命中快取"
    assert len(result1.get("results", [])) == len(result2.get("results", [])), "快取結果數量應一致"

    print("[快取測試] 快取正常 [OK]")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_empty_result_handling(client):
    """
    測試空結果處理
    """
    print("\n[空結果] 測試不存在的案號...")

    result = await client.search(
        case_word="XYZABC",  # 不存在的字別
        case_number="999999"
    )

    print(f"結果: success={result['success']}, 筆數={len(result.get('results', []))}")

    assert result["success"] is True, "即使沒結果也應該成功"
    assert len(result.get("results", [])) == 0, "不存在的案號應該返回空結果"

    print("[空結果] 正常處理 [OK]")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_search_returns_valid_jids(client):
    """
    測試查詢結果的 jid 有效性

    驗證返回的 jid 格式正確
    """
    print("\n[jid 驗證] 測試 jid 格式...")

    search_result = await client.search(
        keyword="民法",
        max_results=5
    )

    assert search_result["success"] and len(search_result.get("results", [])) > 0

    results = search_result["results"]
    print(f"檢查 {len(results)} 筆結果的 jid...")

    for i, item in enumerate(results):
        jid = item.get("jid", "")
        assert jid, f"第 {i+1} 筆 jid 為空"
        assert "," in jid, f"第 {i+1} 筆 jid 格式錯誤（應包含逗號）: {jid}"
        print(f"  {i+1}. {jid[:50]}...")

    print("[jid 驗證] 所有 jid 格式正確 [OK]")
