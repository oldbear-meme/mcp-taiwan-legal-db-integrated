"""台灣法律資料庫 MCP Server — FastMCP 入口"""

import asyncio
import logging
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP

from mcp_server.cache.db import CacheDB
from mcp_server.tools._errors import error_response
from mcp_server.tools.regulations import RegulationClient
from mcp_server.tools.judicial_search import JudicialSearchClient
from mcp_server.tools.judicial_doc import JudgmentDocClient
from mcp_server.tools.waf_bypass import JudicialWAFBypass
from mcp_server.tools.lawsearch import LawSearchClient
from mcp_server.tools.constitutional_court import (
    get_interpretation as _cc_get_interpretation,
    search_interpretations as _cc_search_interpretations,
    get_citations as _cc_get_citations,
)
from mcp_server.tools.regulations import (
    _PCODE_ALL, _PCODE_REVERSE, _ABOLISHED_SET,
    reload_pcode_all,
)
from mcp_server.tools import pcc_letters as _pcc

# 日誌設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("taiwan-legal-mcp")

# 全域資源（lifespan 管理）
cache: CacheDB | None = None
reg_client: RegulationClient | None = None
jud_search: JudicialSearchClient | None = None
jud_doc: JudgmentDocClient | None = None
waf: JudicialWAFBypass | None = None
law_search: LawSearchClient | None = None


async def _maybe_update_pcode_all():
    """啟動時 Saturday-aware 檢查（MCP = 本地開發，只做啟動補漏）"""
    try:
        from mcp_server.updater import update_pcode_all, should_update_saturday
        should, reason = should_update_saturday()
        if not should:
            logger.info("pcode_all.json %s", reason)
            return
        logger.info("pcode_all.json %s，觸發更新", reason)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, update_pcode_all)
        reload_pcode_all()
        logger.info("pcode_all.json 更新完成")
    except Exception as e:
        logger.warning("pcode_all.json 更新失敗: %s", e)


async def _maybe_update_pcc_letters():
    """啟動時檢查工程會函釋庫（每 7 天增量抓新函釋，失敗不影響查詢）"""
    try:
        from mcp_server.pcc_updater import maybe_update
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, maybe_update)
    except Exception as e:
        logger.warning("pcc_letters.db 更新失敗: %s", e)


async def _maybe_self_update():
    """啟動時檢查 GitHub 是否有新版程式碼（每天最多一次，下次重啟生效）"""
    try:
        from mcp_server.self_update import maybe_self_update
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, maybe_self_update)
    except Exception as e:
        logger.warning("程式碼自我更新失敗: %s", e)


def _log_background_task_exception(task: asyncio.Task) -> None:
    """background task 的 done callback：cancelled 無聲，例外必留 traceback。"""
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error(
            "Background task %r failed", task.get_name(), exc_info=exc
        )


@asynccontextmanager
async def lifespan(server: FastMCP):
    """伺服器生命週期：啟動時初始化，關閉時清理"""
    global cache, reg_client, jud_search, jud_doc, waf, law_search

    # 啟動
    cache = CacheDB()
    await cache.initialize()
    await cache.cleanup_expired()
    await cache.cleanup_invalid_regulation_names()

    waf = JudicialWAFBypass()
    reg_client = RegulationClient(cache)
    jud_search = JudicialSearchClient(cache, waf)
    jud_doc = JudgmentDocClient(cache, waf)
    law_search = LawSearchClient(cache, waf)

    logger.info("台灣法律資料庫 MCP Server 已啟動")

    _pcode_task = asyncio.create_task(
        _maybe_update_pcode_all(), name="pcode_all_update"
    )
    _pcode_task.add_done_callback(_log_background_task_exception)

    _pcc_task = asyncio.create_task(
        _maybe_update_pcc_letters(), name="pcc_letters_update"
    )
    _pcc_task.add_done_callback(_log_background_task_exception)

    _self_update_task = asyncio.create_task(
        _maybe_self_update(), name="self_update"
    )
    _self_update_task.add_done_callback(_log_background_task_exception)

    # WAF cookies 預熱：沒預熱的話，第一個請求會在 search handler 內同步等
    # Playwright warmup，使用者看到的只會是籠統的「搜尋逾時」。
    _waf_task = asyncio.create_task(waf.ensure_ready(), name="waf_warmup")
    _waf_task.add_done_callback(_log_background_task_exception)

    yield

    # 關閉
    await reg_client.close()
    await jud_search.close()
    await jud_doc.close()
    await law_search.close()
    await cache.close()
    logger.info("MCP Server 已關閉")


