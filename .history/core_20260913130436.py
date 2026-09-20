#!/usr/bin/env python3
"""
core.py — 采集核心逻辑 v2.0
基于 DrissionPage，替换 AppleScript + Safari 方案
支持：职位搜索 / 公司搜索，简便模式 / 详情模式
"""

import time, re, json, csv, traceback, random
from pathlib import Path
from datetime import datetime
from queue import Queue

DEFAULT_TARGET_POSITIONS = [
    "售前工程师", "解决方案工程师", "技术支持工程师",
    "售后工程师", "技术服务工程师", "应用工程师",
]

# ── DrissionPage 初始化 ───────────────────────────────

def get_page(port: int = 9222):
    """接管已登录的 Chrome"""
    from DrissionPage import ChromiumPage, ChromiumOptions
    co = ChromiumOptions().set_local_port(port)
    return ChromiumPage(co)


# ── 字段解析 ──────────────────────────────────────────

def parse_job_item(item: dict) -> dict:
    """从 joblist.json 单条记录提取字段"""
    return {
        "job_id":       item.get("encryptJobId", ""),
        "security_id":  item.get("securityId", ""),
        "job_name":     item.get("jobName", ""),
        "salary":       item.get("salaryDesc", ""),
        "experience":   item.get("jobExperience", ""),
        "degree":       item.get("jobDegree", ""),
        "skills":       item.get("skills", []),
        "welfare":      item.get("welfareList", []),
        "city":         item.get("cityName", ""),
        "district":     item.get("areaDistrict", ""),
        "biz_district": item.get("businessDistrict", ""),
        "company_id":   item.get("encryptBrandId", ""),
        "company":      item.get("brandName", ""),
        "industry":     item.get("brandIndustry", ""),
        "stage":        item.get("brandStageName", ""),
        "scale":        item.get("brandScaleName", ""),
        "boss_id":      item.get("encryptBossId", ""),
        "boss_name":    item.get("bossName", ""),
        "boss_title":   item.get("bossTitle", ""),
        "boss_online":  item.get("bossOnline", False),
        # 详情模式补充字段（默认空）
        "address":        "",
        "description":    "",
        "company_intro":  "",
        "company_labels": [],
        "boss_active":    "",
        "source_url":     "",
    }


def parse_detail(body: dict) -> dict:
    """从 detail.json 提取补充字段（覆盖列表页可能缺失的字段）"""
    zp         = body.get("zpData", {})
    job_info   = zp.get("jobInfo", {})
    brand_info = zp.get("brandComInfo", {})
    boss_info  = zp.get("bossInfo", {})

    result = {}

    # ── 岗位信息 ────────────────────────────────────────
    if job_info.get("jobName"):
        result["job_name"]   = job_info["jobName"]
    if job_info.get("salaryDesc"):
        result["salary"]     = job_info["salaryDesc"]
    if job_info.get("experienceName"):
        result["experience"] = job_info["experienceName"]
    if job_info.get("degreeName"):
        result["degree"]     = job_info["degreeName"]
    if job_info.get("locationName"):
        result["city"]       = job_info["locationName"]
    if job_info.get("address"):
        result["address"]    = job_info["address"]
    if job_info.get("postDescription"):
        result["description"] = job_info["postDescription"]
    if job_info.get("showSkills"):
        result["skills"]     = job_info["showSkills"]

    # ── 公司信息 ────────────────────────────────────────
    if brand_info.get("brandName"):
        result["company"]       = brand_info["brandName"]
    if brand_info.get("stageName"):
        result["stage"]         = brand_info["stageName"]
    if brand_info.get("scaleName"):
        result["scale"]         = brand_info["scaleName"]
    if brand_info.get("industryName"):
        result["industry"]      = brand_info["industryName"]
    if brand_info.get("introduce"):
        result["company_intro"] = brand_info["introduce"]
    if brand_info.get("labels"):
        result["company_labels"]= brand_info["labels"]

    # ── Boss 信息 ────────────────────────────────────────
    if boss_info.get("name"):
        result["boss_name"]   = boss_info["name"]
    if boss_info.get("title"):
        result["boss_title"]  = boss_info["title"]
    if boss_info.get("activeTimeDesc"):
        result["boss_active"] = boss_info["activeTimeDesc"]

    return result


