# =====================================================================
#  台灣法律資料庫 MCP【整合版】— 公務電腦 全自動安裝 + 自我診斷 懶人包
#  整合版 = 原版 8 工具 + 增補版 3 工具（簡易案件/法令判解）
#           + 工程會採購法函釋 2 工具 + 三層自動更新（法規/函釋/程式碼）
#  特點：自帶可攜 Python、用 ZIP 取碼（免 git）、不需管理員權限、不改系統 PATH。
#  內建坑位修正：①避開微軟商店假 python ②MSIX 雙路徑寫設定
#               ③可編輯安裝免 cwd ④套件安裝驗證 ⑤自我診斷產報告
#  若先前裝過「台灣法律MCP（增補版）」或獨立「工程會函釋MCP」，
#  本包會就地升級並合併設定（pcc-letters 獨立伺服器將移除，功能已併入）。
# =====================================================================
$ErrorActionPreference = "Continue"
$ProgressPreference    = "SilentlyContinue"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 -bor [Net.SecurityProtocolType]::Tls11 -bor [Net.SecurityProtocolType]::Tls } catch {}

# ---- 路徑與參數 ----
$PyUrl   = "https://github.com/astral-sh/python-build-standalone/releases/download/20260602/cpython-3.11.15+20260602-x86_64-pc-windows-msvc-install_only.tar.gz"
$RepoZip = "https://codeload.github.com/oldbear-meme/mcp-taiwan-legal-db-integrated/zip/refs/heads/main"
$Root    = Join-Path $env:USERPROFILE "mcp-taiwan-legal-db-portable"
$PyDir   = Join-Path $Root "python"
$Py      = Join-Path $PyDir "python.exe"
$App     = Join-Path $Root "app"
$Tmp     = Join-Path $Root "_dl"
$Desktop = [Environment]::GetFolderPath("Desktop")
$ReportPath = Join-Path $Desktop "整合版MCP安裝診斷報告.txt"
$PipLog     = Join-Path $Desktop "整合版MCP套件安裝記錄.txt"
$pkgRoot = Join-Path $env:LOCALAPPDATA "Packages\Claude_pzs8sxrjxfjjc"

$R = New-Object System.Collections.Generic.List[string]
function Say($m,$c="White"){ Write-Host $m -ForegroundColor $c }
function Rep($m){ $R.Add([string]$m) }
function SaveReport(){ try { [System.IO.File]::WriteAllText($ReportPath, ($R -join "`r`n"), (New-Object System.Text.UTF8Encoding($false))) } catch {} }
function Fail($m){ Say "`n[X] $m" "Red"; Rep "[FAIL] $m"; SaveReport; Say "`n安裝中止。完整診斷已存到桌面：" "Yellow"; Say "  $ReportPath" "Yellow"; Say "把該檔貼回給協助你的人（或 Claude）即可判讀。" "Yellow"; Read-Host "`n按 Enter 關閉"; exit 1 }

Say "==================================================" "Cyan"
Say "   台灣法律 MCP【整合版】— 全自動安裝 + 自我診斷" "Cyan"
Say "   法規/判決/釋憲/判解 + 工程會採購法函釋 + 自動更新" "Cyan"
Say "   安裝位置：$Root" "Gray"
Say "==================================================`n" "Cyan"
Rep "===== 整合版 MCP 安裝診斷報告  $(Get-Date) ====="
Rep "安裝位置：$Root"
Rep ""

New-Item -ItemType Directory -Force -Path $Root,$Tmp | Out-Null

# ---- [1/7] 環境檢查 ----
Say "[1/7] 環境檢查 ..." "Cyan"
if (-not (Get-Command tar -ErrorAction SilentlyContinue)) { Fail "找不到內建 tar（需 Windows 10 1803 以後）。請更新 Windows 後重試。" }
$isMsix = Test-Path $pkgRoot
Rep ("[環境] tar=OK; MSIX(商店版)=" + $isMsix)
if ($isMsix) { Say "      偵測到 Microsoft Store（MSIX）版 Claude —— 將套用雙路徑寫設定" "Yellow" }
else         { Say "      偵測到一般安裝版 Claude" "Gray" }

