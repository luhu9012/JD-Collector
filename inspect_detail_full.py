#!/usr/bin/env python3
"""
验证脚本：检查右侧详情面板所有字段的 HTML 选择器
用法：python inspect_detail_full.py "https://www.zhipin.com/gongsi/job/xxx.html"
"""
import sys, time
from DrissionPage import ChromiumPage, ChromiumOptions

URL  = sys.argv[1] if len(sys.argv) > 1 else "https://www.zhipin.com/gongsi/job/9513e5c08ac3c3d11X1y3ty5GFA~.html"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 9222

co   = ChromiumOptions().set_local_port(PORT)
page = ChromiumPage(co)

print(f"\n{'='*60}")
print(f"打开：{URL}")
page.get(URL)
time.sleep(3)

def js(selector):
    r = page.run_js(f"var e=document.querySelector('{selector}');return e?e.innerText:null;")
    return (r or '').strip()

def js_all(selector):
    r = page.run_js(f"""
    var els=document.querySelectorAll('{selector}');
    return Array.from(els).map(e=>e.innerText.trim()).filter(Boolean);
    """)
    return r or []

def js_attr(selector, attr):
    r = page.run_js(f"var e=document.querySelector('{selector}');return e?e.getAttribute('{attr}'):null;")
    return (r or '').strip()

print("\n[岗位基础信息]")
print(f"  job_name   : {js('.job-detail-box .job-name')!r}")
print(f"  salary     : {js('.job-detail-box .job-salary')!r}")
print(f"  tag-list   : {js_all('.job-detail-box .tag-list li')}")  # 城市/经验/学历

print("\n[技能标签]")
print(f"  job-label-list : {js_all('.job-label-list li')}")

print("\n[岗位描述]")
desc = js('.job-detail-box .desc')
print(f"  desc (前100): {desc[:100]!r}")

print("\n[Boss信息]")
print(f"  boss name      : {js('.job-boss-info .name')!r}")
print(f"  boss active    : {js('.boss-active-time')!r}")
print(f"  boss-info-attr : {js('.boss-info-attr')!r}")  # 公司名·职位

print("\n[地址]")
print(f"  job-address-desc : {js('.job-address-desc')!r}")

print("\n[公司信息（右侧面板是否有）]")
# 公司页右侧面板通常没有公司详情，但搜索结果页详情面板可能有
candidates_company = [
    '.job-sec-wrap .company-info',
    '.job-company-info',
    '.company-name',
    '.brand-name',
    '.job-boss-info .boss-info-attr',  # 包含 "公司名 · 职位"
]
for sel in candidates_company:
    val = js(sel)
    mark = '✅' if val else '✗ '
    print(f"  {mark} {sel:<40} → {val!r}")

print("\n[公司规模/融资/行业（右侧面板）]")
candidates_meta = [
    '.job-detail-company .company-tag-box li',
    '.company-tag-box li',
    '.sidebar-company .company-tag',
    '.job-sec-wrap .company-tag',
    '.job-company-tag li',
]
for sel in candidates_meta:
    val = js_all(sel)
    mark = '✅' if val else '✗ '
    print(f"  {mark} {sel:<45} → {val}")

print("\n[公司介绍]")
candidates_intro = [
    '.job-sec-wrap .text',
    '.company-intro',
    '.brand-introduction',
    '.job-company-desc',
]
for sel in candidates_intro:
    val = js(sel)
    mark = '✅' if val else '✗ '
    print(f"  {mark} {sel:<40} → {val[:60]!r}")

print("\n[公司标签/福利]")
candidates_labels = [
    '.company-label-list li',
    '.welfare-list li',
    '.tag-list li',
    '.job-label-list li',
]
for sel in candidates_labels:
    val = js_all(sel)
    mark = '✅' if val else '✗ '
    print(f"  {mark} {sel:<35} → {val}")

print(f"\n{'='*60}")
print("✅ 检查完毕")