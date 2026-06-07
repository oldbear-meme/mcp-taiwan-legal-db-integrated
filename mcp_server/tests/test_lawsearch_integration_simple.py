"""lawsearch.py 簡化整合測試 - 驗證核心功能

專注於驗證 MCP 工具本身的功能，而不是重新實作網頁查詢流程。

測試目標：
1. 基本查詢功能正常
2. 結果結構完整
3. 分頁功能正確
4. 快取功能正常
5. 全文取得功能正常
6. 所有文件類型可查

執行：pytest mcp_server/tests/test_lawsearch_integration_simple.py -v -m integration
"""

import asyncio

import pytest

from mcp_server.cache.db import CacheDB
from mcp_server.tools.lawsearch import LawSearchClient
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
    client = LawSearchClient(cache, waf)
    yield client


# ============================================================
# 核心功能測試
# ============================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_basic_search_works(client):
    """
    測試基本查詢功能

    驗證點：
    - 查詢成功（success=True）
    - 有結果返回
    - 結果結構正確（title, url, date, summary）
    """
    result = await client.search(
        keyword="民法",
        doc_type="CD",  # 大法官解釋
        max_results=5
    )

    print(f"\n[基本查詢] keyword=民法, doc_type=CD")
    print(f"結果: success={result['success']}, 筆數={len(result['results'])}")

    # 驗證成功
    assert result["success"] is True, f"查詢失敗: {result.get('error', 'Unknown')}"

    # 驗證有結果
    assert len(result["results"]) > 0, "沒有查到任何結果"

    # 驗證第一筆結果結構
    first_result = result["results"][0]
    required_fields = ["title", "url", "date", "summary"]

    for field in required_fields:
        assert field in first_result, f"結果缺少欄位: {field}"
        print(f"  {field}: {first_result[field][:50] if first_result[field] else '(空)'}...")

    print("[基本查詢] 測試通過 [OK]")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pagination_no_overlap(client):
    """
    測試分頁功能

    驗證點：
    - 第 1 頁和第 2 頁沒有重複項目
    - offset 參數正常運作
    """
    keyword = "法律"
    doc_type = "E"  # 行政函釋（結果通常較多）

    print(f"\n[分頁測試] keyword={keyword}, doc_type={doc_type}")

    # 第 1 頁（offset=0）
    page1 = await client.search(
        keyword=keyword,
        doc_type=doc_type,
        max_results=10,
        offset=0
    )

    # 第 2 頁（offset=10）
    page2 = await client.search(
        keyword=keyword,
        doc_type=doc_type,
        max_results=10,
        offset=10
    )

    assert page1["success"] and page2["success"], "分頁查詢失敗"

    # 提取 URL 作為唯一識別
    urls_page1 = {r["url"] for r in page1["results"]}
    urls_page2 = {r["url"] for r in page2["results"]}

    print(f"第 1 頁: {len(urls_page1)} 筆")
    print(f"第 2 頁: {len(urls_page2)} 筆")

    # 驗證沒有重複
    overlap = urls_page1 & urls_page2
    assert len(overlap) == 0, f"分頁有重複項目：{overlap}"

    print("[分頁測試] 無重複 [OK]")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cache_functionality(client):
    """
    測試快取功能

    驗證點：
    - 第一次查詢：cached=False（或沒有 cached 欄位）
    - 第二次查詢：cached=True
    - 兩次結果一致
    """
    keyword = "契約"
    doc_type = "CD"

    print(f"\n[快取測試] keyword={keyword}, doc_type={doc_type}")

    # 第一次查詢
    result1 = await client.search(
        keyword=keyword,
        doc_type=doc_type,
        max_results=5
    )

    cached1 = result1.get("cached", False)
    print(f"第一次查詢: cached={cached1}, 筆數={len(result1['results'])}")

    # 第二次查詢（應該命中快取）
    result2 = await client.search(
        keyword=keyword,
        doc_type=doc_type,
        max_results=5
    )

    cached2 = result2.get("cached", False)
    print(f"第二次查詢: cached={cached2}, 筆數={len(result2['results'])}")

    # 驗證快取生效
    assert cached2 is True, "第二次查詢應該命中快取"

    # 驗證結果一致
    assert len(result1["results"]) == len(result2["results"]), "快取結果數量不一致"

    print("[快取測試] 快取正常 [OK]")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_document_full_text(client):
    """
    測試取得單筆文件全文

    驗證點：
    - 能成功取得全文
    - 全文長度 > 0
    - 包含必要欄位（title, fields, full_text, url）
    """
    print(f"\n[全文測試] 先查詢取得一筆結果...")

    # 先搜尋取得一筆結果
    search_result = await client.search(
        keyword="婚姻",
        doc_type="CD",
        max_results=1
    )

    assert search_result["success"] and len(search_result["results"]) > 0

    # 從 URL 提取 ty 和 id
    # URL 格式：data.aspx?id=xxx&ro=0&ty=CD&q=...
    url = search_result["results"][0]["url"]
    import re
    ty_match = re.search(r'[?&]ty=([^&]+)', url)
    id_match = re.search(r'[?&]id=([^&]+)', url)
    assert ty_match and id_match, f"無法解析 ty 和 id: {url}"

    ty = ty_match.group(1)
    doc_id = id_match.group(1)

    print(f"取得全文: ty={ty}, id={doc_id}")

    # 取得全文
    doc = await client.get_document(ty=ty, doc_id=doc_id)

    assert doc["success"] is True, f"取得全文失敗: {doc.get('error', 'Unknown')}"

    # 驗證必要欄位
    assert len(doc["title"]) > 0, "標題為空"
    assert len(doc["full_text"]) > 0, "全文為空"
    assert "url" in doc, "缺少 URL"
    assert "fields" in doc, "缺少 fields"

    print(f"標題: {doc['title'][:50]}...")
    print(f"全文長度: {len(doc['full_text'])} 字")
    print(f"結構化欄位數: {len(doc['fields'])}")

    print("[全文測試] 全文取得正常 [OK]")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_all_doc_types_searchable(client):
    """
    測試所有 10 種文件類型都可查詢

    文件類型：JCC, CD, T, C, J2, J1, J, D, Q, E
    """
    doc_types = {
        "JCC": "憲法法庭裁判",
        "CD": "大法官解釋",
        "T": "大法官不受理決議",
        "C": "司法解釋",
        "J2": "大法庭專區",
        "J1": "停止適用之判例",
        "J": "精選裁判",
        "D": "決議",
        "Q": "法律問題",
        "E": "行政函釋",
    }

    print(f"\n[文件類型測試] 測試所有 10 種類型...")

    success_count = 0
    for ty, name in doc_types.items():
        result = await client.search(
            keyword="法律",
            doc_type=ty,
            max_results=1
        )

        if result["success"]:
            success_count += 1
            print(f"  [OK] {name}({ty}): {len(result['results'])} 筆")
        else:
            # 允許暫時失敗（rate limiting）
            print(f"  [SKIP] {name}({ty}): {result.get('error', 'Unknown')}")

        # 延遲避免 rate limiting
        await asyncio.sleep(1)

    # 至少 50% 成功
    assert success_count >= 5, f"成功類型太少：{success_count}/10"
    print(f"[文件類型測試] {success_count}/10 種可查詢 [OK]")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_empty_result_handling(client):
    """
    測試空結果處理

    使用一個不太可能有結果的關鍵字
    """
    result = await client.search(
        keyword="XYZABC9999不存在的關鍵字",
        doc_type="CD",
        max_results=10
    )

    print(f"\n[空結果測試] 不存在的關鍵字")
    print(f"結果: success={result['success']}, 筆數={len(result['results'])}")

    # 即使沒結果，也應該回傳成功（不是錯誤）
    assert result["success"] is True
    assert len(result["results"]) == 0

    print("[空結果測試] 正常處理 [OK]")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_result_structure_integrity(client):
    """
    測試結果結構完整性

    驗證每筆結果都有必要欄位且格式正確
    """
    result = await client.search(
        keyword="法律",
        doc_type="CD",
        max_results=10
    )

    assert result["success"] and len(result["results"]) > 0

    print(f"\n[結構完整性] 檢查 {len(result['results'])} 筆結果...")

    for i, item in enumerate(result["results"]):
        # 必要欄位
        assert "title" in item, f"第 {i+1} 筆缺少 title"
        assert "url" in item, f"第 {i+1} 筆缺少 url"
        assert "date" in item, f"第 {i+1} 筆缺少 date"
        assert "summary" in item, f"第 {i+1} 筆缺少 summary"

        # URL 格式檢查（包含 data.aspx 和 ty 參數）
        assert "data.aspx" in item["url"], f"第 {i+1} 筆 URL 格式錯誤（缺少 data.aspx）"
        assert "ty=" in item["url"], f"第 {i+1} 筆 URL 格式錯誤（缺少 ty 參數）"

        # 標題不應該為空
        assert len(item["title"]) > 0, f"第 {i+1} 筆標題為空"

    print(f"[結構完整性] 所有結果結構正確 [OK]")
