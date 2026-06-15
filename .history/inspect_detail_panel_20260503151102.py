#!/usr/bin/env python3
"""
验证脚本：检查 BOSS直聘公司职位页右侧详情面板的 HTML 结构
用法：python inspect_detail_panel.py <公司职位页URL>
示例：python inspect_detail_panel.py "https://www.zhipin.com/gongsi/job/9513e5c08ac3c3d11X1y3ty5GFA~.html"
"""

import sys
import time
from DrissionPage import ChromiumPage, ChromiumOptions

URL = sys.argv[1] if len(sys.argv) > 1 else "https://www.zhipin.com/gongsi/job/9513e5c08ac3c3d11X1y3ty5GFA~.html"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 9222

co = ChromiumOptions().set_local_port(PORT)
page = ChromiumPage(co)

print(f"\n{'='*60}")
print(f"打开：{URL}")
page.get(URL)
time.sleep(3)

# ── 1. 找右侧详情容器 ──────────────────────────────────
CANDIDATE_SELECTORS = [
    '.job-detail-box',
    '.job-detail',
    '.detail-box',
    '.job-sec-wrap',
    '.job-detail-section',
    '.detail-content',
    '.rightPage',
    '.job-detail-pane',
]

print("\n[1] 尝试常见选择器找右侧详情容器：")
found_container = None
for sel in CANDIDATE_SELECTORS:
    el = page.ele(f'css:{sel}')
    if el:
        print(f"  ✅ 找到：{sel}")
        found_container = (sel, el)
        break
    else:
        print(f"  ✗  {sel}")

# ── 2. 如果没找到，dump 页面所有带 class 的 div，找线索 ──
if not found_container:
    print("\n[2] 未找到已知容器，输出页面顶层 div class 列表：")
    divs = page.eles('css:body > div')
    for d in divs:
        cls = d.attr('class') or ''
        print(f"  div.{cls[:80]}")

    print("\n  再往下一层（main/section/article）：")
    for tag in ['main', 'section', 'article']:
        els = page.eles(f'css:{tag}')
        for e in els:
            cls = e.attr('class') or ''
            print(f"  {tag}.{cls[:80]}")
else:
    sel, container = found_container
    print(f"\n[2] 容器 `{sel}` 内部结构：")
    # 打印直接子元素
    children = container.eles('css:*')
    seen = set()
    for c in children[:40]:
        tag = c.tag
        cls = (c.attr('class') or '')[:60]
        key = f"{tag}.{cls}"
        if key not in seen:
            seen.add(key)
            print(f"  <{tag} class=\"{cls}\">")

# ── 3. 逐项尝试具体字段 ──────────────────────────────────
print("\n[3] 尝试提取具体字段：")

FIELD_SELECTORS = {
    "岗位描述":     ['.job-sec-text', '.job-detail-section .text', '.job-description', '.desc', '.job-sec .text'],
    "公司介绍":     ['.job-company-intro', '.company-desc', '.brand-story', '.company-intro'],
    "地址":         ['.job-location', '.address', '.location-info', '.job-address'],
    "boss活跃度":   ['.boss-active-time', '.active-time', '.boss-info .time', '.last-active'],
    "公司标签":     ['.brand-tag-list li', '.company-label li', '.tag-list li'],
}

for field, selectors in FIELD_SELECTORS.items():
    found = False
    for sel in selectors:
        el = page.ele(f'css:{sel}')
        if el:
            text = el.text.strip()[:100]
            print(f"  ✅ {field:<12} [{sel}]  →  {text!r}")
            found = True
            break
    if not found:
        print(f"  ✗  {field:<12} 未找到")

# ── 4. 输出右侧面板完整 outerHTML（截断）───────────────────
print("\n[4] 右侧面板原始 HTML（前3000字符）：")
if found_container:
    _, container = found_container
    html = container.html or ''
    print(html[:3000])
else:
    # fallback：找包含"岗位职责"关键词的元素
    print("  容器未找到，尝试关键词定位...")
    for kw in ['岗位职责', '任职要求', 'postDescription']:
        el = page.ele(f'xpath://*[contains(text(),"{kw}")]')
        if el:
            parent = el.parent()
            print(f"  关键词 '{kw}' 所在父元素：<{parent.tag} class=\"{parent.attr('class')}\">")
            print(parent.html[:2000])
            break

print(f"\n{'='*60}")
print("✅ 检查完毕，请把输出内容发给我分析")
