/* JD Collector — app.js v2.1.0 */

const state = {
  running: false,
  success: 0, failed: 0, skipped: 0,
  pollTimer: null,
};

const $ = id => document.getElementById(id);
const api = () => window.pywebview?.api;

// ── 工具 ──────────────────────────────────────────────
function appendLog(text, tag = "info") {
  const el = document.createElement("div");
  el.className = `log-line ${tag}`;
  el.textContent = text;
  const area = $("log-area");
  area.appendChild(el);
  area.scrollTop = area.scrollHeight;
}

function setStatus(s, text) {
  $("status-dot").className = "dot " + s;
  $("status-text").textContent = text;
}

function setProgress(current, total) {
  const pct = total > 0 ? Math.round(current / total * 100) : 0;
  $("progress-bar").style.width = pct + "%";
  $("progress-text").textContent = `${current} / ${total}`;
}

function updateStats() {
  $("stat-success").textContent = state.success;
  $("stat-failed").textContent = state.failed;
  $("stat-skipped").textContent = state.skipped;
}

// ── Tab 切换 ──────────────────────────────────────────
function switchTab(name) {
  document.querySelectorAll(".tab").forEach(t =>
    t.classList.toggle("active", t.dataset.tab === name));
  document.querySelectorAll(".tab-content").forEach(c =>{
     c.classList.remove("active");
    if(c.id === "tab-" + name){
      c.classList.add("active");
    }
 
  if (name === "data") loadDataTab();
  })
}

document.querySelectorAll(".tab").forEach(tab =>
  tab.addEventListener("click", () => switchTab(tab.dataset.tab)));

// ── 单选 Chip ─────────────────────────────────────────
["collect-mode","city-chips","jobtype-chips",
 "salary-chips","experience-chips","degree-chips","scale-chips"
].forEach(groupId => {
  const group = $(groupId);
  if (!group) return;
  group.querySelectorAll(".chip").forEach(chip => {
    chip.addEventListener("click", () => {
      group.querySelectorAll(".chip").forEach(c => c.classList.remove("active"));
      chip.classList.add("active");
    });
  });
});

// ── 多选 Chip（行业最多3个）──────────────────────────
const industryGroup = $("industry-chips");
industryGroup.querySelectorAll(".chip").forEach(chip => {
  chip.addEventListener("click", () => {
    if (chip.classList.contains("active")) {
      chip.classList.remove("active");
    } else if (industryGroup.querySelectorAll(".chip.active").length < 3) {
      chip.classList.add("active");
    } else {
      chip.style.opacity = "0.4";
      setTimeout(() => chip.style.opacity = "", 300);
    }
  });
});

// ── Spinner ───────────────────────────────────────────
$("limit-dec").addEventListener("click", () => {
  $("limit").value = Math.max(5, parseInt($("limit").value || 30) - 5);
});
$("limit-inc").addEventListener("click", () => {
  $("limit").value = Math.min(200, parseInt($("limit").value || 30) + 5);
});

// ── 采集参数 ──────────────────────────────────────────
function getCollectParams() {
  const chip = id => $(id)?.querySelector(".chip.active");
  const industries = [...$("industry-chips").querySelectorAll(".chip.active")]
    .map(c => c.dataset.val).filter(Boolean);
  return {
    query:        $("query").value.trim() || "储能 技术支持",
    collect_mode: chip("collect-mode")?.dataset.val     || "fast",
    city:         chip("city-chips")?.dataset.val       || "100010000",
    city_name:    chip("city-chips")?.dataset.name      || "全国",
    industries,
    job_type:     chip("jobtype-chips")?.dataset.val    || "",
    salary:       chip("salary-chips")?.dataset.val     || "",
    experience:   chip("experience-chips")?.dataset.val || "",
    degree:       chip("degree-chips")?.dataset.val     || "",
    scale:        chip("scale-chips")?.dataset.val      || "",
    limit:        parseInt($("limit").value || 30),
  };
}

// ── 开始 / 停止 ───────────────────────────────────────
$("start-btn").addEventListener("click", async () => {
  if (!api()) { appendLog("❌ Python API 未就绪", "error"); return; }

  if (state.running) {
    await api().stop_collect();
    stopRunning("已停止");
    return;
  }

  state.success = state.failed = state.skipped = 0;
  updateStats();
  $("log-area").innerHTML = "";
  setProgress(0, 0);
  $("open-dir-btn").classList.add("hidden");

  state.running = true;
  $("start-btn").textContent = "■ 停止采集";
  $("start-btn").classList.add("running");
  setStatus("running", "采集中...");

  await api().start_collect(getCollectParams());
  state.pollTimer = setInterval(pollLogs, 300);
});