# ---- [2/7] 可攜版 Python ----
Say "[2/7] 取得免安裝 Python（首次約 30-60MB；已有就沿用）..." "Cyan"
if (-not (Test-Path $Py)) {
    $pyTgz = Join-Path $Tmp "python.tar.gz"
    try { Invoke-WebRequest -Uri $PyUrl -OutFile $pyTgz } catch {}
    if (-not (Test-Path $pyTgz) -or (Get-Item $pyTgz).Length -lt 1000000) { Fail "下載 Python 失敗，多半是連不到 github.com（公務網路擋外網/需 Proxy）。" }
    & tar -xf $pyTgz -C $Root
}
if (-not (Test-Path $Py)) { Fail "解壓後找不到 $Py。" }
$pyVer = ((& $Py --version) 2>&1 | Out-String).Trim()
Rep "[Python] $pyVer @ $Py"
if ($pyVer -notmatch "Python\s+3\.(1[0-9]|[2-9][0-9])") { Fail "Python 版本異常：$pyVer" }
Say "      OK：$pyVer" "Green"

# ---- [3/7] 程式碼（整合版；舊版增補版會就地升級）----
Say "[3/7] 取得整合版 MCP 程式碼 ..." "Cyan"
$isIntegrated = (Test-Path (Join-Path $App "mcp_server\pcc_updater.py")) -and (Test-Path (Join-Path $App "verify.py"))
if (-not $isIntegrated) {
    $zip = Join-Path $Tmp "repo.zip"
    try { Invoke-WebRequest -Uri $RepoZip -OutFile $zip } catch {}
    if (-not (Test-Path $zip) -or (Get-Item $zip).Length -lt 1000) { Fail "下載程式碼失敗，請確認能連到 github.com。" }
    $ex = Join-Path $Tmp "repo"; if (Test-Path $ex) { Remove-Item $ex -Recurse -Force }
    Expand-Archive -Path $zip -DestinationPath $ex -Force
    $inner = Get-ChildItem $ex -Directory | Select-Object -First 1
    if (-not $inner) { Fail "解壓程式碼後找不到內容。" }
    # 就地「覆蓋」升級，不刪除整個 app：
    # Claude 若還開著，舊版快取（data\cache\legal_mcp.db*）會被鎖住，
    # 刪目錄會刪到一半失敗；robocopy 覆蓋則完全不碰快取檔。
    New-Item -ItemType Directory -Force -Path $App | Out-Null
    # 清掉先前失敗安裝可能殘留的 zip 內層資料夾
    Get-ChildItem $App -Directory -Filter "mcp-taiwan-legal-db-*" -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    & robocopy $inner.FullName $App /E /NFL /NDL /NJH /NJS /NP | Out-Null
    $rc = $LASTEXITCODE
    Rep "[程式碼] robocopy 退出碼=$rc（0-7 皆為成功）"
    if ($rc -ge 8) { Fail "複製程式碼失敗（robocopy 退出碼 $rc）。請完全結束 Claude 桌面版（工具列圖示右鍵 -> Quit）後重新執行本安裝。" }
} else {
    Say "      已是整合版，沿用既有程式碼（啟動時會自動檢查 GitHub 新版）" "Gray"
}
if (-not (Test-Path (Join-Path $App "verify.py"))) { Fail "程式碼缺 verify.py。" }
if (-not (Test-Path (Join-Path $App "mcp_server\data\pcc_letters.db"))) { Fail "程式碼缺 pcc_letters.db（工程會函釋資料庫）。" }
$dbSize = [math]::Round((Get-Item (Join-Path $App "mcp_server\data\pcc_letters.db")).Length/1MB,1)
Rep "[程式碼] OK @ $App（函釋庫 $dbSize MB）"
Say "      OK：程式碼與函釋資料庫（$dbSize MB）就緒" "Green"