# 建立 FastMCP 伺服器
mcp = FastMCP(
    name="台灣法律資料庫",
    instructions=(
        "查詢司法院裁判書、全國法規資料庫、大法官解釋（釋字）與憲法法庭裁判（憲判字）、"
        "法令判解系統，以及行政院公共工程委員會「政府採購法規解釋函令」（工程會函釋）的 MCP 工具。"
        "釋字/憲判字與工程會函釋從本地快取即時回傳，無需連網。"
    ),
    lifespan=lifespan,
)


# ============================================================
# 工具 1：搜尋裁判書
# ============================================================

@mcp.tool()
async def search_judgments(
    keyword: str = "",
    court: str = "",
    case_type: str = "",
    year_from: int = 0,
    year_to: int = 0,
    case_word: str = "",
    case_number: str = "",
    main_text: str = "",
    max_results: int = 10,
    offset: int = 0,
    search_system: str = "auto",
) -> dict:
    """搜尋司法院裁判書系統。

    結果自動按法院權威性排序（最高法院→高等法院→地方法院），同層級按原始排序。
    每筆結果含 court（法院名稱）、case_type（民事/刑事/行政）、court_level（1=最高/2=高等/3=地方）。

    【重要】查特定案號時，必須用 case_word + case_number（精確查詢），不要把案號放在 keyword。
    所有案件類型（包含一般案件、簡易案件、小額案件）都使用相同方式查詢，系統會自動同時查詢裁判書系統與簡易案件系統。
    例如查「114年度上易字第503號」→ case_word="上易", case_number="503"（不傳year_from/year_to）。
    例如查「114年度羅小字第412號」→ case_word="羅小", case_number="412"（不傳year_from/year_to）。
    例如查「114年度北簡字第100號」→ case_word="北簡", case_number="100"（不傳year_from/year_to）。
    注意：案號年度與裁判日期年度可能不同，查精確案號時不傳年度可避免遺漏。
    keyword 僅用於主題式全文檢索（如「預售屋 遲延交屋」），不可用於查詢特定案號。

    【裁判書系統 vs 簡易案件系統】:
    本工具可查詢兩個系統：
    1. 裁判書系統（通常系統）- 完整判決，支援所有參數過濾
    2. 簡易案件系統 - 地方法院簡易/小額案件，但有以下限制：
       ❌ 不支援 court 參數過濾（無法指定特定地方法院）
       ❌ 不支援 case_type 參數過濾（無法指定民事/刑事）
       ✅ 支援 keyword、main_text、case_word、case_number、year 等參數

    【search_system 參數說明】:
    - "auto"（預設）- 智能判斷：
      * 指定非地方法院（高等/最高/智財/懲戒） → 只查裁判書系統
      * 指定地方法院 → 查詢兩個系統（⚠️ 簡易系統會混入其他地院案件）
      * 未指定法院 → 查詢兩個系統
    - "both" - 強制查詢兩個系統（即使指定了 court/case_type）
    - "regular" - 只查裁判書系統（不含簡易案件）
    - "easy" - 只查簡易系統（僅地方法院簡易/小額案件）

    【指定地方法院時的注意事項】⚠️:
    當指定地方法院（如「臺灣臺東地方法院」）且 search_system="auto" 或 "both" 時：
    - 裁判書系統：正確過濾，只回傳該地院判決 ✅
    - 簡易系統：無法過濾，會混入全國所有地院的簡易案件 ❌

    **解決方法：在 keyword 中加入法院名稱進行二次過濾**
    範例：查臺東地院的侵權行為案件
    → keyword="侵權行為 臺灣臺東地方法院", court="臺灣臺東地方法院"
    → 簡易系統雖會查到其他地院，但因缺少「臺灣臺東地方法院」關鍵字而被排除

    或者使用 search_system="regular" 只查裁判書系統（不含簡易案件）

    【進階實務研究欄位】:
    - main_text: 裁判主文關鍵字 — 最有效的輸贏方篩選方式。
      主文措辭高度制度化（依民刑訴訟法條生成），substring match 接近
      解析半結構化欄位，精度高：
        * 「被告應將 移轉」→ 被告敗訴（物權移轉類）
        * 「被告應給付」→ 被告敗訴（金錢給付類）
        * 「原告之訴駁回」→ 原告敗訴
        * 「上訴駁回」→ 維持原審
      支援布林運算：+（或）、-（不含）、&（且）、()（組合）
        * 「被告應給付&損害賠償」→ 主文同時包含兩者
        * 「原告之訴駁回+上訴駁回」→ 主文包含任一種
    可與 keyword 併用，例：
        找「借名登記成立、被告敗訴」→
        main_text="被告應將 移轉", keyword="借名登記", case_type="民事"

    【分頁機制】:
    本工具每次最多回傳 max_results 筆（上限 200），但實際總筆數可能遠超過 200 筆。
    回傳結果中的 total_count 欄位顯示真實總筆數（從司法院網頁解析）。

    **當 total_count > 回傳筆數時，表示還有更多結果：**
    使用 offset 參數可取得後續結果，例如：
    - 第 1-200 筆：max_results=200, offset=0
    - 第 201-400 筆：max_results=200, offset=200
    - 第 401-600 筆：max_results=200, offset=400

    建議：先用小 max_results 測試，確認 total_count 後再用多次呼叫取得完整結果。

    【系統別件數資訊】:
    查詢結果中會包含 regular_count（裁判書系統件數）和 easy_count（簡易系統件數）。

    **當件數很多時，建議分系統查詢：**
    - 使用 search_system="regular" 查詢裁判書系統
    - 使用 search_system="easy" 查詢簡易系統
    - 可以更精確控制分頁，避免重複抓取資料

    **司法院 500 筆限制：**
    每個系統各有 500 筆上限，如某系統超過 500 筆，第 501 筆之後無法取得。
    解決方案：(1) 按時間拆分（年度、月份、日期）(2) 按法院拆分

    Args:
        keyword: 全文檢索關鍵字（對應 jud_kw）。支援布林運算：+（或）、-（不含）、&（且）、()（組合），例如「不完全給付&瑕疵擔保」、「民法-刑法」
        court: 法院名稱（如「最高法院」「臺灣高等法院」「臺灣臺北地方法院」）
        case_type: 案件類型（民事/刑事/行政/懲戒）
        year_from: 起始年度（民國年，如 110），關鍵字搜尋時使用，查精確案號時不填
        year_to: 截止年度（民國年，如 113），關鍵字搜尋時使用，查精確案號時不填
        case_word: 字別（如「台上」「上易」「重訴」「羅小」「北簡」），查特定案號時必填
        case_number: 案號（數字），查特定案號時必填
        main_text: 裁判主文關鍵字（對應 jud_jmain）— 結構化篩選輸贏方。支援布林運算：+（或）、-（不含）、&（且）、()（組合）
        max_results: 回傳筆數上限（預設 10，上限 200）
        offset: 跳過前幾筆（分頁用，預設 0）
        search_system: 查詢系統選擇（"auto"=智能判斷, "both"=兩者, "regular"=僅裁判書, "easy"=僅簡易），預設 "auto"

    Returns:
        包含搜尋結果的字典：success, query, total_count, results, cached, timestamp
    """
    if max_results <= 0:
        return error_response("max_results 必須大於 0")

    # 硬上限防止 OOM（100 頁 × 20 筆 = 2000 筆，但實務上 200 已足夠）
    max_results = min(max_results, 200)
    logger.info("search_judgments: keyword=%r, court=%r, case_type=%r, "
                "year=%s~%s, case_word=%r, case_number=%r, main_text=%r",
                keyword, court, case_type, year_from, year_to,
                case_word, case_number, main_text)
    result = await jud_search.search(
        keyword=keyword,
        court=court,
        case_type=case_type,
        year_from=year_from,
        year_to=year_to,
        case_word=case_word,
        case_number=case_number,
        main_text=main_text,
        max_results=max_results,
        offset=offset,
        search_system=search_system,
    )
    logger.info("search_judgments 完成: success=%s, count=%s, cached=%s",
                result.get("success"), result.get("total_count", 0), result.get("cached", False))
    return result