def parse_detail_from_html(page) -> dict:
    """从右侧详情面板 HTML 提取字段（用于第一张默认高亮卡片）

    可取字段：
      job_name / salary / city / experience / degree /
      skills / description / address /
      boss_name / boss_title / company / boss_active
    取不到：scale / stage / industry / company_intro / company_labels
    """
    def js_text(sel: str) -> str:
        r = page.run_js(
            f"var e=document.querySelector('{sel}');"
            f"return e ? e.innerText : '';"
        )
        return (r or '').strip()

    def js_list(sel: str) -> list:
        r = page.run_js(
            f"var els=document.querySelectorAll('{sel}');"
            f"return Array.from(els).map(e=>e.innerText.trim()).filter(Boolean);"
        )
        return r or []

    result = {}

    # 职位名 / 薪资
    v = js_text('.job-detail-box .job-name')
    if v: result['job_name'] = v

    v = js_text('.job-detail-box .job-salary')
    if v: result['salary'] = v

    # tag-list 限定在 .job-detail-box 内，前三项依次是城市/经验/学历
    tags = js_list('.job-detail-box .tag-list li')
    if len(tags) >= 1: result['city']       = tags[0]
    if len(tags) >= 2: result['experience'] = tags[1]
    if len(tags) >= 3: result['degree']     = tags[2]

    # 技能标签
    skills = js_list('.job-detail-box .job-label-list li')
    if skills: result['skills'] = skills

    # 岗位描述（innerText 自动过滤反爬隐藏 span）
    v = js_text('.job-detail-box .desc')
    if v: result['description'] = v

    # 地址
    v = js_text('.job-address-desc')
    if v: result['address'] = v

    # Boss 姓名
    v = js_text('.job-boss-info .name')
    if v: result['boss_name'] = v.strip()

    # ".boss-info-attr" 格式："公司名 · 职位"，拆分得到 company 和 boss_title
    boss_attr = js_text('.boss-info-attr')
    if boss_attr and '·' in boss_attr:
        parts = [p.strip() for p in boss_attr.split('·', 1)]
        if parts[0]: result['company']    = parts[0]
        if parts[1]: result['boss_title'] = parts[1]
    elif boss_attr:
        result['boss_title'] = boss_attr

    # boss 活跃（异步加载，通常为空，尽量取一次）
    v = js_text('.boss-active-time')
    if v: result['boss_active'] = v

    return result


def parse_company_card_html(card_el) -> dict:
    """从公司页 HTML 卡片元素提取职位基础信息"""
    name_el   = card_el.ele('css:.job-name')
    salary_el = card_el.ele('css:.job-salary')
    tags      = card_el.eles('css:.tag-list li')
    boss_el   = card_el.ele('css:.boss-name')
    link_el   = card_el.ele('css:.job-name')

    tag_texts = [t.text.strip() for t in tags if t.text.strip()]
    experience = tag_texts[0] if len(tag_texts) > 0 else ""
    degree     = tag_texts[1] if len(tag_texts) > 1 else ""

    href = link_el.attr('href') if link_el else ""
    job_id = ""
    if href:
        m = re.search(r'/job_detail/([a-zA-Z0-9]+)\.html', href)
        if m:
            job_id = m.group(1)

    return {
        "job_id":       job_id,
        "security_id":  "",   # 公司页HTML没有securityId，点击后从detail拿
        "job_name":     name_el.text.strip() if name_el else "",
        "salary":       salary_el.text.strip() if salary_el else "",
        "experience":   experience,
        "degree":       degree,
        "skills":       [],
        "welfare":      [],
        "city":         "",
        "district":     "",
        "biz_district": "",
        "company_id":   "",
        "company":      "",   # 由调用方传入
        "industry":     "",
        "stage":        "",
        "scale":        "",
        "boss_name":    boss_el.text.strip() if boss_el else "",
        "boss_title":   "",
        "boss_online":  False,
        "address":        "",
        "description":    "",
        "company_intro":  "",
        "company_labels": [],
        "boss_active":    "",
        "source_url":     f"https://www.zhipin.com{href}" if href else "",
    }


# ── 判重 ──────────────────────────────────────────────

def get_saved_ids(save_dir: Path) -> set:
    f = save_dir / "collected.txt"
    if not f.exists():
        return set()
    return set(l.strip() for l in f.read_text(encoding='utf-8').splitlines() if l.strip())


def mark_saved(job_id: str, save_dir: Path):
    if job_id:
        with open(save_dir / "collected.txt", 'a', encoding='utf-8') as f:
            f.write(job_id + '\n')


# ── Collector ─────────────────────────────────────────

