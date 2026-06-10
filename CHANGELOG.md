# CHANGELOG

## [1.1.0] - 2026-06-10（整合版）

基於 [AXK1990/mcp-taiwan-legal-db-enhanced](https://github.com/AXK1990/mcp-taiwan-legal-db-enhanced) 1.0.0 的整合版本

### Added（新增功能）

#### 🏗️ 工程會函釋查詢（全新）
- `search_pcc_letters` - 搜尋行政院公共工程委員會「政府採購法規解釋函令及相關函文」
  - 支援關鍵字、採購法條號、法規名稱、發文字號、日期區間、現行有效篩選
  - 內建 3,600+ 則函釋本地快取（1988–2026），離線查詢零延遲
- `get_pcc_letter` - 取得單則函釋全文（含主旨、說明、法規條號、現行有效狀態、來源連結）
- 資料來源：planpe.pcc.gov.tw（公開資訊）；`scripts/` 內附全量重建工具

#### 🔄 自動更新（全新）
- `mcp_server.pcc_updater` - 工程會函釋增量更新
  - 伺服器啟動時背景檢查，每 7 天自動增量抓取新函釋（由新到舊掃到無新資料即停）
  - 禮貌頻率 1.5 秒/請求；失敗只記警告，不影響查詢
- `mcp_server.self_update` - 程式碼自我更新
  - 每日最多一次檢查 GitHub main 分支，有新 commit 即下載覆蓋程式碼（下次重啟生效）
  - 本地資料（pcode_all.json、law_histories.json、pcc_letters.db）一律保留
  - `TWLEGAL_SELF_UPDATE=0` 可停用；`TWLEGAL_REPO=owner/name` 可改追蹤其他倉庫
- 沿用原版 `mcp_server.updater`（法規清單每週六自動更新）

---

## [1.0.0] - 2026-05-31

基於 [lawchat-oss/mcp-taiwan-legal-db](https://github.com/lawchat-oss/mcp-taiwan-legal-db) 的增強版本

### Added（新增功能）

#### 🌟 簡易案件系統查詢（全新）
- 支援查詢司法院簡易案件系統（地方法院簡易案件、小額案件）
- 可透過 `search_system` 參數選擇：
  - `both` - 同時查詢裁判書系統與簡易案件系統
  - `easy` - 只查詢簡易案件系統
- 自動合併兩個系統的結果並按法院層級排序

#### 🌟 法令判解系統查詢（全新）
- `search_legal_interpretations` - 搜尋司法院法令判解系統
  - 支援大法官解釋、憲法法庭裁判、決議、法律問題、精選裁判、行政函釋等
  - 支援全文關鍵字搜尋（含布林運算符：+、-、&、()）

- `search_legal_interpretations_advanced` - 進階搜尋
  - 支援日期範圍篩選（民國年/月/日格式）
  - 支援文件類型精確篩選
  - 採用兩階段查詢機制（先探索類型，再精確取得）

- `get_legal_interpretation` - 取得法令判解全文
  - 支援所有法令判解類型（決議、法律問題、精選裁判等）

#### 🔧 裁判書搜尋增強
- **分頁支援**
  - 新增 `offset` 參數（可跳過前 N 筆）
  - 配合 `max_results` 可取得最多 500 筆結果
  - 自動解析並回傳真實總筆數（`total_count`）

- **系統選擇機制**
  - 新增 `search_system` 參數：
    - `auto` - 智能判斷（預設）
    - `both` - 雙系統查詢
    - `regular` - 僅裁判書系統
    - `easy` - 僅簡易案件系統

- **件數資訊**
  - `regular_count` - 裁判書系統件數
  - `easy_count` - 簡易案件系統件數
  - 自動提示 500 筆限制並建議解決方案（按時間/法院拆分）

### Changed（改進）
- 移除未使用的 `data.judicial.gov.tw` 域名配置
- 優化查詢效能與錯誤處理

---

## 原專案資訊
- 原專案：[lawchat-oss/mcp-taiwan-legal-db](https://github.com/lawchat-oss/mcp-taiwan-legal-db)
- 授權：MIT License
- 本增強版本由社群開發者維護，與原專案維護者無關
