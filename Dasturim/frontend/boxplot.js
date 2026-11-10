(function () {
  "use strict";

  const W = 920;
  const H = 460;
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
  const cut = (s, n) => { s = String(s); return s.length > n ? s.slice(0, n - 3) + "..." : s; };
  const fmt = (n) => Number(n).toLocaleString("ru-RU", { maximumFractionDigits: 2 });
  const short = (n) => {
    const a = Math.abs(n);
    if (a >= 1e9) return +(n / 1e9).toFixed(2) + " mlrd";
    if (a >= 1e6) return +(n / 1e6).toFixed(2) + " mln";
    return fmt(n);
  };
  const qid = (n) => '"' + String(n).replace(/"/g, '""') + '"';

  function colors(resolved) {
    if (!resolved) {
      return { bg: "var(--card, #ffffff)", text: "var(--text, #111111)", muted: "var(--muted, #667085)", line: "var(--line, #dddddd)", accent: "var(--accent, #4f6bed)" };
    }
    const css = (n, d) => getComputedStyle(document.documentElement).getPropertyValue(n).trim() || d;
    return { bg: css("--card", "#ffffff"), text: css("--text", "#111111"), muted: css("--muted", "#667085"), line: css("--line", "#dddddd"), accent: css("--accent", "#4f6bed") };
  }

  const txt = (x, y, s, o) =>
    `<text x="${x}" y="${y}" text-anchor="${o.anchor || "middle"}" style="fill:${o.fill};font-size:${o.size || 11}px;${o.weight ? "font-weight:" + o.weight + ";" : ""}"${o.rotate ? ` transform="rotate(${o.rotate} ${x} ${y})"` : ""}>${esc(s)}</text>`;

  function niceTicks(min, max) {
    if (!(max > min)) max = min + 1;
    const raw = (max - min) / 5;
    const p = Math.pow(10, Math.floor(Math.log10(raw)));
    const f = raw / p;
    const step = (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * p;
    const lo = Math.floor(min / step) * step;
    const hi = Math.ceil(max / step) * step;
    const ticks = [];
    for (let v = lo; v <= hi + step / 2; v += step) ticks.push(Math.round(v / step) * step);
    return { lo, hi, ticks };
  }

  // spec: { title, groups: [{ name, n, q1, med, q3, lo, hi, outs: [sonlar] }] }
  function build(spec, resolved) {
    const c = colors(resolved);
    const groups = spec.groups || [];
    if (!groups.length) return '<div class="note">Boxplot uchun ma\'lumot yo\'q</div>';

    const all = [];
    groups.forEach((g) => {
      all.push(g.lo, g.hi);
      (g.outs || []).forEach((v) => all.push(v));
    });
    const nums = all.filter((v) => Number.isFinite(v));
    const t = niceTicks(Math.min(...nums), Math.max(...nums));
    const labels = t.ticks.map(short);
    const left = Math.max(60, 16 + 7 * Math.max(...labels.map((s) => s.length)));
    const m = { left, right: 24, top: 56, bottom: groups.length > 6 ? 112 : 72 };
    const pw = W - m.left - m.right;
    const ph = H - m.top - m.bottom;
    const y = (v) => m.top + ((t.hi - v) / (t.hi - t.lo)) * ph;
    const band = pw / groups.length;
    const bw = Math.min(band * 0.5, 72);
    const rot = groups.length > 6;

    let s = "";
    t.ticks.forEach((v, i) => {
      const yy = y(v);
      s += `<line x1="${m.left}" y1="${yy}" x2="${m.left + pw}" y2="${yy}" style="stroke:${c.line};stroke-width:1" stroke-dasharray="3 4"/>`;
      s += txt(m.left - 8, yy + 4, labels[i], { anchor: "end", fill: c.muted });
    });

    groups.forEach((g, i) => {
      const cx = m.left + band * i + band / 2;
      const tip = `${g.name}\nn = ${g.n}\nQ1: ${fmt(g.q1)}\nMedian: ${fmt(g.med)}\nQ3: ${fmt(g.q3)}\nMo'ylov: ${fmt(g.lo)} ... ${fmt(g.hi)}\nG'ayritabiiy: ${g.outCount ?? (g.outs || []).length}`;
      const yq1 = y(g.q1), yq3 = y(g.q3), ymed = y(g.med);
      s += `<g><title>${esc(tip)}</title>`;
      s += `<line x1="${cx}" y1="${y(g.hi)}" x2="${cx}" y2="${yq3}" style="stroke:${c.accent};stroke-width:2"/>`;
      s += `<line x1="${cx}" y1="${yq1}" x2="${cx}" y2="${y(g.lo)}" style="stroke:${c.accent};stroke-width:2"/>`;
      s += `<line x1="${cx - bw / 4}" y1="${y(g.hi)}" x2="${cx + bw / 4}" y2="${y(g.hi)}" style="stroke:${c.accent};stroke-width:2"/>`;
      s += `<line x1="${cx - bw / 4}" y1="${y(g.lo)}" x2="${cx + bw / 4}" y2="${y(g.lo)}" style="stroke:${c.accent};stroke-width:2"/>`;
      s += `<rect x="${cx - bw / 2}" y="${yq3}" width="${bw}" height="${Math.max(yq1 - yq3, 1)}" rx="4" style="fill:${c.accent};fill-opacity:.28;stroke:${c.accent};stroke-width:2"/>`;
      s += `<line x1="${cx - bw / 2}" y1="${ymed}" x2="${cx + bw / 2}" y2="${ymed}" style="stroke:${c.text};stroke-width:3"/>`;
      (g.outs || []).forEach((v, k) => {
        const jitter = ((k % 7) - 3) * 3;
        s += `<circle cx="${cx + jitter}" cy="${y(v)}" r="3" style="fill:#ef4444;fill-opacity:.6"/>`;
      });
      s += "</g>";
      const ly = m.top + ph + 18;
      s += txt(cx, ly, `${cut(g.name, rot ? 18 : 14)}`, { anchor: rot ? "end" : "middle", fill: c.muted, rotate: rot ? -35 : 0 });
    });

    s += txt(W / 2, H - 10, "Quti: Q1-Q3 · qora chiziq: median · mo'ylov: 1.5 x IQR · qizil nuqta: g'ayritabiiy qiymat", { fill: c.muted, size: 11 });
    return `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" font-family="Segoe UI, Arial, sans-serif"${resolved ? "" : ' style="max-width:100%;height:auto"'}>` +
      `<rect width="${W}" height="${H}" rx="14" style="fill:${c.bg}"/>` +
      txt(W / 2, 30, spec.title || "Boxplot", { fill: c.text, size: 16, weight: 600 }) + s + "</svg>";
  }

  function draw(el, spec) {
    el.innerHTML = build(spec, false);
  }

  function png(spec) {
    const xml = build(spec, true);
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
        a.download = "boxplot.png";
        a.click();
        URL.revokeObjectURL(a.href);
      });
    };
    img.src = url;
  }

  // ctx.runSql(sql) -> Promise<{columns, rows}>, SQL faqat SELECT/WITH; jadval nomi: data
  async function fetchSpec(ctx, cat, val) {
    const v = qid(val);
    const g = cat ? `CAST(${qid(cat)} AS VARCHAR)` : "'Hammasi'";
    const where = `${v} IS NOT NULL` + (cat ? ` AND ${qid(cat)} IS NOT NULL` : "");
    const base =
      `WITH s AS (SELECT ${g} AS g, ${v} AS v FROM data WHERE ${where}), ` +
      `tg AS (SELECT g FROM s GROUP BY g ORDER BY COUNT(*) DESC LIMIT 12), ` +
      `q AS (SELECT g, COUNT(*) AS n, quantile_cont(v, 0.25) AS q1, quantile_cont(v, 0.5) AS med, ` +
      `quantile_cont(v, 0.75) AS q3 FROM s WHERE g IN (SELECT g FROM tg) GROUP BY g) `;
    const fence = "(q.q3 - q.q1)";
    const stats = await ctx.runSql(
      base +
        `SELECT q.g, q.n, q.q1, q.med, q.q3, ` +
        `(SELECT MIN(s.v) FROM s WHERE s.g = q.g AND s.v >= q.q1 - 1.5 * ${fence}) AS lo, ` +
        `(SELECT MAX(s.v) FROM s WHERE s.g = q.g AND s.v <= q.q3 + 1.5 * ${fence}) AS hi, ` +
        `(SELECT COUNT(*) FROM s WHERE s.g = q.g AND (s.v < q.q1 - 1.5 * ${fence} OR s.v > q.q3 + 1.5 * ${fence})) AS outs ` +
        `FROM q ORDER BY q.n DESC`
    );
    const outs = await ctx.runSql(
      base +
        `SELECT s.g, s.v FROM s JOIN q ON s.g = q.g ` +
        `WHERE s.v < q.q1 - 1.5 * ${fence} OR s.v > q.q3 + 1.5 * ${fence} ORDER BY random() LIMIT 400`
    );
    const byGroup = {};
    outs.rows.forEach((r) => { (byGroup[r[0]] = byGroup[r[0]] || []).push(Number(r[1])); });
    const groups = stats.rows.map((r) => ({
      name: String(r[0]),
      n: Number(r[1]),
      q1: Number(r[2]),
      med: Number(r[3]),
      q3: Number(r[4]),
      lo: Number(r[5]),
      hi: Number(r[6]),
      outCount: Number(r[7]),
      outs: byGroup[r[0]] || [],
    }));
    return { title: cat ? `${val} · ${cat} bo'yicha (boxplot)` : `${val} (boxplot)`, groups };
  }

  // ctx.getColumns() -> [{ name, type: "number" | "text" | "date" }]
  function mount(el, ctx) {
    const cols = ctx.getColumns();
    const nums = cols.filter((c) => c.type === "number");
    const cats = cols.filter((c) => c.type !== "number");
    if (!nums.length) {
      el.innerHTML = '<div class="note">Boxplot uchun kamida bitta raqamli ustun kerak</div>';
      return;
    }
    const opts = (list) => list.map((c) => `<option value="${esc(c.name)}">${esc(c.name)}</option>`).join("");
    const sel = "padding:8px 10px;border:1px solid var(--line,#ddd);border-radius:10px;background:var(--bg,#fff);color:var(--text,#111);font-size:13px";
    el.innerHTML =
      `<div style="display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end;margin-bottom:10px">` +
      `<label style="display:flex;flex-direction:column;gap:4px;font-size:12px;color:var(--muted,#667)">Qiymat (raqamli)<select class="bxv" style="${sel}">${opts(nums)}</select></label>` +
      `<label style="display:flex;flex-direction:column;gap:4px;font-size:12px;color:var(--muted,#667)">Guruhlash (ixtiyoriy)<select class="bxc" style="${sel}"><option value="">- hammasi birga -</option>${opts(cats)}</select></label>` +
      `<button class="btn primary bxgo">Chizish</button><button class="btn bxpng">PNG</button></div>` +
      `<div class="bxmsg"></div><div class="bxout" style="overflow-x:auto"></div>`;

    let last = null;
    const msg = el.querySelector(".bxmsg");
    const out = el.querySelector(".bxout");

    async function run() {
      msg.innerHTML = '<div class="note">Hisoblanmoqda...</div>';
      try {
        last = await fetchSpec(ctx, el.querySelector(".bxc").value, el.querySelector(".bxv").value);
        msg.innerHTML = "";
        draw(out, last);
      } catch (e) {
        msg.innerHTML = `<div class="msg err">${esc(e.message || e)}</div>`;
      }
    }
    el.querySelector(".bxgo").addEventListener("click", run);
    el.querySelector(".bxpng").addEventListener("click", () => { if (last) png(last); });
    run();
  }

  window.DFBox = { mount, build, draw, png, fetchSpec };
})();