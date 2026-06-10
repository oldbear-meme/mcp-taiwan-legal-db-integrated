# -*- coding: utf-8 -*-
"""程式碼自我更新器

伺服器啟動時在背景檢查 GitHub 上是否有新版程式碼；有則下載 zip 並
覆蓋本地 mcp_server 套件檔案，「下次重啟」生效（不影響本次執行）。

設計原則：
  - 每天最多檢查一次（state 檔記錄上次檢查時間與 commit SHA）。
  - 只覆蓋程式碼檔；本地資料（pcode_all.json、law_histories.json、
    pcc_letters.db、快取、state 檔）一律保留。
  - 任何失敗只記警告，絕不影響伺服器啟動與查詢。
  - 設環境變數 TWLEGAL_SELF_UPDATE=0 可停用。
  - 預設追蹤的 repo 可用環境變數 TWLEGAL_REPO 覆蓋（格式 owner/name）。

手動執行：
  python -m mcp_server.self_update          # 立即檢查並更新
  python -m mcp_server.self_update --force  # 忽略每日間隔強制檢查
"""

import io
import json
import logging
import os
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from mcp_server.ssl_setup import inject_os_trust_store

inject_os_trust_store()

import httpx

logger = logging.getLogger(__name__)

DEFAULT_REPO = "AXK1990/mcp-taiwan-legal-db-integrated"
BRANCH = "main"

PACKAGE_DIR = Path(__file__).resolve().parent          # .../mcp_server
STATE_PATH = PACKAGE_DIR / "data" / "self_update_state.json"

# 這些檔案/目錄屬於本地資料，更新時絕不覆蓋或刪除
PRESERVE = {
    "data/pcode_all.json",
    "data/law_histories.json",
    "data/pcc_letters.db",
    "data/self_update_state.json",
}

CHECK_INTERVAL_HOURS = 24
TIMEOUT = 60.0


def _repo() -> str:
    return os.environ.get("TWLEGAL_REPO", DEFAULT_REPO).strip("/ ")


def _enabled() -> bool:
    return os.environ.get("TWLEGAL_SELF_UPDATE", "1") not in ("0", "false", "no")


def _load_state() -> dict:
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=str(STATE_PATH.parent), suffix=".tmp", prefix="self_update_",
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, str(STATE_PATH))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def should_check(force: bool = False) -> tuple[bool, str]:
    if not _enabled():
        return False, "TWLEGAL_SELF_UPDATE=0，自我更新已停用"
    if force:
        return True, "強制檢查"
    state = _load_state()
    last = state.get("last_check", "")
    if not last:
        return True, "尚無檢查紀錄"
    try:
        last_dt = datetime.fromisoformat(last)
    except ValueError:
        return True, f"無法解析上次檢查時間: {last}"
    hours = (datetime.now(timezone.utc) - last_dt).total_seconds() / 3600
    if hours >= CHECK_INTERVAL_HOURS:
        return True, f"距上次檢查已 {hours:.0f} 小時"
    return False, f"距上次檢查 {hours:.0f} 小時，未達 {CHECK_INTERVAL_HOURS} 小時"


def _fetch_latest_sha(client: httpx.Client) -> str:
    url = f"https://api.github.com/repos/{_repo()}/commits/{BRANCH}"
    r = client.get(url, headers={"Accept": "application/vnd.github+json"})
    r.raise_for_status()
    return r.json()["sha"]


def _download_repo_zip(client: httpx.Client) -> bytes:
    url = f"https://codeload.github.com/{_repo()}/zip/refs/heads/{BRANCH}"
    r = client.get(url)
    r.raise_for_status()
    return r.content

def _apply_zip(zip_bytes: bytes) -> int:
    """把 zip 內 mcp_server/ 子樹覆蓋到本地套件目錄（保留本地資料檔）。

    Returns:
        覆蓋的檔案數
    """
    updated = 0
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        # zip 第一層是 <repo>-<branch>/
        roots = {n.split("/", 1)[0] for n in names if "/" in n}
        if len(roots) != 1:
            raise ValueError(f"zip 結構異常：{sorted(roots)[:5]}")
        root = roots.pop()
        prefix = f"{root}/mcp_server/"
        for n in names:
            if not n.startswith(prefix) or n.endswith("/"):
                continue
            rel = n[len(prefix):]              # 相對 mcp_server/ 的路徑
            if rel in PRESERVE:
                continue
            if rel.startswith(("cache/", "tests/__pycache__", "__pycache__")):
                continue
            dest = PACKAGE_DIR / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(n) as src, tempfile.NamedTemporaryFile(
                dir=str(dest.parent), delete=False, suffix=".tmp"
            ) as tmp:
                shutil.copyfileobj(src, tmp)
                tmp_name = tmp.name
            os.replace(tmp_name, str(dest))
            updated += 1
    return updated


def check_and_update(force: bool = False) -> dict:
    """檢查 GitHub 並更新程式碼。回 {"updated": bool, "reason": str}。"""
    should, reason = should_check(force)
    if not should:
        logger.info("自我更新：%s，略過", reason)
        return {"updated": False, "reason": reason}
    logger.info("自我更新：%s，檢查 %s", reason, _repo())

    state = _load_state()
    now = datetime.now(timezone.utc).isoformat()
    with httpx.Client(timeout=TIMEOUT, follow_redirects=True, verify=True) as client:
        latest_sha = _fetch_latest_sha(client)
        if state.get("sha") == latest_sha:
            state["last_check"] = now
            _save_state(state)
            logger.info("自我更新：已是最新版（%s）", latest_sha[:10])
            return {"updated": False, "reason": f"已是最新版 {latest_sha[:10]}"}
        zip_bytes = _download_repo_zip(client)

    updated = _apply_zip(zip_bytes)
    _save_state({"sha": latest_sha, "last_check": now, "updated_at": now})
    logger.info(
        "自我更新：已更新 %d 個檔案至 %s，下次重啟生效", updated, latest_sha[:10]
    )
    return {"updated": True, "reason": f"更新至 {latest_sha[:10]}（{updated} 檔）"}


def maybe_self_update() -> None:
    """供 server.py 啟動背景工作呼叫：失敗只記警告。"""
    try:
        check_and_update(force=False)
    except Exception as e:
        logger.warning("自我更新失敗（不影響使用）: %s", e)


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="忽略每日間隔強制檢查")
    args = ap.parse_args()
    result = check_and_update(force=args.force)
    print(("已更新：" if result["updated"] else "未更新：") + result["reason"])
