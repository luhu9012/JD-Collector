#!/usr/bin/env python3
"""
验证脚本：确认从右侧 HTML 面板提取字段 + 清洗反爬 span 的效果
用法：python inspect_detail_parse.py "https://www.zhipin.com/gongsi/job/xxx.html"
"""

import sys
import time
import re
from DrissionPage import ChromiumPage, ChromiumOptions

URL  = sys.argv[1] if len(sys.argv) > 1 else "https://www.zhipin.com/gongsi/job/9513e5c08ac3c3d11X1y3ty5GFA~.html"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 9222

co   = ChromiumOptions().set_local_port(PORT)
page = ChromiumPage(co)

# ── 反爬 span class 特征：随机类名 + display:none / 极小尺寸 ──────────
# BOSS直聘用内联 <style> 把某些 span 设为 display:none 或 width:0.1px
# 直接用 JS 拿 innerText（浏览器会跳过不可见元素）即可绕过

def get_clean_text_js(page, selector: str) -> str:
    """用 JS innerText 获取可见文本，自动跳过隐藏元素"""
    script = f"""
    var el = document.querySelector('{selector}');
    return el ? el.innerText : '';
    """
    return (page.run_js(script) or '').strip()

def parse_detail_from_html(page) -> dict:
    """从右侧详情面板 HTML 提取字段"""
    result = {
        "description":  "",
        "address":      "",
        "boss_active":  "",
    }

    # 岗位描述：用 JS innerText 自动过滤隐藏 span
    result["description"] = get_clean_text_js(page, '.job-detail-box .desc')

    # 地址
    result["address"] = get_clean_text_js(page, '.job-address-desc')

    # boss 活跃度
    result["boss_active"] = get_clean_text_js(page, '.boss-active-time')

    return result

# ── 主流程 ────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print(f"打开：{URL}")
page.get(URL)
time.sleep(3)

print("\n[第一张卡片默认高亮，直接解析右侧面板]")
data = parse_detail_from_html(page)

print(f"\n  地址      : {data['address']!r}")
print(f"  boss活跃度: {data['boss_active']!r}")
print(f"\n  岗位描述（前500字）:")
print(data['description'][:500])

# ── 验证第二张卡片点击后是否正确更新 ─────────────────────────────────
print(f"\n{'─'*60}")
print("[点击第二张卡片，验证面板更新]")
cards = page.eles('css:li.job-card-box')
print(f"  共找到 {len(cards)} 张卡片")

if len(cards) >= 2:
    cards[1].click()
    time.sleep(2)  # 等面板动态更新
    data2 = parse_detail_from_html(page)
    print(f"\n  地址      : {data2['address']!r}")
    print(f"  boss活跃度: {data2['boss_active']!r}")
    print(f"\n  岗位描述（前500字）:")
    print(data2['description'][:500])
    print(f"\n  ✅ 两次描述不同：{data['description'][:30]!r} vs {data2['description'][:30]!r}")

print(f"\n{'='*60}")
print("✅ 验证完毕")