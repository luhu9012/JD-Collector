#!/usr/bin/env python3
"""
JD Collector — PyWebView 主程序 v2.0
"""

import webview
import subprocess
import threading
import queue
import json
import time
import traceback
from pathlib import Path

CONFIG_PATH = Path.home() / ".jd_collector_config.json"

DEFAULT_CONFIG = {
    "api_key": "",
    "api_base": "https://api.deepseek.com/v1",
    "model": "deepseek-chat",
    "save_dir": str(Path.home() / "Desktop" / "jd_collector_output"),
    "export_formats": ["md", "jsonl", "csv"],
    "chrome_port": 9222,
    "chrome_path": "",
    "target_positions": [
        "售前工程师", "解决方案工程师", "技术支持工程师",
        "售后工程师", "技术服务工程师", "应用工程师",
    ],
}

log_queue = queue.Queue()
_collector = None

# ── Chrome 路径检测 ───────────────────────────────────

CHROME_PATHS_MAC = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
]

CHROME_PATHS_WIN = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]

def find_chrome() -> str:
    import platform
    paths = CHROME_PATHS_MAC if platform.system() == "Darwin" else CHROME_PATHS_WIN
    for p in paths:
        if Path(p).exists():
            return p
    return ""

def check_chrome_connection(port: int = 9222) -> dict:
    import socket
    result = {"connected": False, "error": None}
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        r = s.connect_ex(('127.0.0.1', port))
        s.close()
        if r == 0:
            result["connected"] = True
        else:
            result["error"] = f"端口 {port} 未开放"
    except Exception as e:
        result["error"] = str(e)
    return result