async function pollLogs() {
  if (!api()) return;
  const logs = await api().get_logs();
  logs.forEach(item => {
    if (item.type === "log") {
      appendLog(item.text, item.tag || "info");
    } else if (item.type === "progress") {
      setProgress(item.current, item.total);
    } else if (item.type === "done") {
      state.success = item.success;
      state.failed  = item.failed;
      state.skipped = item.skipped;
      updateStats();
      stopRunning(`完成：成功${item.success} 失败${item.failed} 跳过${item.skipped}`);
      $("open-dir-btn").classList.remove("hidden");
      loadHistory();
    }
  });
}

function stopRunning(text) {
  state.running = false;
  if (state.pollTimer) { clearInterval(state.pollTimer); state.pollTimer = null; }
  $("start-btn").textContent = "▶ 开始采集";
  $("start-btn").classList.remove("running");
  setStatus("done", text);
}

$("open-dir-btn").addEventListener("click", async () => {
  if (api()) await api().open_save_dir();
});

$("export-log-btn").addEventListener("click", async () => {
  if (!api()) return;
  const lines = [...$("log-area").querySelectorAll(".log-line")]
    .map(el => el.textContent).join("\n");
  const result = await api().export_log(lines);
  if (result?.ok) appendLog(`📄 日志已保存：${result.path}`, "info");
});

// ── 历史统计 ──────────────────────────────────────────
async function loadHistory() {
  if (!api()) return;
  try {
    const h = await api().get_history();
    $("history-info").textContent = `已采集 ${h.total} 条  上次：${h.last_date}`;
  } catch(e) {}
}

// ── 设置页 ────────────────────────────────────────────
async function loadSettings() {
  if (!api()) return;
  const cfg = await api().load_config();
  $("chrome-port").value = cfg.chrome_port || 9222;
  $("api-base").value    = cfg.api_base    || "";
  $("api-key").value     = cfg.api_key     || "";
  $("model").value       = cfg.model       || "";
  $("save-dir").value    = cfg.save_dir    || "";

  const chromeResult = await api().get_chrome_path();
  $("chrome-path").value = cfg.chrome_path || chromeResult?.path || "";

  const formats = cfg.export_formats || ["md","jsonl","csv"];
  document.querySelectorAll(".check-group input[type=checkbox]").forEach(cb => {
    cb.checked = formats.includes(cb.value);
  });

  const positions = cfg.target_positions || [];
  $("target-positions").value = positions.join("\n");
}

document.querySelectorAll(".quick-btn[data-val]").forEach(btn => {
  btn.addEventListener("click", () => { $("api-base").value = btn.dataset.val; });
});
document.querySelectorAll(".quick-btn[data-model]").forEach(btn => {
  btn.addEventListener("click", () => { $("model").value = btn.dataset.model; });
});

$("toggle-key").addEventListener("click", () => {
  const inp = $("api-key");
  inp.type = inp.type === "password" ? "text" : "password";
});

$("browse-btn").addEventListener("click", async () => {
  if (!api()) return;
  const result = await api().browse_dir();
  if (result?.path) $("save-dir").value = result.path;
});

$("browse-chrome-btn").addEventListener("click", async () => {
  if (!api()) return;
  const result = await api().browse_file();
  if (result?.path) $("chrome-path").value = result.path;
});

$("launch-chrome-btn").addEventListener("click", async () => {
  if (!api()) return;
  const btn = $("launch-chrome-btn");
  btn.textContent = "启动中...";
  btn.disabled = true;

  const path = $("chrome-path").value.trim();
  const port = parseInt($("chrome-port").value || 9222);
  await api().save_config({ chrome_path: path, chrome_port: port });

  const result = await api().launch_chrome();
  btn.textContent = "🚀 启动 Chrome";
  btn.disabled = false;

  const el = $("chrome-check-result");
  if (result.ok) {
    el.innerHTML = '<p class="check-ok">✅ Chrome 已启动，请在浏览器里登录 BOSS直聘后开始采集</p>';
    $("env-banner").classList.add("hidden");
  } else {
    el.innerHTML = `<p class="check-err">❌ ${result.error}</p>`;
    $("env-msg").textContent = `⚠️  Chrome 启动失败，点击去设置`;
    $("env-banner").classList.remove("hidden");
  }
});