# ---- [4/7] 安裝套件（最關鍵；完整記錄）----
Say "[4/7] 安裝套件（含 mcp SDK，連 pypi.org 下載，請耐心等）..." "Cyan"
"===== 套件安裝記錄 $(Get-Date) =====" | Set-Content $PipLog
(& $Py -m pip install --upgrade pip 2>&1)        | Tee-Object -FilePath $PipLog -Append | Out-Host
(& $Py -m pip install --no-warn-script-location -e "$App" 2>&1) | Tee-Object -FilePath $PipLog -Append | Out-Host
$pipCode = $LASTEXITCODE
Rep "[套件] pip install -e . 退出碼=$pipCode（記錄：$PipLog）"
Say "      pip 退出碼：$pipCode" "Gray"

# ---- [5/7] Playwright（選用）----
Say "[5/7] 瀏覽器備援 Playwright（選用）..." "Cyan"
(& $Py -m playwright install chromium 2>&1) | Out-Null
Rep "[Playwright] 退出碼=$LASTEXITCODE（失敗不影響一般查詢）"

# ---- [6/7] 自我診斷 ----
Say "[6/7] 自我診斷（import 測試 + 工具數 + 函釋試查 + 試跑伺服器）..." "Cyan"
Push-Location $env:TEMP
$imp = ((& $Py -c "import mcp.server.fastmcp, mcp_server.server; print('IMPORT OK')") 2>&1 | Out-String).Trim()
Pop-Location
Rep "[診斷] import 測試：$imp"
$importOK = ($imp -match "IMPORT OK")
if ($importOK) { Say "      import OK" "Green" } else { Say "      import 失敗：$imp" "Red" }

# 工具數應為 13；並實際查一筆工程會函釋
$diag = @"
import asyncio
from mcp_server.server import mcp
tools = asyncio.run(mcp.list_tools())
assert len(tools) == 13, f'tools={len(tools)}'
from mcp_server.tools import pcc_letters as p
r = p.search_pcc_letters(keyword='機關首長', max_results=1)
assert r['success'] and r['total'] > 0, r
print('DIAG_OK tools=13 pcc_total=' + str(r['total']))
"@
$diagFile = Join-Path $env:TEMP "diag_integrated.py"
[System.IO.File]::WriteAllText($diagFile, $diag, (New-Object System.Text.UTF8Encoding($false)))
Push-Location $env:TEMP
$dres = ((& $Py $diagFile) 2>&1 | Out-String).Trim()
Pop-Location
Rep "[診斷] 工具/函釋測試：$dres"
$diagOK = ($dres -match "DIAG_OK")
if ($diagOK) { Say "      工具 13 個、函釋試查 OK" "Green" } else { Say "      工具/函釋測試異常：$dres" "Red" }

$eo = Join-Path $env:TEMP "mcp_e.txt"
try {
    $p = Start-Process -FilePath $Py -ArgumentList "-m","mcp_server.server" -WorkingDirectory $App -RedirectStandardError $eo -RedirectStandardOutput (Join-Path $env:TEMP "mcp_o.txt") -PassThru -WindowStyle Hidden
    Start-Sleep -Seconds 3
    if (-not $p.HasExited) { Rep "[診斷] 伺服器試跑：啟動後持續執行 -> OK"; try{$p.Kill()}catch{} }
    else { Rep ("[診斷] 伺服器試跑：自行結束 退出碼=" + $p.ExitCode + "（異常）") }
    $err = Get-Content $eo -Raw -ErrorAction SilentlyContinue
    if ($err -and $err.Trim()) { Rep "[診斷] 伺服器 stderr：`r`n$($err.Trim())" }
} catch { Rep "[診斷] 試跑失敗：$($_.Exception.Message)" }