def launch_chrome_proc(chrome_path: str, port: int = 9222) -> dict:
    """关闭已有 Chrome，用调试模式重启"""
    import platform
    result = {"ok": False, "error": None}

    # 已经可用则直接返回
    if check_chrome_connection(port)["connected"]:
        result["ok"] = True
        return result

    # 关闭已有进程
    try:
        if platform.system() == "Darwin":
            subprocess.run(["pkill", "-a", "-i", "Google Chrome"], capture_output=True)
            subprocess.run(["pkill", "-a", "-i", "Chromium"], capture_output=True)
        else:
            subprocess.run(["taskkill", "/F", "/IM", "chrome.exe"], capture_output=True)
        time.sleep(2)
    except Exception:
        pass

    # 调试模式启动
    user_data_dir = str(Path.home() / ".jd_collector_chrome")
    try:
        subprocess.Popen(
            [chrome_path,
             f"--remote-debugging-port={port}",
             f"--user-data-dir={user_data_dir}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        result["error"] = f"Chrome 启动失败：{e}"
        return result

    # 等待端口就绪，最多10秒
    for _ in range(20):
        time.sleep(0.5)
        if check_chrome_connection(port)["connected"]:
            result["ok"] = True
            return result

    result["error"] = f"Chrome 启动超时，端口 {port} 未响应"
    return result

# ── 配置读写 ──────────────────────────────────────────

def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            return {**DEFAULT_CONFIG, **data}
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()

def save_config(cfg: dict):
    CONFIG_PATH.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

def _push(text, tag="info"):
    log_queue.put({"type": "log", "text": text, "tag": tag})

# ── PyWebView API ─────────────────────────────────────

class Api:

    def check_environment(self):
        cfg = load_config()
        port = cfg.get("chrome_port", 9222)
        chrome_result = check_chrome_connection(port)
        return {
            "chrome_ok":    chrome_result["connected"],
            "chrome_error": chrome_result["error"],
            "port":         port,
        }

    def get_chrome_path(self):
        cfg = load_config()
        saved = cfg.get("chrome_path", "")
        if saved and Path(saved).exists():
            return {"path": saved}
        return {"path": find_chrome()}

    def launch_chrome(self):
        cfg = load_config()
        port = cfg.get("chrome_port", 9222)
        chrome_path = cfg.get("chrome_path", "").strip() or find_chrome()
        if not chrome_path:
            return {"ok": False, "error": "未找到 Chrome，请在设置页手动填写路径"}
        if not Path(chrome_path).exists():
            return {"ok": False, "error": f"路径不存在：{chrome_path}"}
        return launch_chrome_proc(chrome_path, port)

    def load_config(self):
        return load_config()

    def save_config(self, cfg):
        current = load_config()
        current.update(cfg)
        save_config(current)
        return {"ok": True}

    def get_logs(self):
        logs = []
        while not log_queue.empty():
            try:
                logs.append(log_queue.get_nowait())
            except queue.Empty:
                break
        return logs

    def open_save_dir(self):
        cfg = load_config()
        save_dir = cfg.get("save_dir", "")
        if save_dir:
            Path(save_dir).mkdir(parents=True, exist_ok=True)
            subprocess.run(["open", save_dir])
        return {"ok": True}

    def browse_dir(self):
        script = '''
        tell application "System Events" to activate
        set chosen to choose folder with prompt "选择目录"
        POSIX path of chosen
        '''
        try:
            r = subprocess.run(["osascript", "-e", script],
                               capture_output=True, text=True, timeout=30)
            path = r.stdout.strip()
            if path:
                return {"path": path}
        except Exception:
            pass
        return {"path": ""}

    def browse_file(self):
        """选择文件（用于 Chrome 路径）"""
        script = '''
        tell application "System Events" to activate
        set chosen to choose file with prompt "选择 Chrome 可执行文件"
        POSIX path of chosen
        '''
        try:
            r = subprocess.run(["osascript", "-e", script],
                               capture_output=True, text=True, timeout=30)
            path = r.stdout.strip()
            if path:
                return {"path": path}
        except Exception:
            pass
        return {"path": ""}

    def export_log(self, content: str):
        import datetime
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        cfg = load_config()
        save_dir = Path(cfg.get("save_dir", str(Path.home() / "Desktop" / "jd_collector_output")))
        save_dir.mkdir(parents=True, exist_ok=True)
        log_path = save_dir / f"jd_log_{ts}.txt"
        log_path.write_text(content, encoding="utf-8")
        subprocess.run(["open", "-R", str(log_path)])
        return {"ok": True, "path": str(log_path)}

    def start_collect(self, params):
        global _collector
        cfg = load_config()

        def _run():
            try:
                _push("─" * 48)
                _push(f"▶ 开始采集")
                _push(f"  搜索词：{params.get('query')}")
                _push(f"  城市：{params.get('city_name')}  上限：{params.get('limit')}条")
                _push(f"  模式：{'详情' if params.get('collect_mode')=='detail' else '简便'}")
                _push("─" * 48)

                import sys, os
                base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
                if base not in sys.path:
                    sys.path.insert(0, base)

                from core import Collector
                _collector = Collector(cfg, log_queue)
                _collector.run(params)

            except Exception as e:
                _push(f"❌ 启动异常：{e}", "error")
                _push(traceback.format_exc(), "error")
                log_queue.put({"type": "done", "success": 0, "failed": 0, "skipped": 0})

        threading.Thread(target=_run, daemon=True).start()
        return {"ok": True}

    def stop_collect(self):
        global _collector
        if _collector:
            _collector.stop()
        _push("🛑 已停止", "warn")
        return {"ok": True}

    def get_history(self):
        cfg = load_config()
        save_dir = Path(cfg.get("save_dir", ""))
        result = {"total": 0, "last_date": "—", "last_job": "—"}
        try:
            jsonl = save_dir / "jd_data.jsonl"
            if jsonl.exists():
                lines = [l for l in jsonl.read_text(encoding='utf-8').splitlines() if l.strip()]
                result["total"] = len(lines)
                if lines:
                    last = json.loads(lines[-1])
                    result["last_date"] = last.get("date", "—")
                    result["last_job"]  = f"{last.get('job_name','—')} @ {last.get('company','—')}"
        except Exception:
            pass
        return result

# ── 入口 ─────────────────────────────────────────────

def main():
    api = Api()
    window = webview.create_window(
        title="JD Collector",
        url="ui/index.html",
        js_api=api,
        width=960,
        height=680,
        min_size=(800, 560),
        resizable=True,
    )
    webview.start(debug=False, gui='cocoa')

if __name__ == "__main__":
    main()
