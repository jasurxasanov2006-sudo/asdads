(function () {
  "use strict";

  const PALETTE = ["#4f8cff", "#16a34a", "#d97706", "#dc2626", "#0891b2", "#9333ea",
                   "#db2777", "#65a30d", "#ea580c", "#0d9488", "#6366f1", "#a16207"];
  const W = 900, H = 420;
  const TYPES = { bar: "Ustunli", line: "Chiziqli", pie: "Doiraviy" };

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
  const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const cut = (s, n) => (s.length > n ? s.slice(0, n - 3) + "..." : s);
  const fmt = (n) => Number(n).toLocaleString("ru-RU", { maximumFractionDigits: 2 });

  const style = document.createElement("style");
  style.textContent = `
    .chartpanel{margin:0 0 14px;padding:16px;border:1px solid var(--line);border-radius:14px;background:var(--card);box-shadow:0 5px 20px rgba(27,39,68,.045)}
    .chartpanel summary{cursor:pointer;color:var(--accent);font-size:14px;font-weight:650}
    .chartctl{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin:14px 0}
    .chartctl label{font-size:13px;color:var(--muted)}
    .chartctl select{padding:6px 8px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--text);font-size:13px}
    .chartbox{overflow-x:auto}
    .chartbox svg{max-width:100%;height:auto}`;
  document.head.appendChild(style);

  function toNum(v) {
    if (v === null || v === "") return null;
    const n = Number(String(v).replace(/\s/g, ""));
    return Number.isFinite(n) ? n : null;
  }

  function isNumericCol(rows, i) {
    const vals = rows.map((r) => r[i]).filter((v) => v !== null && v !== "");
    return vals.length > 0 && vals.every((v) => toNum(v) !== null);
  }

  function niceMax(v) {
    if (v <= 0) return 1;
    const p = Math.pow(10, Math.floor(Math.log10(v)));
    const f = v / p;
    return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * p;
  }

  function scale(values) {
    const mx = Math.max(...values), mn = Math.min(...values);
    const hi = mx > 0 ? niceMax(mx) : 0;
    const lo = mn < 0 ? -niceMax(-mn) : 0;
    return hi === lo ? [lo, lo + 1] : [lo, hi];
  }

  function axes(lo, hi, c) {
    const m = { left: 80, right: 20, top: 40, bottom: 100 };
    const pw = W - m.left - m.right, ph = H - m.top - m.bottom;
    const y = (v) => m.top + ((hi - v) / (hi - lo)) * ph;
    let grid = "";
    for (let i = 0; i <= 5; i++) {
      const v = lo + ((hi - lo) * i) / 5;
      const yy = y(v);
      grid += `<line x1="${m.left}" y1="${yy}" x2="${m.left + pw}" y2="${yy}" stroke="${c.line}"/>`;
      grid += `<text x="${m.left - 8}" y="${yy + 4}" text-anchor="end" font-size="11" fill="${c.muted}">${esc(fmt(v))}</text>`;
    }
    return { ...m, pw, ph, y, grid };
  }

  function xLabel(text, x, a, c, rotate) {
    const ly = a.top + a.ph + 16;
    return rotate
      ? `<text x="${x}" y="${ly}" text-anchor="end" font-size="11" fill="${c.muted}" transform="rotate(-35 ${x} ${ly})">${esc(cut(text, 16))}</text>`
      : `<text x="${x}" y="${ly}" text-anchor="middle" font-size="11" fill="${c.muted}">${esc(cut(text, 16))}</text>`;
  }

  function bar(labels, values, c) {
    const [lo, hi] = scale(values);
    const a = axes(lo, hi, c);
    const n = values.length, band = a.pw / n, bw = Math.min(band * 0.7, 70);
    const zero = a.y(Math.max(lo, Math.min(hi, 0)));
    let s = a.grid;
    values.forEach((v, i) => {
      const cx = a.left + band * i + band / 2;
      const yy = a.y(v);
      const top = Math.min(yy, zero), h = Math.abs(yy - zero);
      s += `<rect x="${cx - bw / 2}" y="${top}" width="${bw}" height="${Math.max(h, 0.5)}" fill="${PALETTE[0]}" rx="2"><title>${esc(labels[i])}: ${esc(fmt(v))}</title></rect>`;
      if (n <= 12) {
        s += `<text x="${cx}" y="${top - 5}" text-anchor="middle" font-size="11" fill="${c.text}">${esc(fmt(v))}</text>`;
      }
      s += xLabel(labels[i], cx, a, c, n > 8);
    });
    return s;
  }

  function line(labels, values, c) {
    const [lo, hi] = scale(values);
    const a = axes(lo, hi, c);
    const n = values.length;
    const xp = (i) => a.left + (n === 1 ? a.pw / 2 : (a.pw * i) / (n - 1));
    let s = a.grid;
    const pts = values.map((v, i) => `${xp(i).toFixed(1)},${a.y(v).toFixed(1)}`);
    s += `<polyline points="${pts.join(" ")}" fill="none" stroke="${PALETTE[0]}" stroke-width="2"/>`;
    if (n <= 60) {
      values.forEach((v, i) => {
        s += `<circle cx="${xp(i)}" cy="${a.y(v)}" r="3" fill="${PALETTE[0]}"><title>${esc(labels[i])}: ${esc(fmt(v))}</title></circle>`;
      });
    }
    const step = Math.ceil(n / 8);
    labels.forEach((l, i) => {
      if (i % step === 0) s += xLabel(l, xp(i), a, c, true);
    });
    return s;
  }

  function pie(labels, values, c) {
    let items = labels.map((l, i) => ({ l, v: values[i] })).filter((x) => x.v > 0);
    if (!items.length) {
      return `<text x="${W / 2}" y="${H / 2}" text-anchor="middle" fill="${c.muted}">Doiraviy diagramma uchun musbat qiymatlar kerak</text>`;
    }
    items.sort((a, b) => b.v - a.v);
    if (items.length > 12) {
      const rest = items.slice(11).reduce((t, x) => t + x.v, 0);
      items = items.slice(0, 11).concat([{ l: "Boshqalar", v: rest }]);
    }
    const total = items.reduce((t, x) => t + x.v, 0);
    const cx = 300, cy = H / 2 + 15, r = 150;
    let ang = -Math.PI / 2, s = "";
    items.forEach((it, i) => {
      const color = PALETTE[i % PALETTE.length];
      const frac = it.v / total;
      if (frac >= 0.9999) {
        s += `<circle cx="${cx}" cy="${cy}" r="${r}" fill="${color}"/>`;
      } else {
        const a2 = ang + frac * 2 * Math.PI;
        const x1 = cx + r * Math.cos(ang), y1 = cy + r * Math.sin(ang);
        const x2 = cx + r * Math.cos(a2), y2 = cy + r * Math.sin(a2);
        s += `<path d="M${cx} ${cy} L${x1} ${y1} A${r} ${r} 0 ${frac > 0.5 ? 1 : 0} 1 ${x2} ${y2} Z" fill="${color}" stroke="${c.bg}" stroke-width="1"/>`;
        ang = a2;
      }
      const ly = 60 + i * 26;
      s += `<rect x="560" y="${ly - 11}" width="14" height="14" fill="${color}" rx="2"/>`;
      s += `<text x="582" y="${ly}" font-size="13" fill="${c.text}">${esc(cut(it.l, 22))} · ${(frac * 100).toFixed(1)}%</text>`;
    });
    return s;
  }

  function secondaryLine(labels, values, c) {
    const [lo, hi] = scale(values);
    const a = axes(lo, hi, c);
    const xp = (i) => a.left + (values.length === 1 ? a.pw / 2 : (a.pw * i) / (values.length - 1));
    const points = values.map((value, i) => `${xp(i).toFixed(1)},${a.y(value).toFixed(1)}`).join(" ");
    let markup = `<polyline points="${points}" fill="none" stroke="${PALETTE[1]}" stroke-width="2" stroke-dasharray="6 3"/>`;
    if (values.length <= 60) values.forEach((value, i) => {
      markup += `<circle cx="${xp(i)}" cy="${a.y(value)}" r="3" fill="${PALETTE[1]}"><title>${esc(labels[i])}: ${esc(fmt(value))}</title></circle>`;
    });
    for (let i = 0; i <= 5; i++) {
      const value = lo + ((hi - lo) * i) / 5;
      const y = a.top + (a.ph * i) / 5;
      markup += `<text x="${W - 8}" y="${y + 4}" text-anchor="end" font-size="11" fill="${PALETTE[1]}">${esc(fmt(value))}</text>`;
    }
    return markup;
  }

  function build(type, labels, values, title, secondValues) {
    const c = {
      bg: css("--card") || "#ffffff",
      text: css("--text") || "#111111",
      muted: css("--muted") || "#666666",
      line: css("--line") || "#dddddd",
    };
    const body = type === "pie" ? pie(labels, values, c)
      : type === "line" ? line(labels, values, c)
      : bar(labels, values, c);
    return `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" font-family="Segoe UI, Arial, sans-serif">
      <rect width="${W}" height="${H}" fill="${c.bg}"/>
      <text x="${W / 2}" y="24" text-anchor="middle" font-size="15" font-weight="600" fill="${c.text}">${esc(title)}</text>${body}${secondValues ? secondaryLine(labels, secondValues, c) : ""}</svg>`;
  }

  function savePng(svg) {
    const xml = new XMLSerializer().serializeToString(svg);
    const url = URL.createObjectURL(new Blob([xml], { type: "image/svg+xml;charset=utf-8" }));
    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = W * 2;
      canvas.height = H * 2;
      const ctx = canvas.getContext("2d");
      ctx.scale(2, 2);
      ctx.drawImage(img, 0, 0, W, H);
      URL.revokeObjectURL(url);
      canvas.toBlob((blob) => {
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = "grafik.png";
        a.click();
        URL.revokeObjectURL(a.href);
      });
    };
    img.src = url;
  }

  function readTable(table) {
    const head = Array.from(table.querySelectorAll("thead th")).map((th) => th.textContent);
    const rows = Array.from(table.querySelectorAll("tbody tr")).map((tr) =>
      Array.from(tr.children).map((td) => (td.classList.contains("empty") ? null : td.textContent)));
    return { head, rows };
  }

  function attach(table) {
    if (table.dataset.charted) return;
    table.dataset.charted = "1";
    const { head, rows } = readTable(table);
    if (!rows.length) return;
    const yCols = head.map((_, i) => i).filter((i) => isNumericCol(rows, i));
    if (!yCols.length) return;

    const xDefault = head.findIndex((_, i) => !yCols.includes(i));
    const xi = xDefault >= 0 ? xDefault : 0;
    const yi = yCols.find((i) => i !== xi) ?? yCols[0];
    const opt = (i, selected) => `<option value="${i}"${selected ? " selected" : ""}>${esc(head[i])}</option>`;

    const panel = document.createElement("details");
    panel.className = "chartpanel";
    panel.innerHTML = `<summary>Grafik chizish</summary>
      <div class="chartctl">
        <label>Turi <select data-k="type">${Object.entries(TYPES).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select></label>
        <label>X (belgi) <select data-k="x">${head.map((_, i) => opt(i, i === xi)).join("")}</select></label>
        <label>Y (qiymat) <select data-k="y">${yCols.map((i) => opt(i, i === yi)).join("")}</select></label>
        <label>Y2 (o'ng o'q) <select data-k="y2"><option value="">Yo'q</option>${yCols.filter((i) => i !== yi).map((i) => opt(i, false)).join("")}</select></label>
        <label>Sana bo'yicha <select data-k="dateGroup"><option value="">Guruhlamaslik</option><option value="day">Kun</option><option value="month">Oy</option><option value="year">Yil</option></select></label>
        <button class="btn" data-k="zoomIn">Kattalashtirish +</button><button class="btn" data-k="zoomOut">Kichraytirish −</button>
        <button class="btn" data-k="png">PNG yuklab olish</button>
      </div>
      <div class="chartbox"></div>`;
    const workspace = document.getElementById("chartWorkspace");
    if (workspace) workspace.prepend(panel);
    else (table.closest(".scroll") || table).after(panel);

    const box = panel.querySelector(".chartbox");
    const q = (k) => panel.querySelector(`[data-k="${k}"]`);

    let zoom = 1;
    function draw() {
      const type = q("type").value, x = Number(q("x").value), y = Number(q("y").value);
      const y2 = q("y2").value === "" ? -1 : Number(q("y2").value);
      let labels = rows.map((r) => (r[x] === null ? "bo'sh" : r[x]));
      let values = rows.map((r) => toNum(r[y]));
      let secondValues = y2 >= 0 ? rows.map((r) => toNum(r[y2])) : null;
      const grouping = q("dateGroup").value;
      if (grouping) {
        const grouped = new Map();
        labels.forEach((label, i) => {
          const date = new Date(label);
          if (Number.isNaN(date.getTime()) || values[i] === null) return;
          const key = grouping === "year" ? String(date.getFullYear())
            : grouping === "month" ? `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`
            : date.toISOString().slice(0, 10);
          const entry = grouped.get(key) || { sum: 0, count: 0, second: 0, secondCount: 0 };
          entry.sum += values[i];
          entry.count++;
          if (secondValues && secondValues[i] !== null) {
            entry.second += secondValues[i];
            entry.secondCount++;
          }
          grouped.set(key, entry);
        });
        labels = Array.from(grouped.keys()).sort();
        values = labels.map((key) => grouped.get(key).sum);
        if (secondValues) secondValues = labels.map((key) => {
          const entry = grouped.get(key);
          return entry.secondCount ? entry.second : null;
        });
      }
      if (type === "line") {
        const keep = values.map((v, i) => (v !== null && (!secondValues || secondValues[i] !== null) ? i : -1)).filter((i) => i >= 0);
        labels = keep.map((i) => labels[i]);
        values = keep.map((i) => values[i]);
        if (secondValues) secondValues = keep.map((i) => secondValues[i]);
      } else {
        values = values.map((v) => (v === null ? 0 : v));
        if (secondValues) secondValues = secondValues.map((v) => (v === null ? 0 : v));
      }
      const limit = type === "line" ? 500 : 40;
      const sliced = labels.length > limit;
      if (sliced) {
        labels = labels.slice(0, limit);
        values = values.slice(0, limit);
        if (secondValues) secondValues = secondValues.slice(0, limit);
      }
      if (!values.length) {
        box.innerHTML = '<div class="note">Chizish uchun qiymat yo\'q</div>';
        return;
      }
      box.innerHTML = build(type, labels, values, `${head[y]} · ${head[x]} bo'yicha${secondValues ? ` / Y2: ${head[y2]}` : ""}`, secondValues);
      const svg = box.querySelector("svg");
      svg.style.width = `${zoom * 100}%`;
      svg.style.height = `${zoom * H}px`;
      svg.style.cursor = "grab";
      let drag = null;
      svg.onpointerdown = (event) => {
        drag = [event.clientX, event.clientY, box.scrollLeft, box.scrollTop];
        svg.setPointerCapture(event.pointerId);
      };
      svg.onpointermove = (event) => {
        if (!drag) return;
        box.scrollLeft = drag[2] - (event.clientX - drag[0]);
        box.scrollTop = drag[3] - (event.clientY - drag[1]);
      };
      svg.onpointerup = () => { drag = null; };
      if (sliced) box.insertAdjacentHTML("beforeend", `<div class="note">Dastlabki ${limit} ta qator ko'rsatildi.</div>`);
    }

    panel.addEventListener("toggle", () => { if (panel.open) draw(); });
    panel.querySelectorAll("select").forEach((s) => s.addEventListener("change", draw));
    q("zoomIn").addEventListener("click", () => { zoom = Math.min(2.5, zoom + 0.25); draw(); });
    q("zoomOut").addEventListener("click", () => { zoom = Math.max(0.5, zoom - 0.25); draw(); });
    q("png").addEventListener("click", () => {
      const svg = box.querySelector("svg");
      if (svg) savePng(svg);
    });
  }

  function scan() {
    ["sqlTable", "answerTable"].forEach((id) => {
      const t = document.getElementById(id);
      if (t) attach(t);
    });
  }

  window.DFAttach = attach; new MutationObserver(scan).observe(document.body, { childList: true, subtree: true });
})();