# ============================================================
# 工具 2：取得裁判書全文
# ============================================================

@mcp.tool()
async def get_judgment(
    jid: str = "",
    url: str = "",
) -> dict:
    """取得單一裁判書全文。

    支援兩種查詢方式：
    1. 以 JID 查詢（優先使用 Open Data API）
    2. 以 URL 查詢（直接載入頁面）

    Args:
        jid: 裁判書 JID（如「TPSV,104,台上,472,20150326,1」），從搜尋結果取得
        url: 裁判書 URL（如 https://judgment.judicial.gov.tw/FJUD/printData.aspx?id=...）

    Returns:
        包含裁判書全文的字典：case_id, court, date, main_text, facts, reasoning,
        cited_statutes, cited_cases, full_text, source_url
    """
    if not jid and not url:
        return error_response("至少需要提供 jid 或 url")

    logger.info("get_judgment: jid=%r, url=%r", jid, url[:80] if url else "")
    if jid:
        result = await jud_doc.get_by_jid(jid)
    else:
        result = await jud_doc.get_by_url(url)
    logger.info("get_judgment 完成: success=%s, cached=%s, court=%r",
                result.get("success"), result.get("cached", False), result.get("court", ""))

    return result


# ============================================================
# 工具 3：查詢法規條文
# ============================================================