$("check-chrome-btn").addEventListener("click", async () => {
  if (!api()) return;
  const btn = $("check-chrome-btn");
  btn.textContent = "检测中...";
  btn.disabled = true;
  const result = await api().check_environment();
  btn.textContent = "🔍 检测连接";
  btn.disabled = false;

  const el = $("chrome-check-result");
  if (result.chrome_ok) {
    el.innerHTML = `<p class="check-ok">✅ Chrome 连接正常（端口 ${result.port}）</p>`;
    $("env-banner").classList.add("hidden");
  } else {
    el.innerHTML = `<p class="check-err">❌ ${result.chrome_error}（端口 ${result.port}）</p>`;
    $("env-msg").textContent = `⚠️  Chrome 未连接，点击去设置`;
    $("env-banner").classList.remove("hidden");
  }
});

$("save-settings-btn").addEventListener("click", async () => {
  if (!api()) return;
  const formats = [...document.querySelectorAll(".check-group input:checked")]
    .map(cb => cb.value);
  const positions = $("target-positions").value
    .split("\n").map(s => s.trim()).filter(Boolean);
  const cfg = {
    chrome_path:      $("chrome-path").value.trim(),
    chrome_port:      parseInt($("chrome-port").value || 9222),
    api_base:         $("api-base").value.trim(),
    api_key:          $("api-key").value.trim(),
    model:            $("model").value.trim(),
    save_dir:         $("save-dir").value.trim(),
    export_formats:   formats,
    target_positions: positions,
  };
  await api().save_config(cfg);
  const tip = $("save-tip");
  tip.classList.remove("hidden");
  setTimeout(() => tip.classList.add("hidden"), 2000);
});

// ════════════════════════════════════════════════════════
// ── 数据页 ──────────────────────────────────────────────
// ════════════════════════════════════════════════════════

let _allJobs     = [];       // 全量缓存
let _charts      = {};       // Chart.js 实例
const _selectedIds = new Set();

// 调色板
const PALETTE = [
  '#3b82f6','#10b981','#f59e0b','#8b5cf6',
  '#ef4444','#06b6d4','#84cc16','#f97316',
  '#ec4899','#14b8a6',
];

// ── 加载入口 ──────────────────────────────────────────
async function loadDataTab() {
  if (!api()) return;
  $("data-loading").classList.remove("hidden");
  try {
    _allJobs = await api().get_all_jobs() || [];
    populateFilters(_allJobs);
    renderDataTable(getFilteredJobs());
    await renderCharts();
  } finally {
    $("data-loading").classList.add("hidden");
  }
}

// ── 薪资中位数解析（前端镜像 Python 逻辑）─────────────
function parseSalaryMid(s) {
  if (!s) return null;
  s = s.replace(/[·\s]/g, '');
  let m = s.match(/(\d+)-(\d+)[Kk]/);
  if (m) return (parseInt(m[1]) + parseInt(m[2])) / 2;
  m = s.match(/(\d+)[Kk]以上/);
  if (m) return parseInt(m[1]) * 1.2;
  m = s.match(/(\d+)[Kk]以下/);
  if (m) return parseInt(m[1]) * 0.8;
  return null;
}

