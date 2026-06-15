# JD Collector

轻量级的岗位信息采集桌面工具（基于 `pywebview` + `DrissionPage`）。

项目用途：在已登录的 Chrome（调试模式）中抓取 BOSS直聘的职位列表与详情，导出为 Markdown / JSONL / CSV 便于后续分析。

**主要特点**
- 支持“简便模式”（快速抓取列表）与“详情模式”（采集完整岗位描述）
- 支持公司页与职位搜索两种采集入口
- 可选接入 AI（OpenAI / DeepSeek 等）做公司名过滤
- 输出：Markdown（每条）、`jd_data.jsonl`（追加）、`jd_data.csv`

**仓库结构（简要）**
- `app.py`：桌面 UI 主程序（`pywebview` + 本地 API）
- `core.py`：采集核心逻辑（基于 `DrissionPage` 接管 Chrome）
- `ui/`：前端静态资源（`index.html`, `app.js`, `style.css`）
- `requirements.txt`：Python 依赖
- `jd_collector.spec`：`pyinstaller` 打包配置

---

**准备与运行（快速上手）**

- 系统要求：macOS / Linux（主要在 macOS 上测试），Python 3.10+ 推荐。
- 安装依赖：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

- 运行桌面程序：

```bash
python app.py
```

程序会打开一个窗口（默认 960×680）。首次使用流程：
- 在 `设置` 页检查或填写 Chrome 可执行路径（留空则自动检测）和调试端口（默认 `9222`）。
- 点击「启动 Chrome」会以远程调试模式尝试启动 Chrome（或手动使用 `--remote-debugging-port=9222` 启动并登录 BOSS直聘）。
- Chrome 登录并连接成功后，回到 `采集` 页点击「开始采集」。

---

**关键配置说明**
- 默认配置保存在：`~/.jd_collector_config.json`。
- 主要可配置项：`chrome_path`, `chrome_port`, `save_dir`, `export_formats`, `api_key`, `api_base`, `model`。
- 导出目录默认：`~/Desktop/jd_collector_output`。

---

**打包为 macOS 应用（可选）**

准备好虚拟环境和依赖后，通过 `pyinstaller` 使用仓库中的 `jd_collector.spec` 打包：

```bash
pyinstaller jd_collector.spec
```

注意：如果没有 `assets/icon.icns`，可以临时注释掉 `spec` 中的 icon 行以避免错误。打包完成后在 `dist/` 下会生成 `JD Collector.app`。

若打包后首次运行被系统阻止：右键 → 打开 → 在弹窗中选择「打开」。

---

**输出与数据格式**
- `jd_data.jsonl`：每行一个 JSON 对象，包含字段如 `id`, `date`, `job_name`, `company`, `salary`, `city`, `experience`, `degree`, `skills`, `description`, `source_url` 等。
- `jd_data.csv`：对 `jsonl` 做展平后的 CSV（含表头）。
- `*.md`：每条岗位单独的 Markdown 文档，文件名以 `YYYYMMDD-公司-职位.md` 命名。

---

**注意与合规**
- 该工具通过程序化访问公开网页内容，使用前请确认目标站点的使用条款与当地法律法规；仅用于合规且授权的场景。

---
![采集界面](./colector.png)
![设置界面](./setting.png)
![数据分析](./data.png)