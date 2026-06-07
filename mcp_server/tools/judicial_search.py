"""司法院裁判書搜尋工具（httpx + F5 WAF cookie bypass）"""

import asyncio
import random
import re
import logging
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from mcp_server.config import (
    JUDICIAL_SEARCH_URL,
    JUDICIAL_EASY_SEARCH_URL,
    SEARCH_DELAY_MIN,
    SEARCH_DELAY_MAX,
    COURT_CODES,
    CASE_TYPE_CODES,
)
from mcp_server.cache.db import CacheDB
from mcp_server.parsers.judicial_parser import parse_search_results
from mcp_server.tools._errors import error_response
from mcp_server.tools.waf_bypass import (
    JudicialWAFBypass,
    WAFPermanentBlockError,
    get_with_waf_retry,
)

# JID 預期格式：court_code,year,case_word,case_number,date,serial
# 例：TPSV,104,台上,472,20150326,1
# 每個欄位用 [^,]+ 而非 .+，避免貪婪匹配跨欄位邊界。
_JID_RE = re.compile(r"^[A-Z]{2,6},\d+,[^,]+,[0-9A-Za-z\-]+,\d{8},\d+$")


def _valid_search_results(results: list[dict]) -> bool:
    """回傳 True 表示 results 每筆都有合法 jid，可以寫入 24h 快取。

    搜尋 parser 曾因司法院改版把 iframe chrome 誤 match 成 row（audit item #4）；
    在寫入前 gate 住，避免垃圾污染 24h 快取。
    """
    if not results:
        return False
    return all(bool(_JID_RE.match(r.get("jid", ""))) for r in results)

logger = logging.getLogger(__name__)