@mcp.tool()
async def query_regulation(
    law_name: str = "",
    pcode: str = "",
    article_no: str = "",
    from_no: str = "",
    to_no: str = "",
    include_history: bool = False,
) -> dict:
    """查詢全國法規資料庫的法規條文。

    可查詢單一條文、條號範圍、或法規全文。

    Args:
        law_name: 法規名稱（如「民法」「勞動基準法」），會自動轉換為 pcode
        pcode: 法規代碼（如「B0000001」），若提供 law_name 可不填
        article_no: 條號（如「184」「247-1」「15-1」），查詢單一條文
        from_no: 起始條號（如「184」），查詢條號範圍時使用
        to_no: 截止條號（如「198」），查詢條號範圍時使用
        include_history: 是否包含修法沿革（使用者詢問修法歷程、修正時間、歷次修正內容時設為 True）

    Returns:
        包含法規條文的字典：law (pcode, name, status), articles, source_url, history（選填）
    """
    from mcp_server.tools.regulations import get_law_history

    if not pcode and law_name:
        pcode = reg_client.resolve_pcode(law_name)
        if not pcode:
            return error_response(
                f"找不到法規「{law_name}」的代碼（pcode）。"
                f"請使用 get_pcode 工具查詢，或直接提供 pcode。",
                law_name=law_name,
            )

    if not pcode:
        return error_response("須提供 law_name 或 pcode")

    logger.info("query_regulation: law_name=%r, pcode=%r, article_no=%r, range=%s~%s, history=%s",
                law_name, pcode, article_no, from_no, to_no, include_history)

    if article_no:
        result = await reg_client.get_article(pcode, article_no)
    elif from_no and to_no:
        result = await reg_client.get_article_range(pcode, from_no, to_no)
    else:
        result = await reg_client.get_all_articles(pcode)

    if include_history and result.get("success"):
        history = get_law_history(pcode)
        if history:
            result["history"] = history

    return result


# ============================================================
# 工具 4：法規名稱轉 pcode
# ============================================================