class Collector:
    def __init__(self, cfg: dict, log_queue: Queue):
        self.cfg = cfg
        self.q = log_queue
        self.stop_flag = False
        self.save_dir = Path(cfg.get('save_dir', str(Path.home() / 'Desktop' / 'jd_collector_output')))
        self.save_dir.mkdir(parents=True, exist_ok=True)
        self.log(f"📁 保存目录：{self.save_dir}")

        self.export_formats = cfg.get('export_formats', ['md', 'jsonl', 'csv'])
        self.target_positions = cfg.get('target_positions', DEFAULT_TARGET_POSITIONS)
        self.port = cfg.get('chrome_port', 9222)

        # AI 可选
        api_key = cfg.get('api_key', '').strip()
        if api_key:
            from openai import OpenAI
            self.ai = OpenAI(
                api_key=api_key,
                base_url=cfg.get('api_base', 'https://api.deepseek.com/v1'),
            )
            self.model = cfg.get('model', 'deepseek-chat')
            self.log(f"🤖 AI模型：{self.model}")
        else:
            self.ai = None
            self.model = None
            self.log("⚠️  未配置 API Key，公司名模式AI过滤不可用", "warn")

        self.log(f"💾 导出格式：{', '.join(self.export_formats)}")

    def log(self, text: str, tag: str = 'info'):
        self.q.put({"type": "log", "text": text, "tag": tag})

    def progress(self, current: int, total: int):
        self.q.put({"type": "progress", "current": current, "total": total})

    def done(self, success: int, failed: int, skipped: int):
        self.q.put({"type": "done", "success": success, "failed": failed, "skipped": skipped})

    def stop(self):
        self.stop_flag = True

    # ── URL 构建 ─────────────────────────────────────

    def build_search_url(self, params: dict) -> str:
        url = (f"https://www.zhipin.com/web/geek/jobs"
               f"?query={params.get('query','')}"
               f"&city={params.get('city','100010000')}")
        if params.get('industries'):
            url += f"&industry={','.join(params['industries'])}"
        if params.get('salary'):
            url += f"&salary={params['salary']}"
        if params.get('experience'):
            url += f"&experience={params['experience']}"
        if params.get('degree'):
            url += f"&degree={params['degree']}"
        if params.get('scale'):
            url += f"&scale={params['scale']}"
        if params.get('job_type'):
            url += f"&jobType={params['job_type']}"
        return url

    # ── AI 过滤（公司名模式）────────────────────────

    def ai_filter(self, jobs: list) -> list:
        if not self.ai:
            self.log("⚠️  无API Key，跳过AI过滤，返回全部职位", "warn")
            return jobs
        names = [f"{i+1}. {j['job_name']}" for i, j in enumerate(jobs)]
        self.log(f"   发送 {len(jobs)} 个职位给AI过滤...")
        try:
            resp = self.ai.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": f"""以下是职位名称列表，目标岗位类型：{', '.join(self.target_positions)}

{chr(10).join(names)}

返回符合目标类型的序号列表，格式：[1,3,5]，只返回JSON数组。"""}],
                temperature=0.1,
            )
            raw = resp.choices[0].message.content.strip()
            raw = re.sub(r'^```json?\s*', '', raw)
            raw = re.sub(r'\s*```$', '', raw)
            indices = json.loads(raw)
            filtered = [jobs[i-1] for i in indices if 1 <= i <= len(jobs)]
            self.log(f"   AI过滤：{len(jobs)} → {len(filtered)} 个符合", "success")
            return filtered
        except Exception as e:
            self.log(f"   AI过滤失败：{e}，返回全部", "warn")
            return jobs

    # ── 保存记录 ────────────────────────────────────

    def save_record(self, data: dict) -> str:
        date_str = datetime.now().strftime("%Y%m%d")
        company  = re.sub(r'[\\/:*?"<>|]', '', data.get('company', '未知'))
        job_name = re.sub(r'[\\/:*?"<>|]', '', data.get('job_name', '未知'))
        filename = f"{date_str}-{company}-{job_name}"

        record = {
            "id":             data.get("job_id", ""),
            "date":           datetime.now().strftime("%Y-%m-%d"),
            "job_name":       data.get("job_name", ""),
            "company":        data.get("company", ""),
            "salary":         data.get("salary", ""),
            "city":           data.get("city", ""),
            "district":       data.get("district", ""),
            "experience":     data.get("experience", ""),
            "degree":         data.get("degree", ""),
            "stage":          data.get("stage", ""),
            "scale":          data.get("scale", ""),
            "industry":       data.get("industry", ""),
            "skills":         data.get("skills", []),
            "welfare":        data.get("welfare", []),
            "boss_name":      data.get("boss_name", ""),
            "boss_title":     data.get("boss_title", ""),
            "boss_active":    data.get("boss_active", ""),
            "address":        data.get("address", ""),
            "description":    data.get("description", ""),
            "company_intro":  data.get("company_intro", ""),
            "company_labels": data.get("company_labels", []),
            "source_url":     data.get("source_url", ""),
            "md_file":        filename + ".md",
        }

        if 'md' in self.export_formats:
            desc = data.get('description', '未获取到（简便模式）')
            md = f"""# {data.get('job_name')} - {data.get('company')}

