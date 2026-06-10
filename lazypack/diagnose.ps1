# 重新診斷（整合版）：不重裝，只檢查 + 試跑 + 抓日誌，輸出桌面報告
$ErrorActionPreference = "Continue"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
function Say($m,$c="White"){ Write-Host $m -ForegroundColor $c }
$Root=Join-Path $env:USERPROFILE "mcp-taiwan-legal-db-portable"; $Py=Join-Path $Root "python\python.exe"; $App=Join-Path $Root "app"
$report=Join-Path ([Environment]::GetFolderPath("Desktop")) "整合版MCP重新診斷報告.txt"
$L=New-Object System.Collections.Generic.List[string]; function Log($m){ $L.Add([string]$m); Write-Host $m }
Log "===== 整合版 MCP 重新診斷  $(Get-Date) ====="
Log ("[A] python.exe="+(Test-Path $Py)+"  app="+(Test-Path $App)+"  verify.py="+(Test-Path (Join-Path $App 'verify.py'))+"  mcp_server="+(Test-Path (Join-Path $App 'mcp_server')))
Log ("[A2] pcc_letters.db="+(Test-Path (Join-Path $App 'mcp_server\data\pcc_letters.db'))+"  pcc_updater.py="+(Test-Path (Join-Path $App 'mcp_server\pcc_updater.py'))+"  self_update.py="+(Test-Path (Join-Path $App 'mcp_server\self_update.py')))
if (Test-Path $Py){ Log ("[B] "+(((& $Py --version) 2>&1|Out-String).Trim())) }
if ((Test-Path $Py)-and(Test-Path $App)){ Push-Location $env:TEMP; Log ("[C] import 測試："+(((& $Py -c "import mcp.server.fastmcp, mcp_server.server; print('IMPORT OK')") 2>&1|Out-String).Trim())); Pop-Location }
if ((Test-Path $Py)-and(Test-Path $App)){ Push-Location $env:TEMP; Log ("[C2] 函釋試查："+(((& $Py -c "from mcp_server.tools import pcc_letters as p; r=p.search_pcc_letters(keyword='機關首長',max_results=1); print('PCC OK total='+str(r.get('total'))) if r.get('success') else print('PCC FAIL '+str(r))") 2>&1|Out-String).Trim())); Pop-Location }
if ((Test-Path $Py)-and(Test-Path $App)){
  $eo=Join-Path $env:TEMP "d_e.txt"
  try { $p=Start-Process -FilePath $Py -ArgumentList "-m","mcp_server.server" -WorkingDirectory $App -RedirectStandardError $eo -RedirectStandardOutput (Join-Path $env:TEMP "d_o.txt") -PassThru -WindowStyle Hidden; Start-Sleep 3
        if(-not $p.HasExited){ Log "[D] 伺服器試跑：OK（持續執行）"; try{$p.Kill()}catch{} } else { Log ("[D] 伺服器試跑：自行結束 退出碼="+$p.ExitCode) }
        $e=Get-Content $eo -Raw -ErrorAction SilentlyContinue; if($e -and $e.Trim()){ Log "[D] stderr:`r`n$($e.Trim())" } } catch { Log "[D] 試跑失敗：$($_.Exception.Message)" }
}
Log "[E] 設定檔"
foreach($c in @((Join-Path $env:APPDATA "Claude\claude_desktop_config.json"),(Join-Path $env:LOCALAPPDATA "Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\claude_desktop_config.json"))){
  Log "  >>> $c"; if(Test-Path $c){ Log (Get-Content $c -Raw) } else { Log "      (不存在)" } }
Log "[F] Claude MCP 日誌(最後30行)"
foreach($ld in @((Join-Path $env:APPDATA "Claude\logs"),(Join-Path $env:LOCALAPPDATA "Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\logs"))){
  if(Test-Path $ld){ Get-ChildItem $ld -Filter "*.log"|Sort-Object LastWriteTime -Descending|Select-Object -First 3|ForEach-Object{ Log ("  --- "+$_.Name+" ---"); Log ((Get-Content $_.FullName -Tail 30 -ErrorAction SilentlyContinue) -join "`r`n") } } }
[System.IO.File]::WriteAllText($report, ($L -join "`r`n"), (New-Object System.Text.UTF8Encoding($false)))
Say "`n報告已存到桌面：$report" "Green"; Say "把它貼給協助你的人（或 Claude）即可協助判讀。" "Yellow"
Read-Host "按 Enter 關閉"