@mcp.tool()
async def get_pcode(law_name: str) -> dict:
    """將法規名稱轉換為全國法規資料庫的 pcode 代碼。

    涵蓋 11,700+ 部法規（法律 + 命令），支援模糊比對。

    Args:
        law_name: 法規名稱（如「民法」「勞基法」「消保法」）

    Returns:
        包含 pcode 的字典，或模糊比對建議
    """
    if law_name in _PCODE_ALL:
        pcode = _PCODE_ALL[law_name]
        return {
            "success": True,
            "law_name": law_name,
            "pcode": pcode,
            "status": "已廢止" if pcode in _ABOLISHED_SET else "現行法規",
        }

    resolved = reg_client.resolve_pcode(law_name)
    if resolved:
        full_name = _PCODE_REVERSE.get(resolved, law_name)
        return {
            "success": True,
            "law_name": full_name,
            "pcode": resolved,
            "matched_from": law_name,
            "status": "已廢止" if resolved in _ABOLISHED_SET else "現行法規",
        }

    suggestions = [
        name for name in _PCODE_ALL
        if law_name in name or name in law_name
    ]

    return error_response(
        f"找不到「{law_name}」對應的 pcode",
        suggestions=suggestions[:10],
        available_count=len(_PCODE_ALL),
    )


# ============================================================
# 工具 5：搜尋法規（關鍵字）
# ============================================================

@mcp.tool()
async def search_regulations(keyword: str, offset: int = 0, exclude_abolished: bool = False) -> dict:
    """以關鍵字搜尋法規名稱。

    在完整法規清單（11,700+ 部）中搜尋，回傳符合的法規名稱與 pcode。
    結果按現行法規優先排序，每頁 50 筆。

    Args:
        keyword: 搜尋關鍵字（如「勞動」「消費」「智慧財產」）
        offset: 分頁偏移（從第幾筆開始，預設 0）
        exclude_abolished: 排除已廢止法規（預設 False，已廢止法規仍可搜尋但標記狀態）

    Returns:
        符合關鍵字的法規列表
    """
    if not keyword:
        return error_response("請提供搜尋關鍵字")
    if offset < 0:
        return error_response("offset 不可為負數")

    logger.info("search_regulations: keyword=%r, offset=%d, exclude_abolished=%s",
                keyword, offset, exclude_abolished)
    matches = []
    for name, pcode in _PCODE_ALL.items():
        if keyword in name:
            if exclude_abolished and pcode in _ABOLISHED_SET:
                continue
            matches.append({
                "law_name": name,
                "pcode": pcode,
                "status": "已廢止" if pcode in _ABOLISHED_SET else "現行法規",
            })

    matches.sort(key=lambda m: (m["status"] != "現行法規", m["law_name"]))

    page_size = 50
    page = matches[offset:offset + page_size]

    return {
        "success": True,
        "keyword": keyword,
        "total_count": len(matches),
        "offset": offset,
        "has_more": offset + page_size < len(matches),
        "results": page,
    }


# ============================================================
# 工具 6：大法官解釋 / 憲法法庭裁判
# ============================================================

@mcp.tool()
def get_interpretation(
    case_id: str,
    include_reasoning: bool = False,
    reasoning_keyword: str = "",
    include_opinions: bool = False,
    opinions_keyword: str = "",
) -> dict:
    """取得司法院大法官解釋（釋字第 1-813 號）或憲法法庭裁判（憲判字）全文。

    預設層（字號/日期/爭點/解釋文）從本地快取即時回傳，無需連網。
    理由書/意見書支援全文模式與關鍵字片段模式。

    case_id 格式（自動解析）：「釋字第748號」「釋字748」「748」
    「111年憲判字第1號」「111憲判1」

    Args:
        case_id: 解釋/裁判字號字串
        include_reasoning: 回傳理由書全文（最多 15000 字）
        reasoning_keyword: 在理由書中搜尋關鍵字並回片段（覆蓋 include_reasoning）
        include_opinions: 回傳意見書全文
        opinions_keyword: 在意見書中搜尋關鍵字並回片段
    """
    return _cc_get_interpretation(
        case_id, include_reasoning, reasoning_keyword,
        include_opinions, opinions_keyword,
    )


# ============================================================
# 工具 7：搜尋大法官解釋 / 憲判字
# ============================================================

@mcp.tool()
def search_interpretations(
    keyword: str = "",
    year: int = 0,
    number_from: int = 0,
    number_to: int = 0,
    include_old: bool = True,
    include_new: bool = True,
    max_results: int = 30,
) -> dict:
    """列舉大法官解釋 / 憲法法庭裁判。支援關鍵字全文搜尋（搜爭點 + 理由書）。

    每筆結果帶 case_id，可直接傳給 get_interpretation()。

    Args:
        keyword: 關鍵字（標題/字號/爭點/理由書全文匹配）
        year: 篩選民國年度（0=不篩選，>0 只回新制憲判字）
        number_from: 起始號次（含），0=不篩選
        number_to: 截止號次（含），0=不篩選
        include_old: 包含舊制釋字（year=0 時才生效）
        include_new: 包含新制憲判字
        max_results: 回傳筆數上限（預設 30）
    """
    return _cc_search_interpretations(
        keyword, year, number_from, number_to,
        include_old, include_new, max_results,
    )