# ---- [7/7] 寫入設定檔（合併式；移除已併入的 pcc-letters；雙路徑含 MSIX）----
Say "[7/7] 寫入 Claude 設定（合併式，雙路徑含 MSIX 修正）..." "Cyan"
function WriteCfg($p) {
    $dir = Split-Path $p
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $cfg = $null
    if (Test-Path $p) {
        $bak = "$p.bak_" + (Get-Date -Format "yyyyMMdd_HHmmss")
        Copy-Item $p $bak -Force
        $raw = Get-Content $p -Raw -ErrorAction SilentlyContinue
        if ($raw -and $raw.Trim()) { try { $cfg = $raw | ConvertFrom-Json } catch { $cfg = $null } }
    }
    if (-not $cfg) { $cfg = [PSCustomObject]@{} }
    if (-not ($cfg.PSObject.Properties.Name -contains "mcpServers")) {
        $cfg | Add-Member -NotePropertyName "mcpServers" -NotePropertyValue ([PSCustomObject]@{})
    }
    $srv = [PSCustomObject]@{ command=$Py; args=@("-m","mcp_server.server"); cwd=$App }
    if ($cfg.mcpServers.PSObject.Properties.Name -contains "taiwan-legal-db") { $cfg.mcpServers."taiwan-legal-db" = $srv }
    else { $cfg.mcpServers | Add-Member -NotePropertyName "taiwan-legal-db" -NotePropertyValue $srv }
    # 舊的獨立工程會函釋伺服器已併入整合版，移除避免重複
    if ($cfg.mcpServers.PSObject.Properties.Name -contains "pcc-letters") {
        $cfg.mcpServers.PSObject.Properties.Remove("pcc-letters")
        Rep "[設定] 已移除獨立 pcc-letters（功能已併入 taiwan-legal-db）"
    }
    [System.IO.File]::WriteAllText($p, ($cfg | ConvertTo-Json -Depth 100), (New-Object System.Text.UTF8Encoding($false)))
}
$standard = Join-Path $env:APPDATA "Claude\claude_desktop_config.json"
$msix     = Join-Path $pkgRoot "LocalCache\Roaming\Claude\claude_desktop_config.json"
WriteCfg $standard; Rep "[設定] 已寫入 $standard"; Say "      已寫入：$standard" "Green"
if ($isMsix) { WriteCfg $msix; Rep "[設定] 已寫入(MSIX) $msix"; Say "      已寫入(MSIX)：$msix" "Green" }

# ---- 收尾：寫報告 + 結論 ----
Rep ""
Rep "[設定檔現況]"
foreach ($c in @($standard,$msix)) { Rep "  >>> $c"; if (Test-Path $c) { Rep (Get-Content $c -Raw) } else { Rep "      (不存在)" }; Rep "" }
SaveReport

Remove-Item $Tmp -Recurse -Force -ErrorAction SilentlyContinue

$allOK = ($importOK -and $diagOK)
Say "`n==================================================" $(if($allOK){"Green"}else{"Red"})
if ($allOK) {
    Say "   安裝與自我診斷全部通過！" "Green"
    Say "   接著手動做：" "Green"
    Say "   1) 完全結束 Claude 桌面版（工具列圖示右鍵 -> Quit）" "Yellow"
    Say "   2) 重開 -> 設定 -> Developer：taiwan-legal-db 應為 running" "Yellow"
    Say "   3) 新開對話試問：查民法第 184 條" "Yellow"
    Say "      再試問：查工程會關於機關首長的函釋" "Yellow"
    Say "   之後法規/函釋/程式碼都會自動更新，不用再管。" "Green"
} else {
    Say "   檔案與設定都就緒，但自我診斷未全過。" "Red"
    Say "   多半是連不到 pypi.org（公務網路擋外網/需 Proxy）。" "Yellow"
    Say "   請把這兩個桌面檔貼給協助你的人（或 Claude）判讀：" "Yellow"
    Say "     - $PipLog" "Yellow"
    Say "     - $ReportPath" "Yellow"
}
Say "   診斷報告已存到桌面：$ReportPath" "Gray"
Say "==================================================`n" $(if($allOK){"Green"}else{"Red"})
Read-Host "按 Enter 鍵關閉視窗"
