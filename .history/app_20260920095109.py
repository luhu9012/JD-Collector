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
from typing import Optional

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
        "工业视觉上位机", "视觉工程师", "上位机视觉",
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
    r"C:\Program Files\Google\Chrome Beta\Application\chrome.exe",
    r"C:\Program Files\Google\Chrome SxS\Application\chrome.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
]

def resolve_chrome_executable(path: str) -> str:
    """把 Chrome.app 目录/文件夹路径转换成实际可执行文件路径"""
    if not path:
        return ""
    p = str(path).strip().strip('"')
    if not p:
        return ""

    # 直接就是可执行文件
    if Path(p).is_file() and Path(p).exists():
        return p

    # 传入的是 .app 包目录
    app_candidates = []
    if p.endswith(".app"):
        app_candidates.append(Path(p) / "Contents" / "MacOS" / "Google Chrome")
        app_candidates.append(Path(p) / "Contents" / "MacOS" / "Chromium")
        app_candidates.append(Path(p) / "Contents" / "MacOS" / "Google Chrome Canary")
    elif p.endswith(".app/") or p.endswith(".app\\"):
        base = p.rstrip("/").rstrip("\\")
        app_candidates.append(Path(base) / "Contents" / "MacOS" / "Google Chrome")
        app_candidates.append(Path(base) / "Contents" / "MacOS" / "Chromium")
        app_candidates.append(Path(base) / "Contents" / "MacOS" / "Google Chrome Canary")

    for candidate in app_candidates:
        if candidate.exists() and candidate.is_file():
            return str(candidate)

    return p


