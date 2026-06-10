# mcp-taiwan-legal-db（整合版）🌟🏗️

[English](README.en.md) · **繁體中文**

**本專案為 [mcp-taiwan-legal-db](https://github.com/lawchat-oss/mcp-taiwan-legal-db)（LawChat 原版）→ [mcp-taiwan-legal-db-enhanced](https://github.com/AXK1990/mcp-taiwan-legal-db-enhanced)（增補版）的整合版本**

原專案 [mcp-taiwan-legal-db](https://github.com/lawchat-oss/mcp-taiwan-legal-db) 是一個由 [LawChat](https://lawchat.com.tw) 所開發的 MCP Server，其功能在於讓任何 MCP 相容的 AI 助手直接存取台灣公開法律資料：

- **司法院裁判書** — judgment.judicial.gov.tw（全文搜尋 + 取得）
- **全國法規資料庫** — law.moj.gov.tw（11,700+ 部法規）
- **憲法法庭** — cons.judicial.gov.tw（868 筆大法官解釋 + 憲判字，含理由書全文，離線快取）

[增補版](https://github.com/AXK1990/mcp-taiwan-legal-db-enhanced) 在原專案架構上增設：

🌟 **簡易案件系統查詢**<br>
🌟 **判解函釋查詢系統**（包含精選裁判、判例、司法解釋、決議、法律問題）<br>
🌟 **裁判書進階搜尋與分頁機制**

而本**整合版**在增補版的全部功能之上，再加入：

🏗️ **工程會函釋查詢**（行政院公共工程委員會「政府採購法規解釋函令」，3,600+ 則離線快取，1988–2026）<br>
🔄 **三層自動更新**：法規清單每週自動更新（沿用原版）＋ 工程會函釋每 7 天自動增量抓新 ＋ 程式碼每日自動檢查 GitHub 新版（下次重啟生效）

詳細增補內容請見 [CHANGELOG.md](CHANGELOG.md)。

---

## 特色

> **註**：以下功能表格中，🌟 標記為增補版新增功能，🏗️ 標記為本整合版新增功能，其餘功能均繼承自原專案。

| 功能 | 說明 |
|------|------|
| **原版的 8 個 MCP 工具** | 裁判書搜尋/全文、法規查詢、釋字/憲判字查詢、引用關係圖譜 |
| **🌟 簡易案件系統** | 支援查詢地方法院簡易案件與小額案件（🌟 增補版功能） |
| **🌟 法令判解系統** | 支援查詢大法官解釋、決議、法律問題、精選裁判、行政函釋等（🌟 增補版功能） |
| **🌟 進階搜尋** | 裁判書分頁查詢、系統選擇、件數資訊（🌟 增補版功能） |
| **🏗️ 工程會函釋** | 政府採購法規解釋函令本地快取查詢（search_pcc_letters / get_pcc_letter），支援關鍵字、採購法條號、發文字號、日期、現行有效篩選（🏗️ 整合版功能） |
| **🔄 自動更新** | 法規清單（每週六）、工程會函釋（每 7 天增量）、程式碼（每日檢查 GitHub，下次重啟生效；設 `TWLEGAL_SELF_UPDATE=0` 可停用）（🏗️ 整合版功能） |
| **離線快取** | 868 筆大法官解釋與憲判字（含理由書/意見書全文）從本地 JSON 即時回傳 |
| **引用關係圖譜** | 從理由書抽取所有引用的釋字/憲判字，追溯憲法學說演變 |
| **全文搜尋** | 裁判書關鍵字搜尋 + 釋字爭點/理由書全文搜尋 |
| **混合請求策略** | 預設用 httpx 直打（~0.25s），觸發司法院 F5 WAF 時自動以 Playwright 刷 cookie 後繼續 |

---

## ⚡ 快速上手

### 🪟 Windows 公務機懶人包（最簡單）

[`lazypack/`](lazypack/) 內附全自動安裝懶人包：把資料夾內 5 個檔案放在同一目錄，
雙擊「安裝_台灣法律MCP整合版.bat」即可——自帶可攜 Python、免 git、免管理員權限，
裝完自我診斷並在桌面留報告。曾安裝增補版或獨立工程會函釋 MCP 者會自動就地升級。
詳見 [lazypack/使用說明.txt](lazypack/使用說明.txt)。

### Linux / macOS

照順序執行下列指令（Python 3.10+ 適用）。

```bash
# 0. Debian / Ubuntu 前置安裝（若步驟 2 建立 venv 失敗時執行）
sudo apt install python3-venv python3-pip

# 1. Clone repo（整合版倉庫）
git clone https://github.com/oldbear-meme/mcp-taiwan-legal-db-integrated.git
cd mcp-taiwan-legal-db-integrated

# 2. 建立並初始化虛擬環境
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -e .

# 3. 安裝 Playwright Chromium（僅在司法院 WAF 觸發時使用，一般查詢不會啟動）
# macOS：
.venv/bin/python -m playwright install chromium

# Linux（需要安裝系統依賴，指令會要求 sudo 權限，僅完整支援 Debian/Ubuntu）：
.venv/bin/python -m playwright install --with-deps chromium

# 4. 驗證伺服器安裝
.venv/bin/python verify.py
```

**預期輸出：**
```
Server: 台灣法律資料庫
Tools: ['search_judgments', 'get_judgment', 'query_regulation', 'get_pcode', 'search_regulations', 'get_interpretation', 'search_interpretations', 'get_citations', 'search_legal_interpretations', 'search_legal_interpretations_advanced', 'get_legal_interpretation', 'search_pcc_letters', 'get_pcc_letter']
Setup OK
```
（註：Tools 清單實際為單行輸出）

**完成！**Repo 根目錄已經帶一份 `.mcp.json`，**任何在此資料夾內開的 Claude Code session 會自動載入這個 server**，不需要額外註冊。

---

### Windows

Windows 使用者請執行以下 PowerShell 指令（可整段複製貼上）：

```powershell
# 1. Clone repo（整合版倉庫）
git clone https://github.com/oldbear-meme/mcp-taiwan-legal-db-integrated.git
cd mcp-taiwan-legal-db-integrated

# 2. 建立並初始化虛擬環境
python -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\pip install -e .

# 3. 安裝 Playwright Chromium（僅在司法院 WAF 觸發時使用，一般查詢不會啟動）
.venv\Scripts\python -m playwright install chromium

# 4. 驗證伺服器安裝
.venv\Scripts\python verify.py
```

**預期輸出：**
```
Server: 台灣法律資料庫
Tools: ['search_judgments', 'get_judgment', 'query_regulation', 'get_pcode', 'search_regulations', 'get_interpretation', 'search_interpretations', 'get_citations', 'search_legal_interpretations', 'search_legal_interpretations_advanced', 'get_legal_interpretation', 'search_pcc_letters', 'get_pcc_letter']
Setup OK
```
（註：Tools 清單實際為單行輸出）

**⚙️ Windows 額外設定**

Repo 根目錄的 `.mcp.json` 預設使用 Linux / macOS 路徑格式。Windows 使用者需要修改：

```bash
# 將 .mcp.json 中的 "command" 從
".venv/bin/python"
# 改為
".venv\Scripts\python.exe"
```

或參考下方「註冊到你的 Claude client」章節的完整範例。

**完成！**修改 `.mcp.json` 後，**任何在此資料夾內開的 Claude Code session 會自動載入這個 server**，不需要額外註冊。

---

## 🔄 從原版本遷移

如果你之前安裝過原作者的 `mcp-taiwan-legal-db`，建議先移除再安裝整合版，避免套件衝突。

### 移除原版本

根據你的安裝方式選擇對應的移除指令：

**pip 安裝的情況：**

```bash
# Windows (PowerShell / CMD)
pip uninstall mcp-taiwan-legal-db

# Linux / macOS
pip3 uninstall mcp-taiwan-legal-db
```

**pipx 安裝的情況：**

```bash
pipx uninstall mcp-taiwan-legal-db
```

**uv 安裝的情況：**

```bash
uv tool uninstall mcp-taiwan-legal-db
```

### 安裝整合版

移除原版本後，依照上方「快速上手」章節的步驟安裝整合版即可。

### MCP 設定更新

如果你在 Claude Desktop 或其他 MCP client 中設定過原版本，需要更新設定檔：

**Claude Desktop 設定檔位置：**
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- Windows (Microsoft Store / MSIX 安裝): `C:\Users\<YourName>\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\claude_desktop_config.json`
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Linux: Claude Desktop 目前無 Linux 版，請改用 Claude Code CLI

將設定中的路徑改為指向整合版的安裝位置。

---

## 有什麼工具可以用

> **註**：原版 8 個工具 ＋ 增補版 3 個法令判解工具 ＋ 整合版 2 個工程會函釋工具，共 13 個工具。此外，`search_judgments` 工具已增強支援簡易案件系統查詢、進階搜尋與分頁機制。

13 個 MCP 工具，全部唯讀，全部只打台灣政府的公開資料庫（工程會函釋為本地快取）。

### 法規與裁判（原專案功能）

| 工具 | 用途 | 典型呼叫 |
|---|---|---|
| `search_judgments` | 搜尋司法院裁判書資料庫（含 🌟 增補版功能─簡易案件查詢） | `search_judgments(keyword="預售屋 遲延交屋", case_type="民事")` |
| `get_judgment` | 依 JID 或 URL 取得單筆判決全文 | `get_judgment(jid="TPSM,114,台上,3753,20251112,1")` |
| `query_regulation` | 查詢法規條文／範圍／全文／修法沿革 | `query_regulation(law_name="民法", article_no="184")` |
| `get_pcode` | 將法規名稱解析為 pcode（法規代號） | `get_pcode(law_name="律師法")` |
| `search_regulations` | 以關鍵字搜尋 11,700+ 部法規 | `search_regulations(keyword="勞動")` |

### 憲法法庭（原專案功能）

| 工具 | 用途 | 典型呼叫 |
|---|---|---|
| `get_interpretation` | 大法官解釋/憲判字全文（離線快取） | `get_interpretation("釋字748", reasoning_keyword="婚姻")` |
| `search_interpretations` | 搜尋釋字/憲判字（爭點 + 理由書全文） | `search_interpretations(keyword="集會自由")` |
| `get_citations` | 引用關係圖譜（往前追溯） | `get_citations("釋字748", include_context=True)` |

### 法令判解系統（🌟 增補版功能）

| 工具 | 用途 | 典型呼叫 |
|---|---|---|
| `search_legal_interpretations` | 搜尋司法院法令判解系統 | `search_legal_interpretations(keyword="不完全給付&瑕疵擔保", max_results=20)` |
| `search_legal_interpretations_advanced` | 進階搜尋（支援日期範圍） | `search_legal_interpretations_advanced(date_from="114/1/1", date_to="114/12/31", doc_types=["法律問題"])` |
| `get_legal_interpretation` | 取得法令判解全文 | `get_legal_interpretation(ty="Q", doc_id="114,1234")` |

### 工程會函釋（🏗️ 整合版功能）

| 工具 | 用途 | 典型呼叫 |
|---|---|---|
| `search_pcc_letters` | 搜尋工程會「政府採購法規解釋函令」（本地快取，3,600+ 則） | `search_pcc_letters(keyword="機關首長", article_no="22")` |
| `get_pcc_letter` | 取得單則函釋全文（含現行有效狀態） | `get_pcc_letter(letter_no="工程企字第11500052701號")` |

> 資料來源：[行政院公共工程委員會 政府採購法規解釋函令查詢系統](https://planpe.pcc.gov.tw)（公開資訊）。
> 「已停止適用」標記係依內文關鍵字判定，非 100% 精準；正式引用前請於工程會官網核對最新狀態。

### 工具細節

> **註**：以下工具細節說明主要來自原專案 README，本增補版本已根據新增功能進行更新。

<details>
<summary><b><code>search_judgments</code></b></summary>

搜尋司法院判決系統。支援：

- **精確案號查詢**（快，HTTP GET）：設定 `case_word` + `case_number`
- **全文關鍵字搜尋**：設定 `keyword`
- **裁判主文篩選**：`main_text="被告應將 移轉"` + `keyword="借名登記"` → 找被告敗訴的借名登記案
- 可依 `court`、`case_type`（民事／刑事／行政／懲戒）、`year_from`／`year_to` 過濾
- 結果自動依法院層級排序（最高 → 高等 → 地方）

**重要**：要查某個特定案號時，**一定**要用 `case_word`+`case_number`，不要放進 `keyword`。查精確案號時**不傳** `year_from`/`year_to`，因為案號年度與裁判日期年度可能不同。

```python
# ✅ 正確 — 查台上 3753（最高法院）
search_judgments(case_word="台上", case_number="3753", court="最高法院")

# ✅ 正確 — 全文搜尋
search_judgments(keyword="預售屋 遲延交屋")

# ❌ 錯 — 把案號放進 keyword
search_judgments(keyword="114年度台上字第3753號")
```
</details>

<details>
<summary><b><code>get_judgment</code></b></summary>

取得單筆判決的結構化全文。

- 輸入：`jid`（從 `search_judgments` 結果取得）或 `url`
- 輸出：`{case_id, court, date, main_text, facts, reasoning, cited_statutes, cited_cases, full_text, source_url}`
- HTTP GET data.aspx 取得全文
- 結果快取 30 天

```python
get_judgment(jid="TPSM,114,台上,3753,20251112,1")
```

單筆判決可能超過 1 萬 token。建議先用 `search_judgments` 取得 metadata，只在使用者明確需要時才抓全文。
</details>

<details>
<summary><b><code>query_regulation</code></b></summary>

查詢全國法規資料庫。

```python
# 單一條文
query_regulation(law_name="民法", article_no="184")

# 條文範圍
query_regulation(law_name="民法", from_no="184", to_no="198")

# 完整法規
query_regulation(law_name="律師法")

# 附修法沿革
query_regulation(law_name="勞動基準法", article_no="23", include_history=True)
```

支援 `law_name`（透過 `get_pcode` 自動解析 pcode）或直接傳 `pcode`。子條文如 `247-1`、`15-1` 都支援。
</details>

<details>
<summary><b><code>get_interpretation</code></b></summary>

取得大法官解釋（釋字第 1–813 號）或憲法法庭裁判（憲判字）全文。預設層從本地 JSON 快取即時回傳。

**分層設計**（節省 context）：

| 層級 | 觸發條件 | 離線？ |
|------|---------|-------|
| 預設層（字號/日期/爭點/解釋文） | 永遠回傳 | ✓ |
| 理由書片段 | `reasoning_keyword="關鍵字"` | ✓ |
| 理由書全文（最多 15,000 字） | `include_reasoning=True` | ✓ |
| 意見書片段 | `opinions_keyword="關鍵字"` | ✓ |
| 意見書全文 | `include_opinions=True` | ✓ |

```python
# 預設層（離線，~0ms）
get_interpretation("釋字748")

# 理由書中搜尋關鍵字
get_interpretation("釋字748", reasoning_keyword="婚姻自由")

# 在意見書中定位特定大法官
get_interpretation("釋字499", opinions_keyword="林子儀")

# 新制憲判字
get_interpretation("111年憲判字第1號")
```

建議先用 keyword 片段模式定位，只在需要時才開全文模式。
</details>

<details>
<summary><b><code>search_interpretations</code></b></summary>

搜尋大法官解釋與憲判字。關鍵字同時匹配標題、爭點、理由書全文。

```python
# 全文搜尋（搜爭點 + 理由書）
search_interpretations(keyword="集會自由")

# 篩選年度（新制）
search_interpretations(keyword="言論自由", year=112)

# 列舉最後 10 筆釋字
search_interpretations(number_from=804, number_to=813)
```
</details>

<details>
<summary><b><code>get_citations</code></b></summary>

從理由書中抽取所有引用的釋字/憲判字字號。追溯方向：查詢指定裁判**引用了哪些先前裁判**。

```python
get_citations("釋字748")
# → citations: [釋字第242號, 釋字第362號, 釋字第365號, ...]

# 附上引用前後 80 字片段
get_citations("釋字748", include_context=True)
```
</details>

<details>
<summary><b><code>get_pcode</code></b></summary>

將法規名稱轉換為全國法規資料庫的 pcode（法規代碼）。支援模糊比對。

```python
# 精確名稱
get_pcode(law_name="民法")

# 常用簡稱
get_pcode(law_name="勞基法")
# → 會建議「勞動基準法」

# 模糊搜尋
get_pcode(law_name="消保")
# → 會列出包含「消保」的法規供選擇
```
</details>

<details>
<summary><b><code>search_regulations</code></b></summary>

以關鍵字搜尋全國法規資料庫的 11,700+ 部法規名稱。

```python
# 搜尋包含「勞動」的法規
search_regulations(keyword="勞動")

# 搜尋智慧財產相關法規
search_regulations(keyword="智慧財產")

# 排除已廢止法規
search_regulations(keyword="銀行", exclude_abolished=True)
```
</details>

<details>
<summary><b><code>search_legal_interpretations</code></b>（🌟 增補版功能）</summary>

搜尋司法院法令判解系統（legal.judicial.gov.tw/FINT）。可搜尋大法官解釋、憲法法庭裁判、決議、法律問題、精選裁判、行政函釋等。

```python
# 關鍵字搜尋
search_legal_interpretations(keyword="不完全給付&瑕疵擔保")

# 指定文件類型
search_legal_interpretations(keyword="侵權行為", doc_type="精選裁判")

# 調整回傳筆數
search_legal_interpretations(keyword="租賃", max_results=50)
```

支援布林運算：`+`（或）、`-`（不含）、`&`（且）、`()`（組合）
</details>

<details>
<summary><b><code>search_legal_interpretations_advanced</code></b>（🌟 增補版功能）</summary>

進階搜尋法令判解系統，支援日期範圍篩選。採用兩階段查詢設計：

1. 第一階段：送出查詢條件，取得各類型件數（categories）
2. 第二階段：根據 categories 的類型名稱，精確篩選結果

```python
# 第一階段：查看 114 年有哪些類型
search_legal_interpretations_advanced(
    date_from="114/1/1",
    date_to="114/12/31"
)
# → categories: [{"name": "法律問題", "count": 80}, ...]

# 第二階段：取得全部法律問題
search_legal_interpretations_advanced(
    date_from="114/1/1",
    date_to="114/12/31",
    doc_types=["法律問題"],
    max_results=100
)
```
</details>

<details>
<summary><b><code>get_legal_interpretation</code></b>（🌟 增補版功能）</summary>

取得法令判解系統單筆全文。從 `search_legal_interpretations` 結果的 `ty` 和 `id` 欄位帶入。

```python
# ty 代碼對應（完整 10 種）：
# JCC = 憲法法庭裁判
# CD  = 大法官解釋
# T   = 大法官不受理決議
# C   = 司法解釋
# J2  = 大法庭專區
# J1  = 停止適用之判例
# J   = 精選裁判
# D   = 決議
# Q   = 法律問題
# E   = 行政函釋

get_legal_interpretation(ty="Q", doc_id="114,1234")
get_legal_interpretation(ty="D", doc_id="96,5678")
```
</details>

---

## 範例問法

```
「查民法第 184 條」
「搜尋跟預售屋遲延交屋有關的最高法院判決」
「釋字 748 的理由書重點是什麼」
「哪些大法官解釋討論過集會自由」
「釋字 748 引用了哪些先前的釋字」
「查 111 年憲判字第 1 號」
```

---

## 註冊到你的 Claude client

依你使用的 Claude client 選對應的段落。

### Claude Code (CLI)

Claude Code 會自動載入專案根目錄的 `.mcp.json`。這個 repo 已經內建一份。

**Linux / macOS 使用者**（內建版本，無需修改）：
```json
{
  "mcpServers": {
    "taiwan-legal-db": {
      "command": ".venv/bin/python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "."
    }
  }
}
```

**Windows 使用者**（需要修改 `.mcp.json`）：
```json
{
  "mcpServers": {
    "taiwan-legal-db": {
      "command": ".venv\\Scripts\\python.exe",
      "args": ["-m", "mcp_server.server"],
      "cwd": "."
    }
  }
}
```

**零設定**：`cd` 進 repo 之後跑 `claude` 就好。MCP server 列表會看到 `taiwan-legal-db`，而且此資料夾不會有其他多餘的 server。

**跟隊友分享**：`.mcp.json` 已經 commit 進 repo。任何人 clone 下來跟著 Quick Start 跑完，就會自動完成 MCP 註冊。

**加到其他專案**（你想在另一個資料夾用這個 MCP）：用 `claude mcp add` 以 project scope 加入：

**macOS / Linux：**
```bash
cd /path/to/your/other/project
claude mcp add taiwan-legal-db --scope project --cwd "/absolute/path/to/mcp-taiwan-legal-db-integrated" -- \
  "/absolute/path/to/mcp-taiwan-legal-db-integrated/.venv/bin/python" \
  -m mcp_server.server
```

**Windows（PowerShell）：**
```powershell
cd C:\path\to\your\other\project
claude mcp add taiwan-legal-db --scope project --cwd "C:\path\to\mcp-taiwan-legal-db-integrated" -- `
  "C:\path\to\mcp-taiwan-legal-db-integrated\.venv\Scripts\python.exe" `
  -m mcp_server.server
```

這會在你另一個專案的根目錄寫出一份 `.mcp.json`。想在每個專案都能用，把 `--scope project` 改成 `--scope user`。

### Claude Desktop (macOS / Windows)

Claude Desktop 使用一個全域設定檔：

- **macOS**：`~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**：`%APPDATA%\Claude\claude_desktop_config.json`
- **Windows (Microsoft Store / WinGet / MSIX 安裝)**：`C:\Users\<YourName>\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\claude_desktop_config.json`

**最快開啟方式**：在 Claude Desktop 點選單列（不是視窗）→ **Settings** → **Developer** → **Edit Config**。檔案若不存在 Claude Desktop 會自動建立。

在 `mcpServers` 下加入以下內容（跟已有內容合併）：

**macOS / Linux：**
```json
{
  "mcpServers": {
    "taiwan-legal-db": {
      "command": "/absolute/path/to/mcp-taiwan-legal-db-integrated/.venv/bin/python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "/absolute/path/to/mcp-taiwan-legal-db-integrated"
    }
  }
}
```

**Windows：**
```json
{
  "mcpServers": {
    "taiwan-legal-db": {
      "command": "C:/Users/YourName/mcp-taiwan-legal-db-integrated/.venv/Scripts/python.exe",
      "args": ["-m", "mcp_server.server"],
      "cwd": "C:/Users/YourName/mcp-taiwan-legal-db-integrated"
    }
  }
}
```

把路徑換成你的實際 clone 路徑。`cwd` 欄位建議設定（確保資料檔載入路徑正確）。Windows 路徑可用正斜線 `/` 或雙反斜線 `\\`。

**存檔後，完全關閉並重新開啟 Claude Desktop**（不是只關視窗 — macOS 用 ⌘Q、Windows 右鍵工具列圖示 → Quit）。設定檔只會在重啟時重新載入。

### Claude Cowork (Pro 以上方案)

Claude Cowork 跑在 Claude Desktop 裡面，**共用同一個 `claude_desktop_config.json`** — 沒有另外的 Cowork 設定檔。任何你在 Claude Desktop 註冊的 MCP server 會自動透過 Claude Desktop SDK 橋接進 Cowork 的沙盒 VM。

**設定步驟**：

1. 照上面 **Claude Desktop** 段落把 `taiwan-legal-db` 加進 `claude_desktop_config.json`
2. **完全關閉並重新開啟 Claude Desktop** — 同時也會重啟 Cowork
3. 開一個 Cowork session，`taiwan-legal-db` 的工具就可以用了

**注意**：Cowork 目前在 Claude Pro / Max / Team / Enterprise 方案都可以用，且只能存取你明確授權的資料夾。MCP server 本身跑在你的 host 上（不是 Cowork VM 裡面），透過 Desktop SDK bridge 溝通，所以不管你授權哪個資料夾給 Cowork，它都存取得到內建的資料檔。

### 其他 MCP 相容 client

任何符合 [Model Context Protocol 規範](https://modelcontextprotocol.io/) 的 MCP client 都可以使用這個 server。啟動指令永遠是：

```
.venv/bin/python -m mcp_server.server
```

**Windows：**
```
.venv\Scripts\python.exe -m mcp_server.server
```

⋯⋯加上 `cwd` 設定為 repo 根目錄（Python 才找得到 `mcp_server` 套件）。設定位置請參考你使用的 client 的文件，找 `mcpServers` JSON 區塊寫在哪裡。

---

## 疑難排解

> **備注**：以下指令為 Linux / macOS 格式。Windows 使用者請將 `.venv/bin/` 替換為 `.venv\Scripts\`。

**`ModuleNotFoundError: No module named 'mcp_server'`**
→ 你沒有在 venv 裡面跑 `pip install -e .`。回到 Quick Start 步驟 2。

**`FileNotFoundError: data/pcode_all.json`**
→ 內建的 `mcp_server/data/pcode_all.json` 不見或被刪了。用 `git checkout mcp_server/data/pcode_all.json` 還原，或觸發重新下載：
```bash
.venv/bin/python -m mcp_server.updater
```

**MCP client 回報「伺服器啟動失敗」**
→ 直接跑 Quick Start 步驟 3 的驗證指令。若失敗，代表 import chain 壞了 — 看 traceback。若通過，問題在 MCP client 的啟動設定（路徑或 cwd 錯了）。

**`ssl.SSLCertVerificationError: ... Missing Subject Key Identifier`**
→ 這是 OpenSSL 3.6+ 對 TWCA Global Root CA 的廣泛 rejection，**不是 certifi 舊的問題**。本 repo 透過 [`truststore`](https://github.com/sethmlarson/truststore) 套件讓 Python 改用作業系統原生的 trust store（macOS Security framework、Windows CryptoAPI、Linux 系統 CA），**所有路徑都保留完整 SSL 驗證（`verify=True`）**，不使用 `verify=False`。這在 macOS、Windows 以及 OpenSSL <3.6 的 Linux 都能正常工作。OpenSSL 3.6+ 的 Linux 環境（Fedora 40+、未來的 Ubuntu LTS）目前可能仍有問題，歡迎 issue 回報。

---

## WAF 處理機制

司法院 `judgment.judicial.gov.tw` 部署了 F5 BIG-IP ASM WAF，純 HTTP 請求可能被擋（回固定 245 bytes 的 "Request Rejected"）。

本專案採混合策略：

- 預設用 httpx 直接請求（~0.25s）
- 偵測到被擋（response 含 `Request Rejected` 或 JS challenge marker `bobcmn` / `TSPD`）自動 fallback 到 Playwright 跑一次 JS challenge
- 取得 TSPD cookies 後持久化到 `mcp_server/data/.judicial_cookies.json`（0600 權限，已 gitignore）
- 後續查詢繼續用 httpx 帶 cookies 執行

`cons.judicial.gov.tw`（釋字）跟 `law.moj.gov.tw`（法規）沒這個問題，不經過 WAF 流程。

---

## 資料來源與統計

所有資料都取自台灣政府**公開**資料庫。不會對外做其他網路呼叫：

| 來源 | 網域 | 說明 |
|------|------|------|
| 司法院裁判書系統 | judgment.judicial.gov.tw | 裁判書搜尋與全文（含簡易案件系統） |
| 司法院法令判解系統 | legal.judicial.gov.tw | 大法官解釋、決議、法律問題、精選裁判、行政函釋 |
| 司法院憲法法庭 | cons.judicial.gov.tw | 大法官解釋與憲判字（離線快取） |
| 全國法規資料庫 | law.moj.gov.tw | 法規條文與修法沿革 |

`mcp_server/config.py:ALLOWED_DOMAINS` 以硬編碼 allow-list 強制執行。伺服器會拒絕抓取任何不在這些網域的 URL。

### 憲法法庭資料統計

| 資料集 | 筆數 | 含理由書 | 含意見書 | 檔案大小 |
|--------|------|---------|---------|---------|
| 舊制釋字（old_cases.json） | 813 | 734 | 370 | 7.4 MB |
| 新制憲判字（new_cases.json） | 55 | 55 | 55 | 1.8 MB |

## 快取

| 資料類型 | TTL | 位置 |
|---|---|---|
| 判決全文 | 30 天 | `mcp_server/data/cache/legal_mcp.db`（SQLite，首次啟動時建立） |
| 搜尋結果 | 24 小時 | 同上 |
| 法規條文 | 7 天 | 同上 |
| pcode metadata | 30 天 | 同上 |
| 釋字/憲判字 | 本地 JSON（不過期） | `mcp_server/data/old_cases.json`、`new_cases.json` |

全部清除：刪掉 `mcp_server/data/cache/legal_mcp.db`。快取檔在 `.gitignore` 內。

## 🔄 自動更新（整合版三層機制）

整合版內建三層自動更新，全部在伺服器啟動時於**背景**執行，失敗只記 warning、絕不阻擋啟動與查詢：

| 層 | 內容 | 頻率 | 模組 |
|---|---|---|---|
| 法規清單 | `pcode_all.json` + `law_histories.json`（law.moj.gov.tw 官方 API） | 每週六 06:00 後首次啟動 | `mcp_server.updater`（沿用原版） |
| 工程會函釋 | `pcc_letters.db` 增量抓新函釋（planpe.pcc.gov.tw，由新到舊掃到無新資料即停） | 每 7 天 | `mcp_server.pcc_updater`（🏗️ 整合版） |
| 程式碼 | 檢查 GitHub main 分支新 commit，下載並覆蓋程式碼（本地資料一律保留），**下次重啟生效** | 每日最多一次 | `mcp_server.self_update`（🏗️ 整合版） |

手動更新：
```bash
.venv/bin/python -m mcp_server.updater            # 法規清單
.venv/bin/python -m mcp_server.pcc_updater        # 工程會函釋（增量）
.venv/bin/python -m mcp_server.pcc_updater --full # 工程會函釋（全量補抓）
.venv/bin/python -m mcp_server.self_update --force # 程式碼
```

環境變數：
- `TWLEGAL_SELF_UPDATE=0` — 停用程式碼自我更新
- `TWLEGAL_REPO=owner/name` — 改追蹤其他 GitHub repo（預設本倉庫）

---

## 專案結構

```
mcp-taiwan-legal-db-integrated/
├── .gitignore
├── .mcp.json              # 資料夾內 Claude Code session 自動註冊用
├── LICENSE                # MIT（程式碼）
├── DATA_LICENSE           # CC0 1.0（憲法法庭資料）
├── SOURCES.md             # 資料來源說明
├── CITATION.cff           # 學術引用格式
├── README.md              # 本檔（繁體中文）
├── README.en.md           # English version
├── pyproject.toml         # 套件 metadata 與相依
├── scripts/               # 🏗️ 工程會函釋全量重建工具（一般使用不需要）
│   ├── pcc_console_crawler.js  # 瀏覽器 Console 抓取（零安裝）
│   ├── crawler.py              # Python 版全量爬蟲
│   ├── build_db.py             # JSON → pcc_letters.db
│   └── schema.sql              # 資料表結構
└── mcp_server/
    ├── __init__.py
    ├── server.py          # FastMCP 入口 — 定義 13 個 @mcp.tool() function
    ├── config.py          # URL、法院代碼、快取 TTL、allowed domains
    ├── updater.py         # pcode_all.json 更新（每週六自動）
    ├── pcc_updater.py     # 🏗️ 工程會函釋增量更新（每 7 天自動）
    ├── self_update.py     # 🏗️ 程式碼自我更新（每日檢查 GitHub）
    ├── cache/db.py        # SQLite 快取層
    ├── data/
    │   ├── pcode_all.json          # 11,700+ 部法規（內建，~780 KB）
    │   ├── law_histories.json      # 修法沿革（內建，~9.6 MB）
    │   ├── old_cases.json          # 813 筆舊制釋字全文（內建，~7.4 MB）
    │   ├── new_cases.json          # 55 筆新制憲判字全文（內建，~1.8 MB）
    │   └── pcc_letters.db          # 🏗️ 3,600+ 則工程會函釋（內建，~10 MB）
    ├── models/            # Judgment / Regulation dataclass
    ├── parsers/           # 判決與法規頁面的 HTML parser
    ├── tools/
    │   ├── judicial_search.py      # search_judgments
    │   ├── judicial_doc.py         # get_judgment
    │   ├── lawsearch.py            # search_legal_interpretations, search_legal_interpretations_advanced, get_legal_interpretation
    │   ├── regulations.py          # query_regulation, get_pcode, search_regulations
    │   ├── constitutional_court.py # get_interpretation, search_interpretations, get_citations
    │   └── pcc_letters.py          # 🏗️ search_pcc_letters, get_pcc_letter
    └── tests/             # pytest 測試
```

## 執行測試

```bash
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest mcp_server/tests/ -v
```

---

## 關於

### 原專案

原專案為 **[lawchat-oss/mcp-taiwan-legal-db](https://github.com/lawchat-oss/mcp-taiwan-legal-db)**。

- 原作者：[LawChat](https://lawchat.com.tw)
- 原專案倉庫：[lawchat-oss/mcp-taiwan-legal-db](https://github.com/lawchat-oss/mcp-taiwan-legal-db)

原專案提供了台灣法律資料查詢功能，包括：
- 司法院裁判書系統查詢
- 全國法規資料庫查詢
- 憲法法庭大法官解釋查詢
- WAF 處理機制
- 離線快取設計

### 本專案（整合版本）

**本整合版本以增補版為基礎，包含其全部增補功能：**

🌟 **簡易案件系統查詢**：支援地方法院簡易案件與小額案件查詢<br>
🌟 **法令判解系統查詢**：支援查詢大法官解釋、決議、法律問題、精選裁判、行政函釋等<br>
🌟 **裁判書進階搜尋**：分頁機制、系統選擇、件數統計等功能

**並再整合下列功能：**

🏗️ **工程會函釋查詢**：行政院公共工程委員會「政府採購法規解釋函令」本地快取查詢<br>
🔄 **三層自動更新**：法規清單、工程會函釋、程式碼本身

**維護資訊**：
- 整合版倉庫：[oldbear-meme/mcp-taiwan-legal-db-integrated](https://github.com/oldbear-meme/mcp-taiwan-legal-db-integrated)
- 增補版倉庫：[AXK1990/mcp-taiwan-legal-db-enhanced](https://github.com/AXK1990/mcp-taiwan-legal-db-enhanced)
- 回報問題：[GitHub Issues](https://github.com/oldbear-meme/mcp-taiwan-legal-db-integrated/issues)

**重要聲明**：
- 本增補版本由社群開發者個人維護，與原專案作者及維護者無關
- 增補功能的品質、錯誤或問題，均與原專案作者無涉
- 使用者如有疑問或建議，請於增補版倉庫提出 issue

## 授權

**程式碼**：[MIT License](LICENSE)

**憲法法庭資料**：[CC0 1.0](DATA_LICENSE)（公有領域貢獻）— 任何人皆可自由使用、修改及散布，無需取得授權或署名。學術引用格式請參考 [CITATION.cff](CITATION.cff)。

裁判書與法規資料來源：[司法院](https://judgment.judicial.gov.tw)、[法務部](https://law.moj.gov.tw)（政府公開資料）。
憲法法庭資料來源：[司法院憲法法庭](https://cons.judicial.gov.tw)（依中華民國著作權法第 9 條屬公有領域）。詳見 [SOURCES.md](SOURCES.md)。

## 免責聲明

### 一般免責聲明（繼承自原專案）

This is an **unofficial** tool for querying publicly-available Taiwan legal databases. It is not affiliated with, endorsed by, or authorized by the Judicial Yuan, the Ministry of Justice, or any Taiwan government agency.

The data returned by this tool reflects the state of the upstream official sources at the time of query. It may be cached (see TTLs above), and **must not be treated as legal advice or a substitute for the authoritative official sources**. Always verify against the original sources before relying on the data for any legal or official purpose.

本工具為**非官方**的台灣公開法規資料查詢工具，與司法院、法務部或任何台灣政府機關無隸屬關係。查詢結果以上游官方資料庫當下狀態為準（且可能被快取 — 見上方 TTL 表），**不得作為法律意見或正式用途依據**，使用前請向官方資料庫驗證。

### 關於此增補版本

本專案為 [lawchat-oss/mcp-taiwan-legal-db](https://github.com/lawchat-oss/mcp-taiwan-legal-db) 的增補版本，專案架構完全沿用原作者設計，僅針對個人使用需求增補功能。

**增補版本的責任歸屬**：
- 增補功能（法令判解系統查詢、裁判書進階搜尋、分頁機制等）由社群開發者個人維護
- 增補功能的品質、錯誤、問題，均與原專案作者及維護者無關
- 原專案的功能與設計歸屬於原作者
- 使用者應自行評估工具的適用性，並對使用本工具所做出的任何決策負完全責任
- 任何基於本工具建構的應用程式、服務或衍生作品，須自行負責其行為、輸出正確性與對使用者的聲明
