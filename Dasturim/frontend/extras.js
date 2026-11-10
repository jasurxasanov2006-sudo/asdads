(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const translate = (text) => window.DFTranslate ? window.DFTranslate(text) : text;
  const headers = { "Content-Type": "application/json", "X-Dataflow": "1" };
  let templateItems = [];
  let reportLogoData = "";
  const message = (text, kind) => {
    $("extraMessage").textContent = text || "";
    $("extraMessage").className = "msg " + (kind || "");
  };

  function refreshColumns() {
    const select = $("extraColumn");
    const columns = (typeof lastColumns === "undefined" ? [] : lastColumns)
      .filter((column) => column.type === "number");
    select.innerHTML = columns.length
      ? columns.map((column) => `<option value="${esc(column.name)}">${esc(column.name)}</option>`).join("")
      : '<option value="">Raqamli ustun yo\'q</option>';
  }
  window.DFExtrasRefresh = function () {
    refreshColumns();
    refreshReportSettings();
    renderTemplateGallery();
  };

  async function download(path, filename) {
    const response = await fetch(path);
    if (!response.ok) {
      let detail = `Xatolik (HTTP ${response.status})`;
      try {
        const body = await response.json();
        if (typeof body.detail === "string") detail = body.detail;
      } catch {}
      throw new Error(detail);
    }
    const blob = await response.blob();
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    link.click();
    URL.revokeObjectURL(link.href);
  }

  $("extraReport").addEventListener("click", async () => {
    if (!fileId) return message("Avval jadval tanlang.", "err");
    try {
      await download(`/files/${fileId}/report.html`, "dataflow_hisobot.html");
      message("HTML hisoboti yuklab olindi.", "ok");
    } catch (e) { message(e.message, "err"); }
  });

  $("extraPdf").addEventListener("click", () => {
    if (!fileId) return message("Avval jadval tanlang.", "err");
    const report = window.open(`/files/${fileId}/report.html?print=1`, "_blank");
    if (!report) message("Hisobot oynasi bloklandi. Brauzerda popup'ga ruxsat bering.", "err");
    else message("Hisobot ochildi. Undagi “PDF chop etish” tugmasi orqali PDF saqlang.", "ok");
  });

  $("extraExcel").addEventListener("click", async () => {
    if (!fileId) return message("Avval jadval tanlang.", "err");
    try {
      await download(`/files/${fileId}/download.xlsx`, "dataflow_tozalangan.xlsx");
      message("Excel fayli yuklab olindi.", "ok");
    } catch (e) { message(e.message, "err"); }
  });

  async function refreshReportSettings() {
    try {
      const settings = await api("/report-settings");
      $("reportTitle").value = settings.title || "DataFlow AI hisoboti";
      $("reportTime").value = settings.schedule_time || "02:00";
      $("reportSchedule").checked = Boolean(settings.schedule_enabled);
      $("reportAutoSave").checked = Boolean(settings.auto_save);
      reportLogoData = settings.logo || "";
      $("reportSettingsMessage").textContent = settings.last_error
        ? `Oxirgi yangilash xatosi: ${settings.last_error}`
        : settings.last_run ? `Oxirgi yangilash: ${settings.last_run}` : "Hali avtomatik yangilash bajarilmagan.";
      await refreshSavedReports();
    } catch (error) {
      $("reportSettingsMessage").textContent = error.message;
    }
  }

  async function refreshSavedReports() {
    const reports = await api("/reports/saved");
    $("savedReports").innerHTML = reports.length
      ? `<strong>Saqlangan hisobotlar:</strong> ${reports.map((item) =>
        `<a href="/reports/saved/${encodeURIComponent(item.name)}" target="_blank" rel="noopener">${esc(item.name)}</a>`
      ).join(" · ")}`
      : "Saqlangan hisobotlar yo'q.";
  }

  $("reportLogo").addEventListener("change", (event) => {
    const file = event.target.files[0];
    if (!file) return;
    if (file.size > 512 * 1024) {
      event.target.value = "";
      message("Logotip hajmi 512 KB dan oshmasin.", "err");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => { reportLogoData = String(reader.result || ""); };
    reader.onerror = () => message("Logotip faylini o'qib bo'lmadi.", "err");
    reader.readAsDataURL(file);
  });

  $("reportSettingsSave").addEventListener("click", async () => {
    const button = $("reportSettingsSave");
    button.disabled = true;
    try {
      const settings = await api("/report-settings", {
        method: "PUT",
        headers,
        body: JSON.stringify({
          title: $("reportTitle").value,
          logo: reportLogoData,
          schedule_enabled: $("reportSchedule").checked,
          schedule_time: $("reportTime").value || "02:00",
          auto_save: $("reportAutoSave").checked,
        }),
      });
      $("reportSettingsMessage").textContent =
        `Sozlamalar saqlandi. Kunlik yangilash ${settings.schedule_enabled ? `yoqilgan (${settings.schedule_time})` : "o'chiq"}.`;
      await refreshSavedReports();
    } catch (error) {
      $("reportSettingsMessage").textContent = error.message;
    } finally {
      button.disabled = false;
    }
  });

  $("reportRefreshNow").addEventListener("click", async () => {
    const button = $("reportRefreshNow");
    button.disabled = true;
    try {
      const result = await api("/reports/refresh", { method: "POST", headers });
      $("reportSettingsMessage").textContent =
        `${result.updated} ta jadval hisoboti yangilandi: ${result.last_run}`;
      await refreshSavedReports();
    } catch (error) {
      $("reportSettingsMessage").textContent = error.message;
    } finally {
      button.disabled = false;
    }
  });

  function renderTemplateGallery() {
    const root = $("templateGallery");
    if (!root || !templateItems.length) return;
    root.innerHTML = templateItems.map((template) => {
      const fields = template.fields.map((field) => {
        const options = lastColumns
          .filter((column) => column.type === field.kind || (field.optional && column.type === "empty"))
          .map((column) => `<option value="${esc(column.name)}">${esc(column.name)}</option>`)
          .join("");
        return `<label>${esc(field.label)}
          <select data-field="${esc(field.id)}">
            ${field.optional ? '<option value="">Tanlanmagan</option>' : ""}
            ${options || (!field.optional ? '<option value="">Mos ustun topilmadi</option>' : "")}
          </select></label>`;
      }).join("");
      return `<article class="card" data-template="${esc(template.id)}">
        <div class="note">${esc(template.category)}</div><h3>${esc(template.title)}</h3>
        <p>${esc(template.description)}</p><div class="clean-form">${fields}</div>
        <button class="btn primary" data-template-run="${esc(template.id)}" ${fileId ? "" : "disabled"}>Tekshiruvni hisoblash</button>
      </article>`;
    }).join("");
  }

  async function loadTemplates() {
    try {
      templateItems = await api("/templates");
      renderTemplateGallery();
    } catch (error) {
      $("templateGallery").textContent = `Shablonlarni yuklab bo'lmadi: ${error.message}`;
    }
  }

  $("templateGallery").addEventListener("click", async (event) => {
    const button = event.target.closest("[data-template-run]");
    if (!button) return;
    if (!fileId) return message("Avval jadval tanlang.", "err");
    const card = button.closest("[data-template]");
    const columns = {};
    card.querySelectorAll("[data-field]").forEach((select) => {
      if (select.value) columns[select.dataset.field] = select.value;
    });
    const output = $("templateResult");
    button.disabled = true;
    output.innerHTML = '<div class="note">Shablon hisoblanmoqda...</div>';
    try {
      const result = await api(`/templates/${encodeURIComponent(button.dataset.templateRun)}/run`, {
        method: "POST",
        headers,
        body: JSON.stringify({ file_id: fileId, columns }),
      });
      output.innerHTML = `<div class="card"><h3>${esc(result.template.title)} — tekshirish natijasi</h3>
        <p class="note">${esc(result.notice)}</p><div class="scroll"><table data-template-table></table></div>
        <details><summary>SQL namunasi</summary><pre class="sql">${esc(result.sql)}</pre></details>
        <details><summary>Python namunasi</summary><pre class="sql">${esc(result.python)}</pre></details></div>`;
      renderTable(output.querySelector("[data-template-table]"), result.columns, result.rows);
    } catch (error) {
      output.innerHTML = `<div class="msg err">${esc(error.message)}</div>`;
    } finally {
      button.disabled = false;
    }
  });

  async function outliers(action) {
    if (!fileId) return message("Avval jadval tanlang.", "err");
    const column = $("extraColumn").value;
    if (!column) return message("Raqamli ustun tanlang.", "err");
    if (action !== "preview" && !confirm(translate("Bu amal yangi tozalash versiyasini saqlaydi. Davom etasizmi?"))) return;
    const result = $("extraOutlierResult");
    result.textContent = "Tekshirilmoqda...";
    try {
      const response = await api(`/files/${fileId}/outliers`, {
        method: "POST",
        headers,
        body: JSON.stringify({ column, k: Number($("extraK").value), action }),
      });
      result.textContent = `${response.count} ta g'ayritabiiy qiymat topildi (${response.pct}%). ` +
        `Chegaralar: ${response.lo} – ${response.hi}.` +
        (response.applied ? " O'zgarish saqlandi." : "");
      if (response.applied) {
        await openFile(fileId);
        await refreshTables();
      }
    } catch (e) { result.textContent = e.message; }
  }

  document.querySelectorAll("[data-outlier]").forEach((button) => {
    button.addEventListener("click", () => outliers(button.dataset.outlier));
  });

  $("extraImportUrl").addEventListener("click", async () => {
    const url = $("extraUrl").value.trim();
    if (!url) return message("Havolani kiriting.", "err");
    message("Havoladan yuklanmoqda...");
    try {
      const result = await api("/import/url", {
        method: "POST",
        headers,
        body: JSON.stringify({ url }),
      });
      await refreshTables(result.file_id);
      $("extraUrl").value = "";
      message(`${result.rows} qatorli jadval import qilindi.`, "ok");
    } catch (e) { message(e.message, "err"); }
  });

  $("extraImportDb").addEventListener("click", async () => {
    const payload = {
      kind: $("extraDbKind").value,
      host: $("extraDbHost").value.trim(),
      port: $("extraDbPort").value ? Number($("extraDbPort").value) : null,
      database: $("extraDbName").value.trim(),
      user: $("extraDbUser").value.trim(),
      password: $("extraDbPassword").value,
      query: $("extraDbQuery").value.trim(),
    };
    if (!payload.host || !payload.database || !payload.user || !payload.query) {
      return message("Server, baza, foydalanuvchi va SELECT so'rovini kiriting.", "err");
    }
    message("Bazaga ulanmoqda...");
    try {
      const result = await api("/import/db", {
        method: "POST",
        headers,
        body: JSON.stringify(payload),
      });
      $("extraDbPassword").value = "";
      await refreshTables(result.file_id);
      message(`${result.rows} qator import qilindi${result.truncated ? " (limitga yetdi)" : ""}.`, "ok");
    } catch (e) { message(e.message, "err"); }
  });

  async function refreshBackups() {
    const items = await api("/backups");
    $("extraBackups").innerHTML = items.length
      ? items.map((item) => `<li>${esc(item.name)} (${item.mb} MB)</li>`).join("")
      : "<li>Zaxira nusxasi yo'q.</li>";
  }

  $("extraBackup").addEventListener("click", async () => {
    $("extraBackupResult").textContent = "Zaxira yaratilmoqda...";
    try {
      const result = await api("/backup", { method: "POST", headers });
      $("extraBackupResult").textContent = `${result.name}: ${result.files} fayl, ${result.mb} MB.`;
      await refreshBackups();
    } catch (e) { $("extraBackupResult").textContent = e.message; }
  });

  $("extraRefreshBackups").addEventListener("click", async () => {
    try { await refreshBackups(); }
    catch (e) { $("extraBackupResult").textContent = e.message; }
  });

  refreshColumns();
  refreshReportSettings();
  loadTemplates();
  refreshBackups().catch((e) => { $("extraBackupResult").textContent = e.message; });
})();