def find_chrome() -> str:
    import os
    import platform
    env_path = os.environ.get("CHROME_PATH", "").strip()
    if env_path:
        resolved = resolve_chrome_executable(env_path)
        if resolved and Path(resolved).exists():
            return resolved

    if platform.system() == "Darwin":
        paths = CHROME_PATHS_MAC
    elif platform.system() == "Windows":
        paths = CHROME_PATHS_WIN
    else:
        paths = []

    for p in paths:
        resolved = resolve_chrome_executable(p)
        if Path(resolved).exists():
            return resolved
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
    # 同步打印到 stdout，方便在 IDE 终端或 Debug Console 查看运行日志
    try:
        print(f"[{tag}] {text}", flush=True)
    except Exception:
        pass

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
        if saved:
            resolved = resolve_chrome_executable(saved)
            if resolved and Path(resolved).exists():
                return {"path": resolved}
        auto = find_chrome()
        return {"path": auto}

    def launch_chrome(self):
        cfg = load_config()
        port = cfg.get("chrome_port", 9222)
        raw_path = cfg.get("chrome_path", "").strip() or find_chrome()
        chrome_path = resolve_chrome_executable(raw_path)
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
                item = log_queue.get_nowait()
                # determine whether to include debug logs (config or env override)
                try:
                    cfg = load_config()
                    show_debug = bool(cfg.get('show_debug', False)) or bool(__import__('os').environ.get('JD_COLLECTOR_SHOW_DEBUG'))
                except Exception:
                    show_debug = bool(__import__('os').environ.get('JD_COLLECTOR_SHOW_DEBUG'))
                if item.get('tag') == 'debug' and not show_debug:
                    continue
                logs.append(item)
            except queue.Empty:
                break
        return logs

    def open_save_dir(self):
        cfg = load_config()
        save_dir = cfg.get("save_dir", "")
        if save_dir:
            Path(save_dir).mkdir(parents=True, exist_ok=True)
            import os
            import platform
            if platform.system() == "Windows":
                os.startfile(save_dir)
            elif platform.system() == "Darwin":
                subprocess.run(["open", save_dir])
            else:
                subprocess.run(["xdg-open", save_dir])
        return {"ok": True}

    def browse_dir(self):
        import platform
        if platform.system() == "Windows":
            try:
                import tkinter as tk
                from tkinter import filedialog
                root = tk.Tk()
                root.withdraw()
                folder = filedialog.askdirectory(title="选择目录")
                root.destroy()
                return {"path": folder} if folder else {"path": ""}
            except Exception:
                pass
            return {"path": ""}

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
        import platform
        if platform.system() == "Windows":
            try:
                import tkinter as tk
                from tkinter import filedialog
                root = tk.Tk()
                root.withdraw()
                file_path = filedialog.askopenfilename(
                    title="选择 Chrome 可执行文件",
                    filetypes=[("可执行文件", "*.exe"), ("所有文件", "*.*")]
                )
                root.destroy()
                return {"path": file_path} if file_path else {"path": ""}
            except Exception:
                pass
            return {"path": ""}

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
        import platform
        if platform.system() == "Windows":
            try:
                import os
                os.startfile(str(log_path))
            except Exception:
                pass
        else:
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

    def get_all_jobs(self):
        """读取全量职位数据，供数据页表格展示"""
        cfg = load_config()
        save_dir = Path(cfg.get("save_dir", ""))
        jobs = []
        try:
            jsonl = save_dir / "jd_data.jsonl"
            if jsonl.exists():
                for line in jsonl.read_text(encoding='utf-8').splitlines():
                    line = line.strip()
                    if line:
                        jobs.append(json.loads(line))
        except Exception:
            pass
        return jobs

    def get_stats(self):
        """统计图表数据：薪资/城市/规模/行业/学历/经验分布"""
        cfg = load_config()
        save_dir = Path(cfg.get("save_dir", ""))
        from collections import Counter
        import re

        salary_buckets = Counter()
        city_counter   = Counter()
        scale_counter  = Counter()
        industry_counter = Counter()
        degree_counter = Counter()
        experience_counter = Counter()

        def parse_salary_mid(s: str) -> Optional[float]:
            """把 '15-20K' / '30K以上' 转为中位数（K）"""
            s = s.replace("·", "").replace(" ", "")
            m = re.search(r'(\d+)-(\d+)K', s, re.I)
            if m:
                return (int(m.group(1)) + int(m.group(2))) / 2
            m = re.search(r'(\d+)K以上', s, re.I)
            if m:
                return int(m.group(1)) * 1.2
            m = re.search(r'(\d+)K以下', s, re.I)
            if m:
                return int(m.group(1)) * 0.8
            return None

        salary_ranges = ["5K以下", "5-10K", "10-15K", "15-20K", "20-30K", "30-50K", "50K以上"]

        def salary_bucket(mid):
            if mid is None: return None
            if mid < 5:  return "5K以下"
            if mid < 10: return "5-10K"
            if mid < 15: return "10-15K"
            if mid < 20: return "15-20K"
            if mid < 30: return "20-30K"
            if mid < 50: return "30-50K"
            return "50K以上"

        try:
            jsonl = save_dir / "jd_data.jsonl"
            if jsonl.exists():
                for line in jsonl.read_text(encoding='utf-8').splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    r = json.loads(line)
                    mid = parse_salary_mid(r.get("salary", ""))
                    bucket = salary_bucket(mid)
                    if bucket:
                        salary_buckets[bucket] += 1
                    if r.get("city"):
                        city_counter[r["city"]] += 1
                    if r.get("scale"):
                        scale_counter[r["scale"]] += 1
                    if r.get("industry"):
                        industry_counter[r["industry"]] += 1
                    if r.get("degree"):
                        degree_counter[r["degree"]] += 1
                    if r.get("experience"):
                        experience_counter[r["experience"]] += 1
        except Exception:
            pass

        def top(counter, n=8):
            return [{"label": k, "value": v}
                    for k, v in counter.most_common(n)]

        return {
            "salary":     [{"label": b, "value": salary_buckets.get(b, 0)} for b in salary_ranges],
            "city":       top(city_counter),
            "scale":      top(scale_counter),
            "industry":   top(industry_counter),
            "degree":     top(degree_counter),
            "experience": top(experience_counter),
        }

    def delete_jobs(self, job_ids: list):
        """按 id 列表批量删除职位（jsonl + csv + md + collected.txt）"""
        cfg = load_config()
        save_dir = Path(cfg.get("save_dir", ""))
        id_set = set(job_ids)
        deleted = 0

        try:
            # 重写 jsonl，过滤掉要删的行，同时收集被删记录的 md_file
            jsonl = save_dir / "jd_data.jsonl"
            kept, removed = [], []
            if jsonl.exists():
                for line in jsonl.read_text(encoding='utf-8').splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    r = json.loads(line)
                    if r.get("id") in id_set:
                        removed.append(r)
                    else:
                        kept.append(line)
                jsonl.write_text("\n".join(kept) + ("\n" if kept else ""), encoding='utf-8')
                deleted = len(removed)

            # 删对应 md 文件
            for r in removed:
                md = save_dir / r.get("md_file", "")
                if md.exists():
                    md.unlink()

            # 重写 collected.txt，移除已删 id
            collected_f = save_dir / "collected.txt"
            if collected_f.exists():
                lines = [l.strip() for l in collected_f.read_text(encoding='utf-8').splitlines() if l.strip()]
                lines = [l for l in lines if l not in id_set]
                collected_f.write_text("\n".join(lines) + "\n", encoding='utf-8')

            # 重写 csv（全量重建）
            import csv
            csv_path = save_dir / "jd_data.csv"
            if csv_path.exists() and kept:
                records = [json.loads(l) for l in kept]
                flat_records = []
                for rec in records:
                    flat = {k: (json.dumps(v, ensure_ascii=False) if isinstance(v, list) else v)
                            for k, v in rec.items()}
                    flat_records.append(flat)
                if flat_records:
                    with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
                        writer = csv.DictWriter(f, fieldnames=list(flat_records[0].keys()))
                        writer.writeheader()
                        writer.writerows(flat_records)
            elif csv_path.exists() and not kept:
                csv_path.unlink()

        except Exception as e:
            return {"ok": False, "error": str(e), "deleted": 0}

        return {"ok": True, "deleted": deleted}

    def get_skill_analysis(self):
        """聚焦机器视觉岗位，统计技能热度和权重，过滤非视觉岗位"""
        cfg = load_config()
        save_dir = Path(cfg.get("save_dir", ""))
        skill_counter = {}
        job_counter = {}
        kept_jobs = []
        filtered_out = 0

        def norm_skill(s: str) -> str:
            if not s:
                return ""
            s = s.strip().lower()
            s = s.replace("&", "and").replace("/", " ")
            s = s.replace("（", "(").replace("）", ")")
            s = s.replace("，", " ").replace("。", " ")
            s = s.replace("；", " ").replace(";", " ")
            s = s.replace("、", " ")
            s = s.replace("-", " ")
            s = " ".join(s.split())
            return s

        def tag_strength(t: str) -> int:
            t = t.lower()
            strong = [
                "深度学习", "机器视觉", "计算机视觉", "图像处理", "opencv", "halcon",
                "c++", "python", "视觉算法", "视觉检测", "视觉定位", "视觉导航",
                "工业视觉", "图像识别", "目标检测", "语义分割", "相机标定",
                "三维重建", "特征检测", "摄像头", "算法优化", "机器学习"
            ]
            if any(k in t for k in strong):
                return 3
            if any(k in t for k in ["视觉", "图像", "算法", "检测", "识别", "定位", "导航"]):
                return 2
            return 1

        def extract_skill_tokens(job: dict):
            tokens = []
            for v in job.get("skills", []) or []:
                tokens.append(v)
            text = " ".join([
                job.get("job_name", ""),
                job.get("company", ""),
                job.get("industry", ""),
                job.get("description", ""),
                " ".join(job.get("skills", []) or []),
            ])
            tokens.extend(re.findall(r"[A-Za-z][A-Za-z0-9+.#/ -]{2,}", text))
            tokens.extend(re.findall(r"[\u4e00-\u9fff]{2,}", text))
            return tokens

        def job_is_machine_vision(job: dict) -> bool:
            text = " ".join([
                job.get("job_name", ""),
                job.get("company", ""),
                job.get("industry", ""),
                job.get("description", ""),
                " ".join(job.get("skills", []) or []),
            ]).lower()
            if not text:
                return False

            positive = [
                "机器视觉", "计算机视觉", "工业视觉", "视觉算法", "图像处理",
                "图像识别", "opencv", "halcon", "视觉检测", "视觉定位", "视觉导航",
                "目标检测", "语义分割", "3d视觉", "相机标定", "工业相机", "图像分析",
                "深度学习", "计算机视觉算法", "视觉开发", "视觉工程师"
            ]
            negative = [
                "平面设计", "平面视觉", "海报设计", "网页视觉", "UI设计", "交互设计",
                "视觉设计师", "广告视觉", "包装设计", "原画设计", "插画", "视频剪辑",
                "平面视觉设计师", "视觉设计", "设计师"
            ]

            positive_hit = any(p in text for p in positive)
            negative_hit = any(n in text for n in negative)
            if negative_hit and not positive_hit:
                return False
            return positive_hit or "视觉" in text and any(k in text for k in ["算法", "检测", "定位", "识别", "图像", "相机"])

        jsonl = save_dir / "jd_data.jsonl"
        if jsonl.exists():
            for line in jsonl.read_text(encoding='utf-8', errors='replace').splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    job = json.loads(line)
                except Exception:
                    continue
                if not job_is_machine_vision(job):
                    filtered_out += 1
                    continue
                kept_jobs.append(job)
                for token in extract_skill_tokens(job):
                    t = norm_skill(token)
                    if not t:
                        continue
                    if any(w in t for w in ["岗位", "职责", "要求", "公司", "工资", "经验", "学历", "岗位职责"]):
                        continue
                    if t in ["视觉", "图像", "算法", "工程师", "开发", "岗位", "公司", "团队"]:
                        continue
                    skill_counter[t] = skill_counter.get(t, 0) + tag_strength(t)
                job_name = job.get("job_name", "")
                if job_name:
                    job_counter[job_name] = job_counter.get(job_name, 0) + 1

        top_skills = []
        for name, weight in sorted(skill_counter.items(), key=lambda kv: (-kv[1], kv[0]))[:20]:
            if name in ["视觉", "图像", "算法", "工程师", "开发", "岗位", "公司", "团队"]:
                continue
            top_skills.append({
                "name": name,
                "weight": weight,
                "count": max(1, min(999, weight))
            })

        top_jobs = [{"name": name, "count": count} for name, count in sorted(job_counter.items(), key=lambda kv: (-kv[1], kv[0]))[:10]]

        return {
            "jobs_kept": len(kept_jobs),
            "filtered_out": filtered_out,
            "skills": top_skills,
            "job_titles": top_jobs,
            "summary": {
                "focus": "机器视觉 / 工业视觉 / 图像处理 / 视觉算法",
                "message": "已剔除明显不相关岗位（如平面视觉设计师）并保留与机器视觉强相关的 JD 数据。"
            }
        }

    def analyze_resume(self, resume_text: str):
        """基于 JD 技能热度做规则化简历匹配；若配置了 AI Key，可在本地 heuristics 基础上再补充建议。"""
        if not resume_text or not str(resume_text).strip():
            return {"ok": False, "error": "简历内容为空"}

        skill_analysis = self.get_skill_analysis()
        skills = skill_analysis.get("skills", [])
        jd_skill_map = {item["name"].lower(): item["weight"] for item in skills}

        def norm_term(s: str) -> str:
            if not s:
                return ""
            s = s.lower().strip().replace("&", "and")
            s = s.replace("/", " ").replace("-", " ")
            s = re.sub(r"[^a-z0-9\u4e00-\u9fff\s]+", " ", s)
            return " ".join(s.split())

        def extract_resume_skills(text: str):
            out = set()
            norm = norm_term(text)
            for term in jd_skill_map.keys():
                if term in norm:
                    out.add(term)
            # 基础关键词兜底
            for token in [
                "opencv", "halcon", "python", "c++", "图像处理", "深度学习",
                "机器视觉", "计算机视觉", "目标检测", "语义分割", "视觉算法",
                "工业视觉", "相机标定", "定位", "检测", "识别", "目标跟踪",
                "pytorch", "tensorflow", "numpy", "opencv" ]:
                if token in norm:
                    out.add(token)
            return sorted(out)

        resume_skills = extract_resume_skills(resume_text)
        matched = []
        for item in skills:
            skill_name = item["name"]
            score = 0
            if skill_name.lower() in resume_skills:
                score = min(100, int(item["weight"] * 10 + 20))
            elif any(k in skill_name.lower() for k in ["python", "c++", "opencv", "视觉", "图像", "检测", "识别"]):
                score = 5
            matched.append({
                "name": skill_name,
                "weight": item["weight"],
                "match_score": score,
            })

        matched = sorted(matched, key=lambda x: (-x["match_score"], -x["weight"]))[:12]
        gap_skills = [m["name"] for m in matched if m["match_score"] < 35][:6]

        best_roles = []
        resume_tokens = set(norm_term(resume_text).split())
        for item in skills:
            skill_name = item["name"]
            overlap = 0
            for part in skill_name.split():
                if part in resume_tokens:
                    overlap += 1
            if overlap > 0 or item["weight"] >= 15:
                best_roles.append({
                    "name": skill_name,
                    "priority": max(20, min(99, int(item["weight"] * 5 + overlap * 8))),
                })
        best_roles = sorted(best_roles, key=lambda x: -x["priority"])[:8]

        suggestions = []
        if gap_skills:
            suggestions.append(f"优先补强：{', '.join(gap_skills)}")
        if not any("python" in s.lower() for s in resume_skills):
            suggestions.append("补充 Python / C++ 相关项目经验，尤其是 OpenCV、图像处理或视觉算法开发。")
        if not any("深度学习" in s or "目标检测" in s for s in resume_skills):
            suggestions.append("强调目标检测、语义分割、深度学习模型部署等视觉任务经验。")
        if not suggestions:
            suggestions.append("简历与岗位技能方向匹配度较高，建议继续补足项目量化结果和关键指标。")

        return {
            "ok": True,
            "resume_skills": resume_skills,
            "matched_skills": matched,
            "best_roles": best_roles,
            "gap_skills": gap_skills,
            "suggestions": suggestions,
            "summary": {
                "jobs_kept": skill_analysis.get("jobs_kept", 0),
                "filtered_out": skill_analysis.get("filtered_out", 0)
            }
        }

    def get_resume_match(self, resume_text: str):
        """兼容前端调用：返回简历匹配结果"""
        return self.analyze_resume(resume_text)

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