采集时间：{datetime.now().strftime("%Y-%m-%d %H:%M")}
来源：BOSS直聘
链接：{data.get('source_url', '')}

## 基本信息
| 项目 | 内容 |
|------|------|
| 薪资 | {data.get('salary','')} |
| 城市 | {data.get('city','')} {data.get('district','')} |
| 经验 | {data.get('experience','')} |
| 学历 | {data.get('degree','')} |
| 公司规模 | {data.get('scale','')} |
| 融资阶段 | {data.get('stage','')} |
| 行业 | {data.get('industry','')} |
| 地址 | {data.get('address','')} |

## 技能标签
{', '.join(data.get('skills', [])) or '—'}

## 福利待遇
{', '.join(data.get('welfare', [])) or '—'}

## 岗位描述
{desc}

## 公司介绍
{data.get('company_intro', '—')}

## 招聘者
{data.get('boss_name','')} / {data.get('boss_title','')}（{data.get('boss_active','')}）

---
*由 JD Collector 自动采集*
"""
            (self.save_dir / (filename + ".md")).write_text(md, encoding='utf-8')

        if 'jsonl' in self.export_formats:
            with open(self.save_dir / "jd_data.jsonl", 'a', encoding='utf-8') as f:
                f.write(json.dumps(record, ensure_ascii=False) + '\n')

        if 'csv' in self.export_formats:
            csv_path = self.save_dir / "jd_data.csv"
            write_header = not csv_path.exists()
            flat = {k: (json.dumps(v, ensure_ascii=False) if isinstance(v, list) else v)
                    for k, v in record.items()}
            with open(csv_path, 'a', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=list(flat.keys()))
                if write_header:
                    writer.writeheader()
                writer.writerow(flat)

        return filename

    # ── 职位搜索 - 简便模式 ──────────────────────────

    def collect_search_fast(self, page, params: dict, limit: int) -> tuple:
        success, failed, skipped = 0, 0, 0
        saved_ids = get_saved_ids(self.save_dir)
        collected_jobs = []

        url = self.build_search_url(params)
        self.log(f"🌐 打开搜索页：{url}")
        patterns = [
            'joblist.json',
            'search/joblist.json',
            'zpgeek/search/joblist.json',
            'wapi/zpgeek/search/joblist.json'
        ]
        # start listeners for all candidate patterns before navigation
        for p in patterns:
            try:
                page.listen.start(p)
            except Exception:
                pass
        page.get(url)
        self.log("⏳ 等待页面加载...")

        scroll_count = 0
        while len(collected_jobs) < limit and not self.stop_flag:
            res, page = self._safe_listen_wait(page, patterns, url, timeout=12)
            if not res:
                self.log("   等待超时，尝试滚动触发...", "warn")
                page.scroll.down(500)
                scroll_count += 1
                if scroll_count > 3:
                    break
                continue

            body = res.response.body
            if isinstance(body, str):
                body = json.loads(body)

            job_list = body.get('zpData', {}).get('jobList', [])
            has_more = body.get('zpData', {}).get('hasMore', False)
            res_count = body.get('zpData', {}).get('resCount', 0)

            if scroll_count == 0:
                self.log(f"✅ 搜索结果：共 {res_count} 个职位")
            self.log(f"   本批获取 {len(job_list)} 条，已累计 {len(collected_jobs)} 条")

            for item in job_list:
                if len(collected_jobs) >= limit:
                    break
                job = parse_job_item(item)
                job['source_url'] = f"https://www.zhipin.com/job_detail/{job['job_id']}.html"
                if job['job_id'] and job['job_id'] in saved_ids:
                    skipped += 1
                    continue
                collected_jobs.append(job)

            if not has_more or len(collected_jobs) >= limit:
                break

            page.scroll.down(600)
            time.sleep(random.uniform(1.0, 2.0))
            scroll_count += 1

        try:
            page.listen.stop()
        except Exception:
            pass

        # 公司名模式：AI过滤
        if params.get('search_type') == 'company' and collected_jobs:
            self.log("\n🤖 AI过滤目标岗位...")
            collected_jobs = self.ai_filter(collected_jobs)

        self.progress(0, len(collected_jobs))
        for i, job in enumerate(collected_jobs):
            if self.stop_flag:
                break
            try:
                filename = self.save_record(job)
                if job['job_id']:
                    mark_saved(job['job_id'], self.save_dir)
                self.log(f"   ✅ {job['job_name']} | {job['company']} | {job['salary']}", "success")
                success += 1
                self.progress(success, len(collected_jobs))
            except Exception as e:
                self.log(f"   ❌ 保存失败：{e}", "error")
                failed += 1

        return success, failed, skipped

    # ── 职位搜索 - 详情模式 ──────────────────────────

    def collect_search_detail(self, page, params: dict, limit: int) -> tuple:
        success, failed, skipped = 0, 0, 0
        saved_ids = get_saved_ids(self.save_dir)
        collected_jobs = []

        url = self.build_search_url(params)
        self.log(f"🌐 打开搜索页：{url}")
        patterns = [
            'joblist.json',
            'search/joblist.json',
            'zpgeek/search/joblist.json',
            'wapi/zpgeek/search/joblist.json',
        ]
        for p in patterns:
            try:
                page.listen.start(p)
            except Exception:
                pass
        page.get(url)
        self.log("⏳ 等待页面加载...")

        # 先收集列表数据
        scroll_count = 0
        while len(collected_jobs) < limit and not self.stop_flag:
            res, page = self._safe_listen_wait(page, patterns, url, timeout=12)
            if not res:
                page.scroll.down(500)
                scroll_count += 1
                if scroll_count > 3:
                    break
                continue

            body = res.response.body
            if isinstance(body, str):
                body = json.loads(body)

            job_list = body.get('zpData', {}).get('jobList', [])
            has_more = body.get('zpData', {}).get('hasMore', False)

            for item in job_list:
                if len(collected_jobs) >= limit:
                    break
                job = parse_job_item(item)
                job['source_url'] = f"https://www.zhipin.com/job_detail/{job['job_id']}.html"
                if job['job_id'] and job['job_id'] in saved_ids:
                    skipped += 1
                    continue
                collected_jobs.append(job)

            if not has_more or len(collected_jobs) >= limit:
                break

            page.scroll.down(600)
            time.sleep(random.uniform(1.0, 2.0))
            scroll_count += 1

        page.listen.stop()
        self.log(f"✅ 共收集 {len(collected_jobs)} 个待采集职位")

        # 公司名模式：AI过滤
        if params.get('search_type') == 'company' and collected_jobs:
            self.log("\n🤖 AI过滤目标岗位...")
            collected_jobs = self.ai_filter(collected_jobs)

        # 逐个点击卡片拿详情
        self.progress(0, len(collected_jobs))
        cards = page.eles('css:.job-card-box')
        self.log(f"\n📋 开始逐个获取详情（共 {len(collected_jobs)} 个）")

        for i, job in enumerate(collected_jobs):
            if self.stop_flag:
                break

            self.log(f"\n── [{i+1}/{len(collected_jobs)}] {job['job_name']} ──")

            try:
                if i == 0:
                    # 第一张卡片：页面加载时已默认高亮，直接从右侧 HTML 面板解析
                    job.update(parse_detail_from_html(page))
                    self.log(f"   ✅ 详情获取成功（HTML）")
                else:
                    # 后续卡片：点击触发 detail.json，监听响应
                    page.listen.start('zpgeek/job/detail')
                    if i < len(cards):
                        cards[i].click()
                    res, page = self._safe_listen_wait(page, 'zpgeek/job/detail', None, timeout=10)
                    try:
                        page.listen.stop()
                    except Exception:
                        pass
                    if res:
                        body = res.response.body
                        if isinstance(body, str):
                            body = json.loads(body)
                        job.update(parse_detail(body))
                        self.log(f"   ✅ 详情获取成功（JSON）")
                    else:
                        # 超时降级：从 HTML 面板读取
                        job.update(parse_detail_from_html(page))
                        self.log(f"   ⚠️  JSON超时，降级HTML解析", "warn")
                    time.sleep(random.uniform(1.5, 2.5))
            except Exception as e:
                self.log(f"   ⚠️  详情获取失败：{e}", "warn")


            try:
                filename = self.save_record(job)
                if job['job_id']:
                    mark_saved(job['job_id'], self.save_dir)
                self.log(f"   💾 {job['job_name']} | {job['salary']}", "success")
                success += 1
                self.progress(success, len(collected_jobs))
            except Exception as e:
                self.log(f"   ❌ 保存失败：{e}", "error")
                failed += 1

        return success, failed, skipped

    # ── 公司页 - 简便模式 ────────────────────────────

    def collect_company_fast(self, page, company_url: str,
                             company_name: str, limit: int) -> tuple:
        success, failed, skipped = 0, 0, 0
        saved_ids = get_saved_ids(self.save_dir)
        page_num = 1

        self.log(f"🏢 打开公司职位页：{company_url}")
        page.get(company_url)
        time.sleep(3)

        # 职位类型
        type_items = page.eles('css:.position-select-list li')
        if type_items:
            self.log(f"   职位类型：")
            for t in type_items[:6]:
                self.log(f"     {t.text.strip()}")

        collected = 0
        while collected < limit and not self.stop_flag:
            cards = page.eles('css:li.job-card-box')
            self.log(f"\n   第{page_num}页，{len(cards)} 个职位")

            for card in cards:
                if collected >= limit or self.stop_flag:
                    break
                try:
                    job = parse_company_card_html(card)
                    job['company'] = company_name
                    if job['job_id'] and job['job_id'] in saved_ids:
                        skipped += 1
                        continue
                    filename = self.save_record(job)
                    if job['job_id']:
                        mark_saved(job['job_id'], self.save_dir)
                    self.log(f"   ✅ {job['job_name']} | {job['salary']}", "success")
                    success += 1
                    collected += 1
                    self.progress(success, limit)
                except Exception as e:
                    self.log(f"   ❌ 失败：{e}", "error")
                    failed += 1

            # 翻页
            next_btn = page.ele(f'xpath://a[@ka="page-{page_num+1}"]')
            if not next_btn or collected >= limit:
                break
            self.log(f"   翻到第{page_num+1}页...")
            next_btn.click(by_js=True)
            time.sleep(2)
            page_num += 1

        return success, failed, skipped

    # ── 公司页 - 详情模式 ────────────────────────────

    def collect_company_detail(self, page, company_url: str,
                               company_name: str, limit: int) -> tuple:
        success, failed, skipped = 0, 0, 0
        saved_ids = get_saved_ids(self.save_dir)
        page_num = 1

        self.log(f"🏢 打开公司职位页：{company_url}")
        page.get(company_url)
        time.sleep(3)

        collected = 0
        while collected < limit and not self.stop_flag:
            cards = page.eles('css:li.job-card-box')
            self.log(f"\n   第{page_num}页，{len(cards)} 个职位")

            for idx, card in enumerate(cards):
                if collected >= limit or self.stop_flag:
                    break
                try:
                    job = parse_company_card_html(card)
                    job['company'] = company_name

                    if job['job_id'] and job['job_id'] in saved_ids:
                        skipped += 1
                        continue

                    if idx == 0:
                        # 第一张卡片：页面加载时已默认高亮，直接从右侧 HTML 面板解析
                        job.update(parse_detail_from_html(page))
                        self.log(f"   ✅ 详情获取成功（HTML）")
                    else:
                        # 后续卡片：点击触发 detail.json，监听响应
                        target_cards = page.eles('css:li.job-card-box')
                        page.listen.start('detail')
                        target_cards[idx].click()
                        res, page = self._safe_listen_wait(page, 'detail', None, timeout=10)
                        try:
                            page.listen.stop()
                        except Exception:
                            pass
                        if res:
                            body = res.response.body
                            if isinstance(body, str):
                                body = json.loads(body)
                            job.update(parse_detail(body))
                            self.log(f"   ✅ 详情获取成功（JSON）")
                        else:
                            # 超时降级：从 HTML 面板读取
                            job.update(parse_detail_from_html(page))
                            self.log(f"   ⚠️  JSON超时，降级HTML解析", "warn")
                        time.sleep(random.uniform(1.5, 2.5))

                    filename = self.save_record(job)
                    if job['job_id']:
                        mark_saved(job['job_id'], self.save_dir)
                    self.log(f"   💾 {job['job_name']} | {job['salary']}", "success")
                    success += 1
                    collected += 1
                    self.progress(success, limit)
                except Exception as e:
                    self.log(f"   ❌ 失败：{e}", "error")
                    failed += 1

            next_btn = page.ele(f'xpath://a[@ka="page-{page_num+1}"]')
            if not next_btn or collected >= limit:
                break
            self.log(f"   翻到第{page_num+1}页...")
            next_btn.click(by_js=True)
            time.sleep(2)
            page_num += 1

        return success, failed, skipped

    # ── 主入口 ──────────────────────────────────────

    def run(self, params: dict):
        try:
            query        = params.get('query', '储能 技术支持')
            collect_mode = params.get('collect_mode', 'fast')
            limit        = int(params.get('limit', 30))

            self.log(f"🔍 搜索词：{query}  城市：{params.get('city_name','全国')}  上限：{limit}条")
            self.log(f"   模式：{'详情' if collect_mode == 'detail' else '简便'}")

            # 连接 Chrome
            self.log(f"\n🔗 连接 Chrome（端口 {self.port}）...")
            try:
                page = get_page(self.port)
                self.log(f"✅ 连接成功：{page.title}")
            except Exception as e:
                self.log(f"❌ Chrome 连接失败：{e}", "error")
                self.log("   请确认已用调试模式启动 Chrome：", "error")
                self.log("   /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome --remote-debugging-port=9222", "error")
                self.done(0, 0, 0)
                return

            # 先打开搜索页，判断是否有公司卡片
            search_url = self.build_search_url(params)
            self.log(f"\n🌐 打开搜索页，判断结果类型...")
            patterns = [
                'joblist.json',
                'search/joblist.json',
                'zpgeek/search/joblist.json',
                'wapi/zpgeek/search/joblist.json',
            ]
            for p in patterns:
                try:
                    page.listen.start(p)
                except Exception:
                    pass
            page.get(search_url)
            res, page = self._safe_listen_wait(page, patterns, search_url, timeout=12)
            try:
                page.listen.stop()
            except Exception:
                pass

            # 如果没有捕获到网络响应，可能页面改为通过不同接口或直接客户端渲染
            if not res:
                self.log("   未捕获到 joblist.json 响应，尝试通过 DOM 检测结果或延长等待...", "warn")
                time.sleep(1)
                # 先尝试通过 DOM 判断是否已有职位卡片
                company_card = page.ele('xpath://div[contains(@class,"c-company-card")]')
                cards = page.eles('css:.job-card-box')
                if not company_card and not cards:
                    # 再尝试延长监听（兼容接口名变化或延迟加载）
                    self.log("   未在 DOM 中找到职位卡片，延长监听至 20s ...", "warn")
                    res, page = self._safe_listen_wait(page, patterns, search_url, timeout=20)
                    try:
                        page.listen.stop()
                    except Exception:
                        pass
                    # 更新 DOM 检测结果
                    company_card = page.ele('xpath://div[contains(@class,"c-company-card")]')
                    cards = page.eles('css:.job-card-box')
                    # 如果仍然没有卡片，轮询 DOM（兼容前端延迟渲染）并收集诊断信息
                    if not company_card and not cards:
                        self.log("   继续轮询 DOM，等待客户端渲染（最多 20s）...", "warn")
                        waited = 0
                        while waited < 20 and not (company_card or cards):
                            time.sleep(1)
                            waited += 1
                            if waited % 5 == 0:
                                self.log(f"   已等待 {waited}s，检查 DOM...", "warn")
                            company_card = page.ele('xpath://div[contains(@class,"c-company-card")]')
                            cards = page.eles('css:.job-card-box')
                        if not company_card and not cards:
                            # 诊断性日志：采集页面URL与脚本摘要，帮助定位接口/渲染方式
                            try:
                                url_snip = page.url
                            except Exception:
                                url_snip = '<unknown>'
                            try:
                                scripts = page.run_js(
                                    "var s=Array.from(document.scripts).map(x=>x.src||x.innerText.slice(0,200)); JSON.stringify(s);"
                                )
                            except Exception:
                                scripts = 'unable to read scripts'
                            self.log(f"   诊断：仍未找到职位卡片，当前URL：{url_snip}", "error")
                            self.log(f"   诊断：页面脚本（片段）：{str(scripts)[:1000]}", "error")
            else:
                time.sleep(2)
                company_card = page.ele('xpath://div[contains(@class,"c-company-card")]')

            if company_card:
                # 公司搜索模式
                company_name_el = company_card.ele('css:.company-name')
                company_name = company_name_el.text.strip() if company_name_el else query
                self.log(f"\n🏢 检测到公司卡片：{company_name}")

                job_link = company_card.ele('xpath:.//a[contains(@href,"gongsir")]')
                if not job_link:
                    self.log("❌ 未找到在招职位链接", "error")
                    self.done(0, 0, 0)
                    return

                job_count_el = job_link.ele('css:.count-text')
                job_count = job_count_el.text.strip() if job_count_el else "?"
                self.log(f"   在招职位数：{job_count}")
                self.log(f"   点击「在招职位」...")
                job_link.click(by_js=True)
                time.sleep(3)

                company_url = page.url
                self.log(f"   公司职位页：{company_url}")

                if collect_mode == 'detail':
                    self.log(f"\n📋 详情模式采集...")
                    s, f, sk = self.collect_company_detail(page, company_url, company_name, limit)
                else:
                    self.log(f"\n⚡ 简便模式采集...")
                    s, f, sk = self.collect_company_fast(page, company_url, company_name, limit)
            else:
                # 职位搜索模式
                self.log(f"\n📋 职位搜索模式")
                if collect_mode == 'detail':
                    self.log(f"   详情模式采集...")
                    s, f, sk = self.collect_search_detail(page, params, limit)
                else:
                    self.log(f"   简便模式采集...")
                    s, f, sk = self.collect_search_fast(page, params, limit)

            self.log("\n" + "=" * 48, "success")
            self.log(f"🎉 采集完成！成功 {s}  失败 {f}  跳过 {sk}", "success")
            self.log(f"📁 {self.save_dir}", "success")
            self.log("=" * 48, "success")
            self.done(s, f, sk)

        except Exception as e:
            self.log(f"\n❌ 采集异常：{e}", "error")
            self.log(traceback.format_exc(), "error")
            self.done(0, 0, 0)

    def _safe_listen_wait(self, page, pattern, url: str = None, timeout: int = 12):
        """Attempt to call `page.listen.wait` for one or multiple patterns.
        `pattern` may be a string or a list/tuple of substrings to try.
        If the listener is broken, attempt to recreate the page and retry
        once. Returns a tuple (res, page).
        """
        patterns = pattern if isinstance(pattern, (list, tuple)) else [pattern]

        def try_patterns(p: object, pats, wait_timeout):
            for pat in pats:
                try:
                    p.listen.start(pat)
                except Exception:
                    # ignore start errors and continue with next pattern
                    pass
                # poll in short intervals to increase chance of catching requests
                waited = 0
                step = 1
                while waited < wait_timeout:
                    try:
                        # log current page URL for diagnostics
                        try:
                            cur_url = getattr(p, 'url', None) or getattr(p, 'current_url', None)
                        except Exception:
                            cur_url = '<unknown>'
                        self.log(f"   监听模式 '{pat}' 等待中，已等待 {waited}s，页面URL={cur_url}")
                        res = p.listen.wait(int(step))
                        if res:
                            return res, p
                    except Exception as e:
                        # if listen.wait raises, record and continue polling
                        self.log(f"   监听模式 '{pat}' 异常等待：{e}", "warn")
                    waited += step
                # timed out for this pattern, continue to next
            return None, p

        # First try with current page
        self.log(f"   调试：尝试捕获网络响应，候选模式={patterns}，超时={timeout}s")
        try:
            res, page = try_patterns(page, patterns, timeout)
            if res:
                # try to gather some diagnostic info about matched response
                try:
                    url_matched = getattr(res.response, 'url', None) or getattr(res, 'url', None)
                except Exception:
                    url_matched = None
                preview = None
                try:
                    body = res.response.body
                    if isinstance(body, str):
                        preview = body[:800]
                    elif isinstance(body, (bytes, bytearray)):
                        preview = str(body)[:800]
                    elif isinstance(body, dict):
                        preview = json.dumps(list(body.keys()))[:800]
                except Exception:
                    preview = '<unable to preview body>'
                self.log(f"   捕获到响应：url={url_matched}  预览={str(preview)[:300]}")
                return res, page
        except AttributeError:
            pass

        # If nothing found or listener broken, try to recreate page and retry
        self.log("   监听未命中或异常，尝试重连页面并用更多候选模式重试...", "warn")
        try:
            new_page = get_page(self.port)
            # If a URL is provided, navigate once to re-trigger network
            if url:
                try:
                    new_page.get(url)
                except Exception as e:
                    self.log(f"   重连时导航失败：{e}", "warn")
            res, new_page = try_patterns(new_page, patterns, timeout)
            if res:
                try:
                    url_matched = getattr(res.response, 'url', None) or getattr(res, 'url', None)
                except Exception:
                    url_matched = None
                self.log(f"   重连后捕获到响应：url={url_matched}")
            else:
                self.log("   重连后仍未捕获到响应", "warn")
            return res, new_page
        except Exception as e:
            self.log(f"   监听重连失败：{e}", "error")
            return None, page