# ============================================================
# 工具 8：大法官解釋引用關係
# ============================================================

@mcp.tool()
def get_citations(
    case_id: str,
    include_context: bool = False,
) -> dict:
    """從大法官解釋/憲判字的理由書中抽取所有引用的其他釋字/憲判字字號。

    追溯方向：查詢指定裁判引用了哪些先前裁判（往前追溯）。

    Args:
        case_id: 解釋/裁判字號字串（格式同 get_interpretation）
        include_context: 每個引用附上原文前後 80 字片段
    """
    return _cc_get_citations(case_id, include_context)


# ============================================================
# 工具 9：搜尋法令判解
# ============================================================

@mcp.tool()
async def search_legal_interpretations(
    keyword: str,
    doc_type: str = "",
    max_results: int = 20,
    offset: int = 0,
) -> dict:
    """搜尋司法院法令判解系統（legal.judicial.gov.tw/FINT）。

    可搜尋大法官解釋、憲法法庭裁判、決議、法律問題、精選裁判、行政函釋等。
    與 get_interpretation / search_interpretations 的差異：
    - 本工具查詢線上「法令判解系統」，支援全文關鍵字搜尋，可跨多個資料類型
    - get_interpretation 查詢的是離線快取的大法官解釋／憲判字

    doc_type 可填以下中文名稱或留空（空白 = 全部類型）：
    憲法法庭裁判、大法官解釋、大法官不受理決議、司法解釋、
    大法庭專區、停止適用之判例、精選裁判、決議、法律問題、行政函釋

    分頁說明：每次最多回傳 max_results 筆，使用 offset 跳過前幾筆。
    例如取第 21-40 筆：max_results=20, offset=20。

    Args:
        keyword:     關鍵字（法院名稱、裁判案號、案由、全文檢索字詞）。支援布林運算：+（或）、-（不含）、&（且）、()（組合），例如「不完全給付&瑕疵擔保」
        doc_type:    資料類型篩選，空白表示搜尋全部類型
        max_results: 最多回傳筆數（預設 20，上限 200）
        offset:      跳過前幾筆（分頁用，預設 0）

    Returns:
        {success, keyword, doc_type, categories（各類筆數）,
         total_count, results, cached, timestamp}
        results 每筆含：doc_type, title, date, summary, ty, id, url
    """
    logger.info(
        "search_legal_interpretations: keyword=%r, doc_type=%r, offset=%d",
        keyword, doc_type, offset,
    )
    result = await law_search.search(
        keyword=keyword,
        doc_type=doc_type,
        max_results=max_results,
        offset=offset,
    )
    logger.info(
        "search_legal_interpretations 完成: success=%s, count=%s",
        result.get("success"), result.get("total_count", 0),
    )
    return result


# ============================================================
# 工具 9-2：進階搜尋法令判解（支援日期範圍）
# ============================================================

