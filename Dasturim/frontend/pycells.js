(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const main = document.querySelector("main");
  if (!main || !$("result")) return;

  const HDR = { "Content-Type": "application/json", "X-Dataflow": "1" };
  const STARTER = "# df - faol jadval (pandas DataFrame)\ndf.describe()";
  let pythonMode = null;
  let activeExecutionId = null;
  const executionId = () => (window.crypto && crypto.randomUUID
    ? crypto.randomUUID().replace(/-/g, "")
    : `${Date.now().toString(16)}${Math.random().toString(16).slice(2).padEnd(20, "0")}`.slice(0, 32));

  const style = document.createElement("style");
  style.textContent = `
    .pycell{border:1px solid var(--line);border-radius:10px;padding:10px;margin-bottom:12px}
    .pycode{width:100%;min-height:90px;padding:8px 10px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--text);font-family:Consolas,monospace;font-size:13px;resize:vertical}
    .pyrow{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:6px 0}
    .pymarkdown{background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:10px;white-space:pre-wrap;min-height:44px}
    pre.pyout,pre.pyerr{background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:8px 10px;font-size:12px;white-space:pre-wrap;overflow-x:auto;margin:8px 0}
    pre.pyerr{color:var(--err)}
    .pyai{flex:1;min-width:200px;padding:8px 10px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--text);font-size:13px}`;
  document.head.appendChild(style);

  const card = document.createElement("div");
  card.className = "card nav-view";
  card.id = "view-notebook";
  card.innerHTML = `<h2>Python kataklari</h2>
    <div class="note">Mahalliy rejimda kod localhost'dagi doimiy kerneldan foydalanadi. Server rejimida har bir bajarish alohida, tarmoqsiz Docker konteynerida (30 soniya, 1 GiB xotira, 1 CPU) bajariladi.
      O'zgaruvchilar: <b>df</b> (faol jadval), <b>tables</b> (hamma jadvallar), <b>pd</b>, <b>np</b>.
      Faqat o'zingiz tushungan yoki o'qib chiqqan kodni bajaring. Xavfsizlik siyosati fayl, tarmoq va boshqa jarayon amallarini cheklaydi.</div>
    <div class="pyrow">
      <input class="pyai" id="pyPrompt" type="text" placeholder="AI kod yozsin: masalan, hududlar bo'yicha o'rtacha narxni hisoblab, eng qimmat 5 tasini ko'rsat">
      <button class="btn primary" id="pyAi">AI kod yozsin</button>
    </div>
    <div id="pyAiMsg"></div>
    <div class="pyrow">
      <button class="btn" id="pyAdd">+ Kod katagi</button>
      <button class="btn" id="pyAddMarkdown">+ Markdown</button>
      <button class="btn" id="pyAll">Hammasini bajarish</button>
      <button class="btn" id="pyRestart">Qayta boshlash</button>
      <button class="btn" id="pyStop">To'xtatish</button>
      <button class="btn" id="pyImport">Import (.py/.ipynb)</button>
      <button class="btn" id="pyExport">.py eksport</button>
      <button class="btn" id="pyExportIpynb">.ipynb eksport</button>
      <input id="pyImportFile" type="file" accept=".py,.ipynb" hidden>
      <label class="note" style="margin:0"><input type="checkbox" id="pyAbove" checked>
        Tanlangan katakdan oldingilarini bajarish</label>
    </div>
    <div id="pySaveMsg" class="msg"></div>
    <div id="pyList"></div>`;
  main.insertBefore(card, $("result"));
  const list = $("pyList");

  let saveTimer = null;
  function scheduleSave() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(saveNotebook, 800);
  }

  async function saveNotebook() {
    clearTimeout(saveTimer);
    const cells = Array.from(list.children).map((b) => ({
      id: b.dataset.id,
      type: b.dataset.type,
      code: b.querySelector("textarea").value,
    }));
    try {
      await api("/py/notebook", { method: "POST", headers: HDR, body: JSON.stringify({ cells }) });
      $("pySaveMsg").textContent = "";
      return true;
    } catch (e) {
      $("pySaveMsg").textContent = `Daftar saqlanmadi: ${e.message}`;
      $("pySaveMsg").className = "msg err";
      return false;
    }
  }

  window.DFSaveNotebook = saveNotebook;
  window.DFReloadNotebook = async function () {
    list.innerHTML = "";
    try {
      const cells = await api("/py/notebook", { headers: HDR });
      cells.forEach((c) => addCell(c.code, c.id, c.type));
    } catch (e) {
      $("pyAiMsg").innerHTML = `<div class="msg err">Daftar yuklanmadi: ${esc(e.message)}</div>`;
    }
    if (!list.children.length) addCell(STARTER);
  };

  function markdownHtml(source) {
    return esc(source)
      .replace(/^###### (.+)$/gm, "<h6>$1</h6>")
      .replace(/^##### (.+)$/gm, "<h5>$1</h5>")
      .replace(/^#### (.+)$/gm, "<h4>$1</h4>")
      .replace(/^### (.+)$/gm, "<h3>$1</h3>")
      .replace(/^## (.+)$/gm, "<h2>$1</h2>")
      .replace(/^# (.+)$/gm, "<h1>$1</h1>")
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/\*(.+?)\*/g, "<em>$1</em>")
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\n/g, "<br>");
  }

  function addCell(code, id, type = "code", insertBefore = null) {
    const box = document.createElement("div");
    box.className = "pycell";
    box.dataset.id = id || Math.random().toString(36).slice(2, 10);
    box.dataset.type = type === "markdown" ? "markdown" : "code";
    box.innerHTML = `<div class="pyrow">
        <strong data-role="kind"></strong>
        <button class="btn" data-act="up" title="Yuqoriga">↑</button>
        <button class="btn" data-act="down" title="Pastga">↓</button>
        <button class="btn" data-act="copy">Nusxalash</button>
        <button class="btn" data-act="edit" hidden>Tahrirlash</button>
      </div>
      <textarea class="pycode" spellcheck="false" aria-label="Katak matni"></textarea>
      <div class="pymarkdown" data-role="markdown" hidden></div>
      <div class="pyrow">
        <button class="btn primary" data-act="run">Bajarish (Shift+Enter)</button>
        <button class="btn" data-act="del">O'chirish</button>
      </div>
      <div data-role="out"></div>`;
    const ta = box.querySelector("textarea");
    ta.value = code || "";
    ta.rows = Math.max(3, ta.value.split("\n").length + 1);
    box.querySelector('[data-role="kind"]').textContent = box.dataset.type === "code" ? "Python" : "Markdown";
    if (box.dataset.type === "markdown") {
      ta.hidden = true;
      box.querySelector('[data-role="markdown"]').hidden = false;
      box.querySelector('[data-role="markdown"]').innerHTML = markdownHtml(ta.value);
      box.querySelector('[data-act="run"]').hidden = true;
      box.querySelector('[data-act="edit"]').hidden = false;
    }
    list.insertBefore(box, insertBefore);
    return box;
  }

  function renderOut(out, r) {
    let html = "";
    if (r.stdout) html += `<pre class="pyout">${esc(r.stdout)}</pre>`;
    if (r.result && r.result.kind === "table") {
      const t = r.result;
      const more = t.truncated ? " (dastlabki 500 ta ko'rsatildi)" : "";
      html += `<div class="note">${t.total} qator × ${t.columns.length} ustun${more}</div>
        <div class="scroll"><table class="pytable"></table></div>`;
    } else if (r.result && r.result.kind === "text") {
      html += `<pre class="pyout">${esc(r.result.text)}</pre>`;
    }
    for (const image of (r.images || [])) {
      html += `<img alt="Python grafigi" style="max-width:100%;height:auto" src="data:image/png;base64,${image}">`;
    }
    if (r.error) {
      html += `<pre class="pyerr">${esc(r.error)}</pre>
        <button class="btn" data-act="fix">AI tushuntirsin va tuzatsin</button><div data-role="fix"></div>`;
    }
    html += `<div class="note">${r.seconds} s</div>`;
    out.innerHTML = html;
    out.dataset.error = r.error || "";
    const table = out.querySelector("table.pytable");
    if (table) {
      renderTable(table, r.result.columns, r.result.rows);
      if (window.DFAttach) window.DFAttach(table);
    }
  }

  async function executeCell(box, before = []) {
    if (box.dataset.type !== "code") return true;
    const code = box.querySelector("textarea").value;
    const out = box.querySelector('[data-role="out"]');
    const btn = box.querySelector('[data-act="run"]');
    const id = executionId();
    activeExecutionId = id;
    btn.disabled = true;
    out.innerHTML = '<div class="note">Bajarilmoqda...</div>';
    try {
      const r = await api("/py/run", {
        method: "POST",
        headers: HDR,
        body: JSON.stringify({ code, before, execution_id: id, active_id: typeof fileId === "undefined" ? null : fileId }),
      });
      renderOut(out, r);
      return !r.error;
    } catch (e) {
      out.innerHTML = `<pre class="pyerr">${esc(e.message)}</pre>`;
      return false;
    } finally {
      btn.disabled = false;
      if (activeExecutionId === id) activeExecutionId = null;
    }
  }

  async function runCell(box) {
    const boxes = Array.from(list.children);
    const idx = boxes.indexOf(box);
    try {
      pythonMode = pythonMode || (await api("/py/mode")).mode;
    } catch (e) {
      $("pySaveMsg").textContent = e.message;
      $("pySaveMsg").className = "msg err";
      return;
    }
    if (pythonMode === "docker") {
      const before = $("pyAbove").checked
        ? boxes.slice(0, idx).filter((prior) => prior.dataset.type === "code").map((prior) => prior.querySelector("textarea").value)
        : [];
      await executeCell(box, before);
    } else {
      if ($("pyAbove").checked) {
        for (const prior of boxes.slice(0, idx)) {
          if (prior.dataset.type === "code" && !(await executeCell(prior))) return;
        }
      }
      await executeCell(box);
    }
  }

  async function downloadNotebook(path, name) {
    try {
      const response = await fetch(path, { headers: { "X-Dataflow": "1" } });
      if (!response.ok) throw new Error(`Eksport amalga oshmadi (HTTP ${response.status})`);
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = name;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      $("pySaveMsg").textContent = e.message;
      $("pySaveMsg").className = "msg err";
    }
  }

  async function fixCell(box) {
    const ta = box.querySelector("textarea");
    const out = box.querySelector('[data-role="out"]');
    const slot = out.querySelector('[data-role="fix"]');
    slot.innerHTML = '<div class="note">AI tahlil qilyapti...</div>';
    try {
      const r = await api("/py/ai", {
        method: "POST",
        headers: HDR,
        body: JSON.stringify({
          task: "fix",
          code: ta.value,
          error: out.dataset.error || "",
          active_id: typeof fileId === "undefined" ? null : fileId,
        }),
      });
      slot.innerHTML = `<p>${esc(r.explanation)}</p><pre class="pyout">${esc(r.code)}</pre>
        <button class="btn primary">Tuzatilgan kodni katakka qo'yish</button>`;
      slot.querySelector("button").addEventListener("click", () => {
        ta.value = r.code;
        ta.rows = Math.max(3, r.code.split("\n").length + 1);
        scheduleSave();
      });
    } catch (e) {
      slot.innerHTML = `<div class="msg err">${esc(e.message)}</div>`;
    }
  }

  async function aiWrite() {
    const prompt = $("pyPrompt").value.trim();
    if (!prompt) return;
    const msg = $("pyAiMsg");
    const btn = $("pyAi");
    btn.disabled = true;
    msg.innerHTML = '<div class="note">AI kod yozyapti...</div>';
    try {
      const r = await api("/py/ai", {
        method: "POST",
        headers: HDR,
        body: JSON.stringify({
          task: "write",
          prompt,
          active_id: typeof fileId === "undefined" ? null : fileId,
        }),
      });
      const box = addCell(r.code);
      box.querySelector('[data-role="out"]').innerHTML =
        `<div class="note">AI: ${esc(r.explanation)} Kodni o'qib chiqing, keyin bajaring.</div>`;
      msg.innerHTML = "";
      scheduleSave();
      box.scrollIntoView({ behavior: "smooth", block: "center" });
    } catch (e) {
      msg.innerHTML = `<div class="msg err">${esc(e.message)}</div>`;
    } finally {
      btn.disabled = false;
    }
  }

  list.addEventListener("click", (e) => {
    const b = e.target.closest("button[data-act]");
    if (!b) return;
    const box = b.closest(".pycell");
    if (b.dataset.act === "run") runCell(box);
    else if (b.dataset.act === "fix") fixCell(box);
    else if (b.dataset.act === "del") {
      box.remove();
      scheduleSave();
    } else if (b.dataset.act === "copy") {
      addCell(box.querySelector("textarea").value, null, box.dataset.type, box.nextElementSibling);
      scheduleSave();
    } else if (b.dataset.act === "edit") {
      const editing = box.querySelector("textarea").hidden;
      box.querySelector("textarea").hidden = !editing;
      box.querySelector('[data-role="markdown"]').hidden = editing;
      b.textContent = editing ? "Ko'rish" : "Tahrirlash";
      if (editing) box.querySelector("textarea").focus();
    } else if (b.dataset.act === "up" && box.previousElementSibling) {
      list.insertBefore(box, box.previousElementSibling);
      scheduleSave();
    } else if (b.dataset.act === "down" && box.nextElementSibling) {
      list.insertBefore(box.nextElementSibling, box);
      scheduleSave();
    }
  });

  list.addEventListener("input", (e) => {
    const box = e.target.closest(".pycell");
    if (box && box.dataset.type === "markdown") {
      box.querySelector('[data-role="markdown"]').innerHTML = markdownHtml(e.target.value);
    }
    scheduleSave();
  });

  list.addEventListener("keydown", (e) => {
    const ta = e.target.closest("textarea.pycode");
    if (!ta) return;
    if (e.key === "Tab") {
      e.preventDefault();
      ta.setRangeText("    ", ta.selectionStart, ta.selectionEnd, "end");
      scheduleSave();
    } else if (e.key === "Enter" && e.shiftKey) {
      e.preventDefault();
      runCell(ta.closest(".pycell"));
    }
  });

  $("pyAdd").addEventListener("click", () => {
    const box = addCell("");
    box.querySelector("textarea").focus();
    scheduleSave();
  });
  $("pyAddMarkdown").addEventListener("click", () => {
    const box = addCell("", null, "markdown");
    box.querySelector("textarea").focus();
    scheduleSave();
  });

  $("pyAll").addEventListener("click", async () => {
    const boxes = Array.from(list.children);
    try {
      pythonMode = pythonMode || (await api("/py/mode")).mode;
    } catch (e) {
      $("pySaveMsg").textContent = e.message;
      $("pySaveMsg").className = "msg err";
      return;
    }
    for (let index = 0; index < boxes.length; index += 1) {
      const box = boxes[index];
      if (box.dataset.type !== "code") continue;
      const before = pythonMode === "docker"
        ? boxes.slice(0, index).filter((prior) => prior.dataset.type === "code").map((prior) => prior.querySelector("textarea").value)
        : [];
      if (!(await executeCell(box, before))) break;
    }
  });

  $("pyRestart").addEventListener("click", async () => {
    try {
      await api("/py/restart", { method: "POST", headers: HDR, body: "{}" });
      $("pySaveMsg").textContent = "Kernel qayta ishga tushirildi; o'zgaruvchilar tozalandi.";
      $("pySaveMsg").className = "msg ok";
    } catch (e) {
      $("pySaveMsg").textContent = e.message;
      $("pySaveMsg").className = "msg err";
    }
  });
  $("pyStop").addEventListener("click", async () => {
    if (!activeExecutionId) {
      $("pySaveMsg").textContent = "Faol bajarish yo'q.";
      $("pySaveMsg").className = "msg";
      return;
    }
    try {
      const result = await api("/py/interrupt", {
        method: "POST", headers: HDR, body: JSON.stringify({ execution_id: activeExecutionId }),
      });
      $("pySaveMsg").textContent = result.interrupted ? "Bajarish to'xtatildi." : "Faol bajarish yo'q.";
      $("pySaveMsg").className = "msg";
    } catch (e) {
      $("pySaveMsg").textContent = e.message;
      $("pySaveMsg").className = "msg err";
    }
  });
  $("pyExport").addEventListener("click", () => downloadNotebook("/py/export.py", "notebook.py"));
  $("pyExportIpynb").addEventListener("click", () => downloadNotebook("/py/export.ipynb", "notebook.ipynb"));
  $("pyImport").addEventListener("click", () => $("pyImportFile").click());
  $("pyImportFile").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    try {
      const response = await fetch("/py/import", { method: "POST", headers: { "X-Dataflow": "1" }, body: form });
      if (!response.ok) {
        let detail = `Import amalga oshmadi (HTTP ${response.status})`;
        try { detail = (await response.json()).detail || detail; } catch {}
        throw new Error(detail);
      }
      const result = await response.json();
      list.innerHTML = "";
      result.cells.forEach((c) => addCell(c.code, c.id, c.type));
      $("pySaveMsg").textContent = `${result.cells.length} ta katak import qilindi.`;
      $("pySaveMsg").className = "msg ok";
    } catch (err) {
      $("pySaveMsg").textContent = err.message;
      $("pySaveMsg").className = "msg err";
    } finally {
      e.target.value = "";
    }
  });

  $("pyAi").addEventListener("click", aiWrite);
  $("pyPrompt").addEventListener("keydown", (e) => { if (e.key === "Enter") aiWrite(); });

  (async function init() {
    await window.DFReloadNotebook();
  })();
})();