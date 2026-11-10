(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const main = document.querySelector("main");
  if (!main || !$("result")) return;
  const translate = (text) => window.DFTranslate ? window.DFTranslate(text) : text;

  const style = document.createElement("style");
  style.textContent = `.dashgrid{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:12px}
    .dashpanel{border:1px solid var(--line);border-radius:10px;padding:12px;min-width:0}
    .dashpanel .bar{margin-bottom:6px}
    .dashkpi{font-size:30px;font-weight:750;padding:18px 4px;color:var(--accent)}
    .dashfilters{display:flex;gap:10px;flex-wrap:wrap;align-items:end;margin:12px 0}
    .dashfilters label{display:grid;gap:4px;font-size:12px;color:var(--muted)}
    .dashfilters select,.dashfilters input{min-width:130px;max-width:220px;padding:7px;border:1px solid var(--line);border-radius:8px}`;
  document.head.appendChild(style);

  const card = document.createElement("div");
  card.className = "card nav-view";
  card.id = "view-dashboard";
  card.innerHTML = `<div class="bar" style="margin-bottom:10px">
      <h2 style="margin:0">Dashboard</h2>
      <span><button class="btn" id="dashExport">HTML eksport</button>
      <button class="btn" id="dashRefresh">Hammasini yangilash</button></span></div>
    <div class="card"><strong>Global filtrlar</strong><div id="dashFilters" class="dashfilters"></div>
      <button class="btn primary" id="dashApplyFilters">Filtrlarni qo'llash va saqlash</button>
      <button class="btn" id="dashClearFilters">Tozalash</button></div>
    <div class="note" id="dashEmpty">Hali panel yo'q. SQL natijasi tagidagi "Dashboardga qo'shish" tugmasini bosing.</div>
    <div id="dashList" class="dashgrid"></div>`;
  main.insertBefore(card, $("result"));
  const list = $("dashList");

  function updateEmpty() {
    $("dashEmpty").classList.toggle("hidden", list.children.length > 0);
  }

  async function loadFilters() {
    const result = await api("/dashboard/filters");
    const root = $("dashFilters");
    root.innerHTML = "";
    result.options.forEach((option, index) => {
      const saved = result.filters.find((f) => f.table === option.table && f.column === option.column);
      const field = document.createElement("label");
      field.dataset.filterIndex = index;
      field.dataset.table = option.table;
      field.dataset.column = option.column;
      field.dataset.kind = option.kind;
      if (option.kind === "date") {
        field.innerHTML = `${esc(option.table)} · ${esc(option.column)}<span><input type="date" data-bound="from" value="${esc(saved?.from || "")}"><input type="date" data-bound="to" value="${esc(saved?.to || "")}"></span>`;
      } else {
        const options = option.values.map((v) =>
          `<option value="${esc(v)}" ${saved?.values?.includes(v) ? "selected" : ""}>${esc(v)}</option>`
        ).join("");
        field.innerHTML = `${esc(option.table)} · ${esc(option.column)}<select multiple size="3">${options}</select>`;
      }
      root.appendChild(field);
    });
  }

  async function saveFilters() {
    const filters = [];
    document.querySelectorAll("#dashFilters label").forEach((label) => {
      const rule = { table: label.dataset.table, column: label.dataset.column, kind: label.dataset.kind };
      if (rule.kind === "date") {
        rule.from = label.querySelector('[data-bound="from"]').value;
        rule.to = label.querySelector('[data-bound="to"]').value;
        if (!rule.from && !rule.to) return;
      } else {
        rule.values = Array.from(label.querySelector("select").selectedOptions).map((option) => option.value);
        if (!rule.values.length) return;
      }
      filters.push(rule);
    });
    await api("/dashboard/filters", {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filters }),
    });
    await loadAll();
  }

  function applyChart(table, cfg) {
    const wrap = table.closest(".scroll");
    const panel = wrap && wrap.nextElementSibling;
    if (!panel || !panel.classList.contains("chartpanel")) return;
    const sel = (k) => panel.querySelector(`[data-k="${k}"]`);
    const pick = (k, label) => {
      const s = sel(k);
      const o = s && Array.from(s.options).find((x) => x.textContent === label);
      if (o) s.value = o.value;
    };
    if (cfg.type && sel("type")) sel("type").value = cfg.type;
    pick("x", cfg.x);
    pick("y", cfg.y);
    pick("y2", cfg.y2);
    if (cfg.dateGroup && sel("dateGroup")) sel("dateGroup").value = cfg.dateGroup;
    panel.open = cfg.show !== false;
  }

  async function fill(item, body) {
    body.innerHTML = '<div class="note">Hisoblanmoqda...</div>';
    try {
      const r = await api(`/dashboard/${item.id}/run`, { method: "POST" });
      if (item.kind === "kpi") {
        const value = r.rows.length ? r.rows[0][0] : "—";
        body.innerHTML = `<div class="dashkpi">${esc(value)}</div>`;
        return;
      }
      const more = r.truncated ? " (dastlabki 500 ta)" : "";
      body.innerHTML = `<div class="note">${r.rows.length} qator${more}</div><div class="scroll"><table></table></div>`;
      const table = body.querySelector("table");
      renderTable(table, r.columns, r.rows);
      if (window.DFAttach) {
        window.DFAttach(table);
        applyChart(table, item.chart || {});
      }
    } catch (e) {
      body.innerHTML = `<div class="msg err">${esc(e.message)}</div>`;
    }
  }

  function addPanel(item) {
    const box = document.createElement("div");
    box.dataset.panelId = item.id;
    box.className = "dashpanel";
    const span = Math.max(3, Math.min(12, Number(item.grid?.span) || 6));
    box.style.gridColumn = `span ${span}`;
    box.innerHTML = `<div class="bar"><strong>${esc(item.title)}</strong>
      <span><button class="btn" data-act="up" title="Yuqoriga">↑</button>
      <button class="btn" data-act="down" title="Pastga">↓</button>
      <button class="btn" data-act="size" title="Kengligi">↔</button>
      <button class="btn" data-act="edit">Tahrirlash</button>
      <button class="btn" data-act="refresh">Yangilash</button>
      <button class="btn" data-act="del">O'chirish</button></span></div>
      <details><summary class="note" style="cursor:pointer">SQL</summary><pre class="sql">${esc(item.sql)}</pre></details>
      <div class="dbody"></div>`;
    list.appendChild(box);
    const body = box.querySelector(".dbody");
    fill(item, body);
    box.addEventListener("click", async (e) => {
      const b = e.target.closest("button[data-act]");
      if (!b) return;
      if (b.dataset.act === "refresh") {
        fill(item, body);
      } else if (b.dataset.act === "edit") {
        const title = prompt(translate("Panel nomi:"), item.title);
        if (title === null) return;
        const sql = prompt(translate("Panel SQL:"), item.sql);
        if (sql === null) return;
        try {
          await api(`/dashboard/panels/${item.id}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ...item, title, sql }),
          });
          await loadAll();
        } catch (err) { alert(err.message); }
      } else if (b.dataset.act === "size") {
        item.grid = { ...(item.grid || {}), span: span === 12 ? 6 : span + 3 };
        try {
          await api(`/dashboard/panels/${item.id}`, {
            method: "PUT", headers: { "Content-Type": "application/json" },
            body: JSON.stringify(item),
          });
          await loadAll();
        } catch (err) { alert(err.message); }
      } else if (b.dataset.act === "up" || b.dataset.act === "down") {
        const boxes = Array.from(list.children);
        const index = boxes.indexOf(box);
        const target = b.dataset.act === "up" ? index - 1 : index + 1;
        if (target < 0 || target >= boxes.length) return;
        [boxes[index], boxes[target]] = [boxes[target], boxes[index]];
        try {
          await api("/dashboard/reorder", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ panel_ids: boxes.map((node) => node.dataset.panelId) }),
          });
          await loadAll();
        } catch (err) { alert(err.message); }
      } else if (b.dataset.act === "del" && confirm(`${item.title}: ${translate("panelini o'chirasizmi?")}`)) {
        try {
          await api(`/dashboard/${item.id}`, { method: "DELETE" });
          box.remove();
          updateEmpty();
        } catch (err) {
          alert(err.message);
        }
      }
    });
  }

  async function loadAll() {
    list.innerHTML = "";
    try {
      (await api("/dashboard")).forEach(addPanel);
      await loadFilters();
    } catch (e) {
      list.innerHTML = `<div class="msg err">${esc(e.message)}</div>`;
    }
    updateEmpty();
  }

  async function saveCurrent() {
    const sqlBox = $("sqlResult");
    const sql = $("sql").value.trim();
    if (!sql) return;
    const title = prompt(translate("Panel nomi:"), sql.slice(0, 40));
    if (!title) return;
    let chart = {};
    const panel = sqlBox.querySelector(".chartpanel");
    if (panel) {
      const label = (k) => {
        const s = panel.querySelector(`[data-k="${k}"]`);
        return s && s.selectedIndex >= 0 ? s.options[s.selectedIndex].textContent : null;
      };
      chart = {
        type: panel.querySelector('[data-k="type"]').value,
        x: label("x"), y: label("y"), y2: label("y2"),
        dateGroup: panel.querySelector('[data-k="dateGroup"]').value,
        show: panel.open,
      };
    }
    const active = tables.find((t) => t.file_id === fileId);
    try {
      const kind = confirm(translate("KPI kartochkasi sifatida qo'shilsinmi? (Bekor qilish = grafik/jadval)")) ? "kpi" : "chart";
      const item = await api("/dashboard", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, sql, table: active ? active.table : null, chart, kind, grid: { span: kind === "kpi" ? 3 : 6 } }),
      });
      addPanel(item);
      updateEmpty();
      card.scrollIntoView({ behavior: "smooth" });
    } catch (e) {
      alert(e.message);
    }
  }

  const sqlBox = $("sqlResult");
  new MutationObserver(() => {
    if (sqlBox.querySelector("#sqlTable") && !sqlBox.querySelector("#dashAdd")) {
      const btn = document.createElement("button");
      btn.className = "btn primary";
      btn.id = "dashAdd";
      btn.style.marginLeft = "8px";
      btn.textContent = "Dashboardga qo'shish";
      btn.addEventListener("click", saveCurrent);
      const csv = sqlBox.querySelector("#sqlCsv");
      if (csv) csv.after(btn);
      else sqlBox.appendChild(btn);
    }
  }).observe(sqlBox, { childList: true, subtree: true });

  $("dashRefresh").addEventListener("click", loadAll);
  $("dashApplyFilters").addEventListener("click", () => saveFilters().catch((e) => alert(e.message)));
  $("dashClearFilters").addEventListener("click", async () => {
    document.querySelectorAll("#dashFilters select").forEach((select) => Array.from(select.options).forEach((option) => { option.selected = false; }));
    document.querySelectorAll('#dashFilters input[type="date"]').forEach((input) => { input.value = ""; });
    try { await saveFilters(); } catch (e) { alert(e.message); }
  });
  $("dashExport").addEventListener("click", () => { window.location.href = "/dashboard/export.html"; });
  window.DFReloadDashboard = loadAll;
  loadAll();
})();