_QRYRESULT_URL = "https://judgment.judicial.gov.tw/FJUD/qryresult.aspx"
_QRYRESULT_BASE = "https://judgment.judicial.gov.tw/FJUD/"
_IFRAME_SRC_RE = re.compile(r'<iframe[^>]*src=["\']([^"\']+)', re.IGNORECASE)

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class JudicialSearchClient:
    """裁判書搜尋 — httpx + F5 WAF cookie bypass"""

    def __init__(self, cache: CacheDB, waf: JudicialWAFBypass):
        self.cache = cache
        self.waf = waf
        self._last_search_time: float = 0

    async def close(self):
        pass

    async def _rate_limit(self):
        now = asyncio.get_running_loop().time()
        elapsed = now - self._last_search_time
        min_delay = random.uniform(SEARCH_DELAY_MIN, SEARCH_DELAY_MAX)
        if elapsed < min_delay:
            await asyncio.sleep(min_delay - elapsed)
        self._last_search_time = asyncio.get_running_loop().time()

    async def search(
        self,
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
        """執行裁判書搜尋（可選擇查詢系統）

        Args:
            offset: 跳過前幾筆（分頁用，預設 0）
            search_system: 查詢系統選擇（"auto", "both", "regular", "easy"）
        """
        params = {
            "keyword": keyword,
            "court": court,
            "case_type": case_type,
            "year_from": year_from,
            "year_to": year_to,
            "case_word": case_word,
            "case_number": case_number,
            "main_text": main_text,
            "offset": offset,
            "max_results": max_results,  # Bug #2 修復：快取 key 必須包含 max_results
        }

        cached = await self.cache.get_search(params)
        if cached:
            cached["cached"] = True
            return cached

        if not keyword and not case_number and not main_text:
            return error_response(
                "至少需要提供 keyword / case_number / main_text 其一",
                query=params,
            )

        try:
            # ── 精確案號搜尋：同時查裁判書系統（GET）和簡易案件系統（POST）──
            if params.get("case_word") and params.get("case_number"):
                # 需要抓取 offset + max_results 筆，才能正確實現分頁
                fetch_count = offset + max_results

                # 根據 search_system 參數決定查詢策略（與關鍵字搜尋相同邏輯）
                should_query_regular = True
                should_query_easy = True

                if search_system == "regular":
                    should_query_easy = False
                elif search_system == "easy":
                    should_query_regular = False
                elif search_system == "both":
                    pass  # 兩者都查
                elif search_system == "auto":
                    if params.get("court"):
                        court_name = params["court"]
                        if any(kw in court_name for kw in ["高等法院", "最高法院", "智慧財產", "懲戒法院"]):
                            should_query_easy = False

                # 根據策略決定查詢哪些系統
                tasks = []
                if should_query_regular:
                    tasks.append(self._precise_search_http(params, fetch_count))
                else:
                    tasks.append(asyncio.sleep(0))

                if should_query_easy:
                    tasks.append(self._easy_search_http(params, fetch_count))
                else:
                    tasks.append(asyncio.sleep(0))

                results = await asyncio.gather(*tasks, return_exceptions=True)
                http_results = results[0] if should_query_regular else []
                easy_results = results[1] if should_query_easy else []

                if isinstance(http_results, Exception):
                    logger.warning("精確搜尋失敗: %s", http_results)
                    http_results = None
                if isinstance(easy_results, Exception):
                    logger.warning("簡易案件精確搜尋失敗: %s", easy_results)
                    easy_results = []

                combined: list[dict] = []
                seen_jids: set[str] = set()

                # 解包結果（精確搜尋的 http 返回 list，easy 返回 tuple）
                http_list = http_results if http_results and not isinstance(http_results, Exception) else []
                easy_list = easy_results[0] if isinstance(easy_results, tuple) else (easy_results or [])

                for r_item in http_list + easy_list:
                    jid = r_item.get("jid", "")
                    if jid and jid not in seen_jids:
                        seen_jids.add(jid)
                        combined.append(r_item)

                if combined:
                    if not params.get("court"):
                        combined.sort(key=lambda r: r.get("court_level", 99))

                    # 套用 offset 和 max_results 進行分頁切片
                    paginated_results = combined[offset:offset + max_results]

                    data = {
                        "success": True,
                        "query": params,
                        "total_count": len(combined),
                        "results": paginated_results,
                        "cached": False,
                        "timestamp": datetime.now().isoformat(),
                    }

                    if _valid_search_results(paginated_results):
                        await self.cache.set_search(params, data)
                    return data

            # ── 關鍵字搜尋：同時查兩個系統 ──
            await self._rate_limit()

            # 根據 search_system 參數決定查詢策略
            should_query_regular = True
            should_query_easy = True

            if search_system == "regular":
                should_query_easy = False
                logger.info("search_system=regular，僅查詢裁判書系統")
            elif search_system == "easy":
                should_query_regular = False
                logger.info("search_system=easy，僅查詢簡易系統")
            elif search_system == "both":
                logger.info("search_system=both，查詢兩個系統")
            elif search_system == "auto":
                # 智能判斷邏輯
                if params.get("court"):
                    court_name = params["court"]
                    # 非地方法院 → 只查裁判書系統
                    if any(kw in court_name for kw in ["高等法院", "最高法院", "智慧財產", "懲戒法院"]):
                        should_query_easy = False
                        logger.info("auto: 指定非地方法院 %s，跳過簡易系統", court_name)
                    else:
                        # 地方法院 → 查兩個系統
                        logger.info("auto: 指定地方法院 %s，查詢兩個系統（簡易系統會混入其他地院）", court_name)
                else:
                    # 未指定法院 → 查兩個系統
                    logger.info("auto: 未指定法院，查詢兩個系統")
            else:
                logger.warning("search_system 參數無效: %s，使用預設(both)", search_system)

            # 根據策略決定查詢哪些系統
            # 注意：如果查詢兩個系統，offset 需要在合併後應用（因為排序會改變順序）
            # 如果只查詢單一系統，可以在系統內部應用 offset（直接跳頁）
            query_both_systems = should_query_regular and should_query_easy

            if query_both_systems:
                # 查詢兩個系統：需要抓取 offset + max_results 筆，因為合併後才能確定順序
                fetch_count = offset + max_results
                tasks = []
                tasks.append(self._keyword_search_http(params, fetch_count, offset=0))
                tasks.append(self._easy_search_http(params, fetch_count, offset=0))
            else:
                # 查詢單一系統：可以直接在系統內部應用 offset（直接跳頁）
                tasks = []
                if should_query_regular:
                    tasks.append(self._keyword_search_http(params, max_results, offset))
                else:
                    tasks.append(asyncio.sleep(0))  # 占位

                if should_query_easy:
                    tasks.append(self._easy_search_http(params, max_results, offset))
                else:
                    tasks.append(asyncio.sleep(0))  # 占位

            results = await asyncio.gather(*tasks, return_exceptions=True)
            regular_result = results[0] if should_query_regular else ([], None)
            easy_result = results[1] if should_query_easy else ([], None)

            # 解包結果和總筆數
            if isinstance(regular_result, Exception):
                logger.warning("裁判書查詢失敗: %s", regular_result)
                regular_results = []
                regular_total = None
            else:
                regular_results, regular_total = regular_result

            if isinstance(easy_result, Exception):
                logger.warning("簡易案件查詢失敗: %s", easy_result)
                easy_results = []
                easy_total = None
            else:
                easy_results, easy_total = easy_result

            # 計算真實總筆數（兩個系統的總和，如果都有的話）
            real_total_count: int | None = None
            if regular_total is not None and easy_total is not None:
                real_total_count = regular_total + easy_total
            elif regular_total is not None:
                real_total_count = regular_total
            elif easy_total is not None:
                real_total_count = easy_total

            seen_jids: set[str] = set()
            merged: list[dict] = []
            for r_item in regular_results + easy_results:
                jid = r_item.get("jid", "")
                if jid and jid not in seen_jids:
                    seen_jids.add(jid)
                    merged.append(r_item)

            if not params.get("court"):
                merged.sort(key=lambda r: r.get("court_level", 99))

            # 套用分頁邏輯
            if query_both_systems:
                # 查詢兩個系統：需要在合併後套用 offset 切片
                results = merged[offset:offset + max_results]
            else:
                # 查詢單一系統：offset 已在內部處理，只需限制數量
                results = merged[:max_results]

            data = {
                "success": True,
                "query": params,
                "total_count": real_total_count if real_total_count is not None else len(results),
                "results": results,
                "cached": False,
                "timestamp": datetime.now().isoformat(),
            }

            # 加入各系統的件數（方便使用者判斷是否要分系統查詢）
            if should_query_regular or should_query_easy:
                data["regular_count"] = regular_total if should_query_regular else 0
                data["easy_count"] = easy_total if should_query_easy else 0

            # 當某個系統 >= 500 筆時，提示使用者
            info_messages = []
            if regular_total is not None and regular_total >= 500:
                info_messages.append(
                    f"裁判書系統顯示 {regular_total} 筆，但司法院限制最多只能取得前 500 筆。"
                    "建議按時間拆分（年度/月份/日期）或按法院拆分查詢。"
                )
            if easy_total is not None and easy_total >= 500:
                info_messages.append(
                    f"簡易系統顯示 {easy_total} 筆，但司法院限制最多只能取得前 500 筆。"
                    "建議按時間拆分（年度/月份/日期）或按法院拆分查詢。"
                )
            if info_messages:
                data["info"] = " ".join(info_messages)

            if _valid_search_results(results):
                await self.cache.set_search(params, data)

            return data

        except (asyncio.TimeoutError, httpx.TimeoutException):
            # httpx 的 timeout 實際型別是 httpx.TimeoutException（HTTPError 子類），
            # 必須在 httpx.HTTPError arm 之前攔截。asyncio.TimeoutError 涵蓋
            # waf_bypass 收斂上來的 Playwright warmup 逾時。
            logger.exception("搜尋逾時")
            return error_response(
                "搜尋逾時，請稍後重試或縮小查詢範圍", query=params
            )
        except WAFPermanentBlockError:
            logger.warning("搜尋遭司法院 WAF 硬擋")
            return error_response(
                "司法院網站暫時無法通過 WAF 防護，請稍後重試", query=params
            )
        except httpx.HTTPError:
            logger.exception("搜尋連線失敗")
            return error_response(
                "連線司法院網站失敗，請稍後重試", query=params
            )
        except Exception:
            logger.exception("搜尋發生未預期錯誤")
            return error_response(
                "搜尋發生未預期錯誤，請查看 server log 取得詳細資訊",
                query=params,
            )

    async def _precise_search_http(
        self, params: dict, max_results: int,
    ) -> list[dict] | None:
        """精確案號搜尋 — HTTP GET（裁判書系統）"""
        case_word = params["case_word"].replace("臺", "台")
        case_number = str(params["case_number"])

        base_params: dict[str, str] = {
            "jud_case": case_word,
            "jud_no": case_number,
            "judtype": "JUDBOOK",
        }

        year = params.get("year_from") or params.get("year_to")
        if year:
            base_params["jud_year"] = str(year)

        if params.get("court"):
            court_code = COURT_CODES.get(params["court"], params["court"])
            base_params["jud_court"] = court_code

        if params.get("case_type"):
            sys_codes = [CASE_TYPE_CODES.get(params["case_type"], "V")]
        else:
            sys_codes = ["V", "M", "A"]

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(15.0),
                follow_redirects=True,
                headers={"User-Agent": _USER_AGENT},
                cookies=self.waf.get_cookies(),
            ) as client:
                probe_params = {**base_params, "sys": sys_codes[0]}
                probe = await get_with_waf_retry(
                    client, _QRYRESULT_URL, self.waf, params=probe_params
                )
                outer_responses = [probe]
                if len(sys_codes) > 1:
                    outer_tasks = [
                        client.get(_QRYRESULT_URL, params={**base_params, "sys": sc})
                        for sc in sys_codes[1:]
                    ]
                    outer_responses += list(
                        await asyncio.gather(*outer_tasks, return_exceptions=True)
                    )

                iframe_tasks = []
                for resp in outer_responses:
                    if isinstance(resp, Exception) or resp.status_code != 200:
                        continue
                    m = _IFRAME_SRC_RE.search(resp.text)
                    if m:
                        src = m.group(1).replace("&amp;", "&")
                        if not src.startswith("http"):
                            src = _QRYRESULT_BASE + src
                        iframe_tasks.append(client.get(src))

                if not iframe_tasks:
                    logger.info("精確搜尋: 無 iframe src，可能無結果")
                    return None

                iframe_responses = await asyncio.gather(
                    *iframe_tasks, return_exceptions=True,
                )

                all_results: list[dict] = []
                seen_jids: set[str] = set()

                for resp in iframe_responses:
                    if isinstance(resp, Exception) or resp.status_code != 200:
                        continue
                    page_results = parse_search_results(resp.text)
                    for r in page_results:
                        jid = r.get("jid", "")
                        if jid and jid not in seen_jids:
                            seen_jids.add(jid)
                            all_results.append(r)

                if not params.get("court"):
                    all_results.sort(key=lambda r: r.get("court_level", 99))

                logger.info(
                    "精確搜尋 HTTP GET: %s %s → %d 筆",
                    params["case_word"], case_number, len(all_results),
                )
                return all_results[:max_results]

        except WAFPermanentBlockError:
            # WAF 硬擋不是「此路徑壞了改走 keyword」，而是整組請求都會擋。
            # 放行給上層 search() 統一分流。
            raise
        except Exception as e:
            logger.warning("精確搜尋 HTTP GET 失敗: %s", e)
            return None

    async def _keyword_search_http(
        self, params: dict, max_results: int, offset: int = 0,
    ) -> tuple[list[dict], int | None]:
        """關鍵字搜尋 — 裁判書查詢系統

        Returns:
            (results, total_count): 結果列表和真實總筆數
        """
        return await self._post_search(
            JUDICIAL_SEARCH_URL, params, max_results, offset, label="裁判書"
        )

    async def _easy_search_http(
        self, params: dict, max_results: int, offset: int = 0,
    ) -> tuple[list[dict], int | None]:
        """簡易案件查詢 — 簡易案件系統

        Returns:
            (results, total_count): 結果列表和真實總筆數
        """
        return await self._post_search(
            JUDICIAL_EASY_SEARCH_URL, params, max_results, offset, label="簡易案件"
        )

    async def _post_search(
        self, search_url: str, params: dict, max_results: int, offset: int = 0, label: str = ""
    ) -> tuple[list[dict], int | None]:
        """共用的 POST 表單搜尋邏輯

        Args:
            search_url: 搜尋系統 URL
            params: 搜尋參數
            max_results: 最多回傳筆數
            offset: 跳過前幾筆（分頁用，每頁 20 筆）
            label: 日誌標籤

        Returns:
            (results, total_count): 結果列表和真實總筆數（如果解析失敗則為 None）
        """
        is_easy = search_url == JUDICIAL_EASY_SEARCH_URL
        PAGE_SIZE = 20  # 每頁固定 20 筆
        start_page = (offset // PAGE_SIZE) + 1  # 起始頁碼（從 1 開始）
        skip_in_page = offset % PAGE_SIZE  # 頁內偏移

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENT},
            cookies=self.waf.get_cookies(),
        ) as client:
            r = await get_with_waf_retry(client, search_url, self.waf)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")

            viewstate = soup.find("input", {"name": "__VIEWSTATE"})
            event_val = soup.find("input", {"name": "__EVENTVALIDATION"})
            viewgen = soup.find("input", {"name": "__VIEWSTATEGENERATOR"})

            if not viewstate or not event_val:
                raise RuntimeError(
                    "無法取得 ASP.NET 表單 token（__VIEWSTATE / __EVENTVALIDATION）。"
                    "可能原因：F5 WAF cookies 失效（檢查 .judicial_cookies.json + Playwright 安裝）"
                    "或司法院頁面結構改版。"
                )

            form_data: dict[str, str] = {
                "__VIEWSTATE": viewstate["value"],
                "__EVENTVALIDATION": event_val["value"],
                "__VIEWSTATEGENERATOR": viewgen["value"] if viewgen else "",
                "__VIEWSTATEENCRYPTED": "",
                "judtype": "SIMJUDBOOK" if is_easy else "JUDBOOK",
                "whosub": "1" if is_easy else "0",
                "ctl00$cp_content$btnQry": "送出查詢",
            }

            if params.get("keyword"):
                form_data["jud_kw"] = params["keyword"]
            if params.get("main_text"):
                form_data["jud_jmain"] = params["main_text"]

            # 簡易案件系統不支援法院代碼，只有裁判書系統才傳 court
            if params.get("court") and not is_easy:
                court_code = COURT_CODES.get(params["court"], params["court"])
                form_data["jud_court"] = court_code

            if params.get("case_type") and not is_easy:
                type_code = CASE_TYPE_CODES.get(params["case_type"], params["case_type"])
                form_data["jud_sys"] = type_code

            # 簡易案件系統年度用民國年但需分拆成 dy/dm/dd 三個欄位
            if params.get("year_from"):
                year = params["year_from"]
                if is_easy:
                    form_data["dy1"] = str(year)
                    form_data["dm1"] = "01"
                    form_data["dd1"] = "01"
                else:
                    form_data["dy1"] = str(year)
            if params.get("year_to"):
                year = params["year_to"]
                if is_easy:
                    form_data["dy2"] = str(year)
                    form_data["dm2"] = "12"
                    form_data["dd2"] = "31"
                else:
                    form_data["dy2"] = str(year)

            if params.get("case_word"):
                form_data["jud_case"] = params["case_word"]
            if params.get("case_number"):
                form_data["jud_no"] = str(params["case_number"])

            r2 = await get_with_waf_retry(
                client, search_url, self.waf, method="POST", data=form_data
            )
            r2.raise_for_status()
            soup2 = BeautifulSoup(r2.text, "html.parser")

            iframe = soup2.find("iframe")
            if not iframe or not iframe.get("src"):
                logger.info("%s查詢：POST 後無 iframe，可能無結果", label)
                return ([], None)

            iframe_url = iframe["src"]
            if not iframe_url.startswith("http"):
                iframe_url = _QRYRESULT_BASE + iframe_url

            # 提取 q hash（用於構建分頁 URL）
            import re
            q_match = re.search(r"q=([0-9a-f]+)", iframe_url)
            q_hash = q_match.group(1) if q_match else None

            # 如果需要跳到指定頁碼，構建帶有 page 參數的 URL
            if start_page > 1 and q_hash:
                iframe_url = f"{_QRYRESULT_BASE}/qryresultlst.aspx?q={q_hash}&sort=DS&page={start_page}"
                logger.info("%s查詢：跳至第 %d 頁（offset=%d），URL: %s", label, start_page, offset, iframe_url)

            all_results: list[dict] = []
            seen_jids: set[str] = set()
            page_num = start_page  # 從指定頁碼開始
            MAX_PAGES = 100
            total_count_from_page: int | None = None

            while len(all_results) < max_results and page_num <= MAX_PAGES:
                r3 = await get_with_waf_retry(client, iframe_url, self.waf)
                if r3.status_code != 200:
                    logger.warning(
                        "%s查詢第 %d 頁 HTTP 失敗: %d", label, page_num, r3.status_code
                    )
                    break

                # 第一次迭代時解析總筆數（無論在哪一頁）
                if page_num == start_page:
                    from mcp_server.parsers.judicial_parser import extract_total_count
                    total_count_from_page = extract_total_count(r3.text)
                    if total_count_from_page is not None:
                        logger.info("%s查詢總筆數: %d", label, total_count_from_page)

                page_results = parse_search_results(r3.text)
                logger.info("%s查詢第 %d 頁: 解析 %d 筆", label, page_num, len(page_results))

                if not page_results:
                    break

                # 第一頁（start_page）需要跳過頁內偏移的筆數
                if page_num == start_page and skip_in_page > 0:
                    page_results = page_results[skip_in_page:]
                    logger.info("%s查詢：第 %d 頁跳過前 %d 筆，剩餘 %d 筆",
                               label, page_num, skip_in_page, len(page_results))

                new_count = 0
                for r_item in page_results:
                    jid = r_item.get("jid", "")
                    if jid and jid not in seen_jids:
                        seen_jids.add(jid)
                        all_results.append(r_item)
                        new_count += 1

                if new_count == 0 and page_num > 1:
                    break

                if len(all_results) >= max_results:
                    break

                next_url = self._extract_next_page_url(r3.text)
                if not next_url:
                    break

                iframe_url = next_url
                page_num += 1

            if not params.get("court"):
                all_results.sort(key=lambda r: r.get("court_level", 99))

            logger.info("%s查詢完成: %d 筆 (真實總數: %s)", label, len(all_results),
                       total_count_from_page if total_count_from_page is not None else "未知")
            return (all_results[:max_results], total_count_from_page)

    @staticmethod
    def _extract_next_page_url(html: str) -> str | None:
        """從結果頁 HTML 中擷取下一頁 URL"""
        soup = BeautifulSoup(html, "html.parser")
        next_link = soup.find("a", id="hlNext")
        if not next_link:
            return None
        href = next_link.get("href")
        if not href:
            return None
        if href.startswith("/"):
            href = f"https://judgment.judicial.gov.tw{href}"
        elif not href.startswith("http"):
            href = _QRYRESULT_BASE + href
        return href