@mcp.tool()
async def search_legal_interpretations_advanced(
    keyword: str = "",
    date_from: str = "",
    date_to: str = "",
    doc_types: list[str] | None = None,
    max_results: int = 20,
    offset: int = 0,
) -> dict:
    """進階搜尋司法院法令判解系統，支援日期範圍篩選和文件類型過濾。

    ## 核心機制說明

    本工具採用「兩階段查詢」設計：
    1. 第一階段：送出查詢條件（日期、關鍵字），取得 categories 統計
    2. 第二階段：根據 categories 的類型名稱，精確篩選結果

    **重要：categories 中的 "name" 欄位值，可以直接用於 doc_types 參數！**

    ## 推薦工作流程（兩次查詢）

    **第一次查詢（探索）：**
    ```
    search_legal_interpretations_advanced(
        date_from="114/1/1",
        date_to="114/12/31",
        doc_types=None  # 不指定類型
    )

    回傳：
    categories: [
        {"ty": "Q", "name": "法律問題", "count": 80},
        {"ty": "D", "name": "決議", "count": 0},
        {"ty": "J", "name": "精選裁判", "count": 197},
        ...
    ]
    ```

    **第二次查詢（精確取得）：**
    ```
    search_legal_interpretations_advanced(
        date_from="114/1/1",
        date_to="114/12/31",
        doc_types=["法律問題"],  # 直接使用 categories 的 name 值
        max_results=100  # 調高上限以取得全部 80 筆
    )

    回傳：
    全部 80 筆「法律問題」類型的結果
    ```

    ## 使用範例

    **範例 1：查詢 96 年所有決議**
    ```python
    # 步驟 1：先查看有多少筆
    result1 = search_legal_interpretations_advanced(
        date_from="96/1/1", date_to="96/12/31"
    )
    # categories 顯示：{"ty": "D", "name": "決議", "count": 20}

    # 步驟 2：取得全部 20 筆決議
    result2 = search_legal_interpretations_advanced(
        date_from="96/1/1",
        date_to="96/12/31",
        doc_types=["決議"],  # 使用 categories 的 name
        max_results=50
    )
    ```

    **範例 2：查詢 114 年高院法律座談會**
    （注意：法律座談會在「法律問題」類別，不在「決議」類別）
    ```python
    # 步驟 1：查看 114 年有哪些類型
    result1 = search_legal_interpretations_advanced(
        date_from="114/1/1", date_to="114/12/31"
    )
    # categories 顯示：{"ty": "Q", "name": "法律問題", "count": 80}

    # 步驟 2：取得全部 80 筆法律問題
    result2 = search_legal_interpretations_advanced(
        date_from="114/1/1",
        date_to="114/12/31",
        doc_types=["法律問題"],
        max_results=100
    )
    ```

    **範例 3：查詢特定細分類型**
    ```python
    # 只查民事決議（網站表單直接支援的細分類型）
    result = search_legal_interpretations_advanced(
        date_from="96/1/1",
        date_to="96/12/31",
        doc_types=["民事決議"]
    )
    ```

    ## 文件類型選項說明

    **概括類型（對應 categories 的 name，使用後篩選機制）：**
    - "憲法法庭裁判", "大法官解釋", "大法官不受理決議", "司法解釋"
    - "大法庭專區", "停止適用之判例", "精選裁判", "決議", "法律問題", "行政函釋"

    **細分類型（網站表單直接支援，使用前篩選機制）：**
    - "民事決議", "刑事決議", "家事決議", "行政決議"

    **錯誤處理：**
    如果 doc_types 包含無效值，工具會報錯並列出所有有效選項。

    ## 參數說明

    Args:
        keyword:     關鍵字（選填），可用於縮小搜尋範圍
        date_from:   起始日期，格式：民國年/月/日（如 "114/1/1"）
        date_to:     結束日期，格式：民國年/月/日（如 "114/12/31"）
        doc_types:   文件類型列表（使用 categories 的 name 值或細分類型），None = 全部類型
        max_results: 最多回傳筆數（預設 20，上限 200），建議第二次查詢時調高以取得全部結果
        offset:      跳過前幾筆（分頁用，預設 0）

    Returns:
        {success, query, categories（各類筆數）, total_count, results, cached, timestamp}

        categories 結構：[{"ty": "代碼", "name": "類型名稱", "count": 筆數}, ...]
        results 每筆含：doc_type, title, date, summary, ty, id, url
    """
    logger.info(
        "search_legal_interpretations_advanced: keyword=%r, date_from=%r, date_to=%r, doc_types=%r, offset=%d",
        keyword, date_from, date_to, doc_types, offset,
    )
    result = await law_search.search_advanced(
        keyword=keyword,
        date_from=date_from,
        date_to=date_to,
        doc_types=doc_types,
        max_results=max_results,
        offset=offset,
    )
    logger.info(
        "search_legal_interpretations_advanced 完成: success=%s, count=%s",
        result.get("success"), result.get("total_count", 0),
    )
    return result