// ── 图表渲染 ──────────────────────────────────────────
async function renderCharts() {
  if (!api() || typeof Chart === 'undefined') return;
  const stats = await api().get_stats();
  if (!stats) return;

  function destroy(id) {
    if (_charts[id]) { _charts[id].destroy(); delete _charts[id]; }
  }

  function barChart(id, labels, data, color = '#3b82f6') {
    destroy(id);
    const ctx = document.getElementById(id);
    if (!ctx) return;
    _charts[id] = new Chart(ctx, {
      type: 'bar',
      data: {
        labels,
        datasets: [{ data, backgroundColor: color, borderRadius: 5, borderSkipped: false }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { font: { size: 11 }, maxRotation: 30 }, grid: { display: false } },
          y: { ticks: { font: { size: 11 }, precision: 0 },
               grid: { color: 'rgba(128,128,128,.1)' }, beginAtZero: true },
        },
      },
    });
  }

  function doughnutChart(id, labels, data) {
    destroy(id);
    const ctx = document.getElementById(id);
    if (!ctx) return;
    _charts[id] = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels,
        datasets: [{
          data,
          backgroundColor: PALETTE.slice(0, data.length),
          borderWidth: 2,
          borderColor: getComputedStyle(document.documentElement)
            .getPropertyValue('--card').trim() || '#fff',
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        cutout: '60%',
        plugins: {
          legend: {
            position: 'right',
            labels: { font: { size: 11 }, boxWidth: 10, padding: 8 },
          },
        },
      },
    });
  }

  // 薪资：柱状
  barChart('chart-salary',
    stats.salary.map(d => d.label),
    stats.salary.map(d => d.value),
    '#3b82f6');

  // 城市：环形
  doughnutChart('chart-city',
    stats.city.map(d => d.label),
    stats.city.map(d => d.value));

  // 规模 + 融资：环形
  doughnutChart('chart-scale',
    stats.scale.map(d => d.label),
    stats.scale.map(d => d.value));

  // 行业：环形
  doughnutChart('chart-industry',
    stats.industry.map(d => d.label),
    stats.industry.map(d => d.value));

  // 学历：柱状
  barChart('chart-degree',
    stats.degree.map(d => d.label),
    stats.degree.map(d => d.value),
    '#10b981');

  // 经验：柱状
  barChart('chart-experience',
    stats.experience.map(d => d.label),
    stats.experience.map(d => d.value),
    '#f59e0b');
}

// ── 筛选下拉框填充 ────────────────────────────────────
function populateFilters(jobs) {
  function fill(selId, values) {
    const sel = $(selId);
    if (!sel) return;
    const cur = sel.value;
    sel.innerHTML = `<option value="">全部</option>` +
      values.map(v => `<option value="${v}">${v}</option>`).join('');
    if (values.includes(cur)) sel.value = cur;
  }
  fill('df-city',  [...new Set(jobs.map(j => j.city).filter(Boolean))].sort());
  fill('df-scale', [...new Set(jobs.map(j => j.scale).filter(Boolean))].sort());
  fill('df-industry', [...new Set(jobs.map(j => j.industry).filter(Boolean))].sort());
}

// ── 筛选逻辑 ──────────────────────────────────────────
function getFilteredJobs() {
  const kw       = ($('df-search')?.value || '').trim().toLowerCase();
  const city     = $('df-city')?.value     || '';
  const scale    = $('df-scale')?.value    || '';
  const industry = $('df-industry')?.value || '';
  const salary   = $('df-salary')?.value   || '';

  return _allJobs.filter(j => {
    if (kw && !`${j.job_name}${j.company}`.toLowerCase().includes(kw)) return false;
    if (city     && j.city     !== city)     return false;
    if (scale    && j.scale    !== scale)    return false;
    if (industry && j.industry !== industry) return false;
    if (salary) {
      const [lo, hi] = salary.split(',').map(Number);
      const mid = parseSalaryMid(j.salary);
      if (mid === null || mid < lo || mid >= hi) return false;
    }
    return true;
  });
}

// ── 表格渲染 ──────────────────────────────────────────
function renderDataTable(jobs) {
  const tbody = $('data-tbody');
  const empty = $('data-empty');
  const countEl = $('data-total-count');
  if (countEl) countEl.textContent = `共 ${jobs.length} 条`;

  if (!jobs.length) {
    tbody.innerHTML = '';
    empty.classList.remove('hidden');
    updateSelectionUI();
    return;
  }
  empty.classList.add('hidden');

  tbody.innerHTML = jobs.map(j => {
    const checked = _selectedIds.has(j.id) ? 'checked' : '';
    const selCls  = _selectedIds.has(j.id) ? 'selected' : '';
    const urlBtn  = j.source_url
      ? `<a class="tbl-link" href="${j.source_url}" target="_blank">🔗</a>` : '';
    return `<tr class="${selCls}" data-id="${j.id}">
      <td class="col-ck"><input type="checkbox" class="row-ck" data-id="${j.id}" ${checked}></td>
      <td class="col-date">${(j.date||'').slice(5)}</td>
      <td class="col-job" title="${escHtml(j.job_name)}">${escHtml(j.job_name||'—')}</td>
      <td class="col-co"  title="${escHtml(j.company)}">${escHtml(j.company||'—')}</td>
      <td class="col-sal">${escHtml(j.salary||'—')}</td>
      <td class="col-city">${escHtml(j.city||'—')}</td>
      <td class="col-scale">${escHtml(j.scale||'—')}</td>
      <td class="col-exp">${escHtml(j.experience||'—')}</td>
      <td class="col-deg">${escHtml(j.degree||'—')}</td>
      <td class="col-op">${urlBtn}<button class="del-row-btn" data-id="${j.id}" title="删除此条">✕</button></td>
    </tr>`;
  }).join('');

  updateSelectionUI();
}