# ============================================================
# 工具 10：取得法令判解全文
# ============================================================

@mcp.tool()
async def get_legal_interpretation(
    ty: str,
    doc_id: str,
) -> dict:
    """取得司法院法令判解系統單筆全文。

    從 search_legal_interpretations 結果的 ty 和 id 欄位帶入。

    ty 代碼對應：
      JCC=憲法法庭裁判、CD=大法官解釋、T=大法官不受理決議、C=司法解釋、
      J2=大法庭專區、J1=停止適用之判例、J=精選裁判、D=決議、Q=法律問題、E=行政函釋

    Args:
        ty:     資料類型代碼（從 search_legal_interpretations 結果取得）
        doc_id: 文件 ID（從 search_legal_interpretations 結果取得）

    Returns:
        {success, ty, id, doc_type, title, full_text, url, cached, timestamp}
    """
    if not ty or not doc_id:
        return {
            "success": False,
            "error": "請提供 ty 和 doc_id（從 search_legal_interpretations 結果取得）",
        }

    logger.info("get_legal_interpretation: ty=%r, doc_id=%r", ty, doc_id)
    result = await law_search.get_document(ty=ty, doc_id=doc_id)
    logger.info(
        "get_legal_interpretation 完成: success=%s, cached=%s",
        result.get("success"), result.get("cached", False),
    )
    return result


# ============================================================
# 工具 11：搜尋工程會函釋
# ============================================================

@mcp.tool()
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
    """搜尋行政院公共工程委員會「政府採購法規解釋函令及相關函文」（工程會函釋）。

    供採購法疑義、釋疑案、章則或分層負責審查引用採購法（及其子法）函釋時查證。
    查的是本地快取（離線、零延遲），伺服器啟動時每 7 天自動增量更新。
    回摘要清單，取全文用 get_pcc_letter。法規不限政府採購法，亦含
    「機關委託技術服務廠商評選及計費辦法」等子法，可用 law_name 篩。

    Args:
        keyword: 主旨＋說明全文關鍵字（例：機關首長、契約變更、開口契約）
        article_no: 採購法條號（例：22、63、101、22-1）
        law_name: 法規名稱關鍵字（例：政府採購法、評選及計費辦法）
        letter_no: 發文字號模糊比對（例：工程企字）
        date_from: 發文日期下限（西元 ISO，例：2020-01-01）
        date_to: 發文日期上限（西元 ISO）
        only_active: 只回現行有效（排除停止適用），預設 True
        max_results: 筆數上限（預設 20）
        offset: 分頁偏移

    Returns:
        {success, total, returned, results:[{letter_id, letter_no, law_name,
                                             articles, subject, issue_date_roc, status}]}
    """
    logger.info("search_pcc_letters: keyword=%r, article_no=%r, law_name=%r",
                keyword, article_no, law_name)
    return _pcc.search_pcc_letters(
        keyword=keyword, article_no=article_no, law_name=law_name,
        letter_no=letter_no, date_from=date_from, date_to=date_to,
        only_active=only_active, max_results=max_results, offset=offset,
    )


# ============================================================
# 工具 12：取得工程會函釋全文
# ============================================================

@mcp.tool()
def get_pcc_letter(letter_id: str = "", letter_no: str = "") -> dict:
    """取得單一工程會函釋全文（主旨、說明全文、法規、條號、發文日期、現行有效狀態、來源）。

    letter_id 與 letter_no（發文字號）擇一提供。若 status 為 superseded/partial，
    務必改引取代函釋或標註已停止適用，勿直接援用。

    Args:
        letter_id: 函釋 ID（從 search_pcc_letters 結果取得）
        letter_no: 發文字號模糊比對（例：工程企字第11500052701號）

    Returns:
        {success, letter_id, letter_no, law_name, based_on, articles, subject,
         full_text, issuer, issue_date_roc, issue_date, status, superseded_by,
         status_note, source_url, fetched_at}
    """
    logger.info("get_pcc_letter: letter_id=%r, letter_no=%r", letter_id, letter_no)
    return _pcc.get_pcc_letter(letter_id=letter_id, letter_no=letter_no)


# ============================================================
# 啟動入口
# ============================================================

if __name__ == "__main__":
    mcp.run()