function escHtml(s) {
  return String(s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ── 勾选状态同步 ──────────────────────────────────────
function updateSelectionUI() {
  const cnt = _selectedIds.size;
  const selEl  = $('data-sel-count');
  const delBtn = $('data-delete-btn');
  if (selEl)  { selEl.textContent = cnt ? `已选 ${cnt} 条` : ''; }
  if (delBtn) { delBtn.classList.toggle('hidden', cnt === 0); }

  const allCks = [...($('data-tbody')?.querySelectorAll('.row-ck') || [])];
  const ckAll  = $('ck-all');
  if (ckAll && allCks.length) {
    const checkedCnt = allCks.filter(c => c.checked).length;
    ckAll.checked       = checkedCnt === allCks.length;
    ckAll.indeterminate = checkedCnt > 0 && checkedCnt < allCks.length;
  }
}

// ── 删除执行 ──────────────────────────────────────────
async function doDelete(ids) {
  if (!api() || !ids.length) return;
  const r = await api().delete_jobs(ids);
  if (r?.ok) {
    const idSet = new Set(ids);
    ids.forEach(id => _selectedIds.delete(id));
    _allJobs = _allJobs.filter(j => !idSet.has(j.id));
    populateFilters(_allJobs);
    renderDataTable(getFilteredJobs());
    await renderCharts();
    loadHistory();
    showToast(`已删除 ${r.deleted} 条记录`);
  } else {
    alert('删除失败：' + (r?.error || '未知错误'));
  }
}

function showToast(msg) {
  let t = $('data-toast');
  if (!t) return;
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2500);
}

// ── 事件：筛选 ────────────────────────────────────────
['df-search','df-city','df-scale','df-industry','df-salary'].forEach(id => {
  const el = $(id);
  if (el) el.addEventListener('input', () => renderDataTable(getFilteredJobs()));
});

// ── 事件：全选框 ──────────────────────────────────────
const ckAllEl = $('ck-all');
if (ckAllEl) {
  ckAllEl.addEventListener('change', e => {
    $('data-tbody').querySelectorAll('.row-ck').forEach(cb => {
      cb.checked = e.target.checked;
      const id = cb.dataset.id;
      e.target.checked ? _selectedIds.add(id) : _selectedIds.delete(id);
      cb.closest('tr').classList.toggle('selected', e.target.checked);
    });
    updateSelectionUI();
  });
}

// ── 事件：行勾选 / 单行删除（委托）─────────────────────
const tbodyEl = $('data-tbody');
if (tbodyEl) {
  tbodyEl.addEventListener('change', e => {
    if (!e.target.classList.contains('row-ck')) return;
    const id = e.target.dataset.id;
    e.target.checked ? _selectedIds.add(id) : _selectedIds.delete(id);
    e.target.closest('tr').classList.toggle('selected', e.target.checked);
    updateSelectionUI();
  });

  tbodyEl.addEventListener('click', async e => {
    const btn = e.target.closest('.del-row-btn');
    if (!btn) return;
    if (!confirm('确定删除这条记录？此操作不可撤销。')) return;
    await doDelete([btn.dataset.id]);
  });
}

// ── 事件：批量删除 ────────────────────────────────────
const delBtnEl = $('data-delete-btn');
if (delBtnEl) {
  delBtnEl.addEventListener('click', async () => {
    if (!_selectedIds.size) return;
    if (!confirm(`确定删除选中的 ${_selectedIds.size} 条记录？此操作不可撤销。`)) return;
    await doDelete([..._selectedIds]);
  });
}

// ── 事件：刷新 ────────────────────────────────────────
const refreshEl = $('data-refresh-btn');
if (refreshEl) refreshEl.addEventListener('click', loadDataTab);

// ── 初始化 ────────────────────────────────────────────
window.addEventListener("pywebviewready", async () => {
  await loadSettings();
  await loadHistory();
  const result = await api().check_environment();
  if (!result.chrome_ok) {
    $("env-msg").textContent = `⚠️  Chrome 未连接，点击去设置`;
    $("env-banner").classList.remove("hidden");
  }
});
