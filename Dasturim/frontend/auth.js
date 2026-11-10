(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const accountName = $("accountName");
  if (!accountName) return;

  let csrfToken = "";
  let currentUser = null;
  const authLayer = document.createElement("div");
  authLayer.id = "authLayer";
  authLayer.style.cssText = "position:fixed;inset:0;z-index:1000;background:#111827aa;display:none;place-items:center;padding:18px";
  document.body.appendChild(authLayer);

  const onboardingLayer = document.createElement("div");
  onboardingLayer.style.cssText = authLayer.style.cssText;
  onboardingLayer.style.zIndex = "999";
  onboardingLayer.style.display = "none";
  document.body.appendChild(onboardingLayer);

  const style = document.createElement("style");
  style.textContent = `
    .auth-card{width:min(440px,100%);background:#fff;border:1px solid #e3e9f2;border-radius:16px;padding:24px;box-shadow:0 24px 80px #11182755}
    .auth-card h2{margin:0 0 8px;font-size:20px}.auth-card p{color:#69758a;font-size:13px;line-height:1.55}
    .auth-card label{display:grid;gap:6px;margin:12px 0;color:#475569;font-size:13px}
    .auth-card input,.auth-card select{width:100%;padding:10px;border:1px solid #d5dce7;border-radius:8px;font:inherit}
    .auth-actions{display:flex;gap:8px;justify-content:flex-end;margin-top:16px}
    .auth-error{min-height:20px;color:#dc2626;font-size:13px}
    .auth-table{max-height:240px;overflow:auto}.auth-table table{font-size:12px}
    details{margin:12px 0}summary{cursor:pointer;font-weight:600}details p{margin:6px 0}
  `;
  document.head.appendChild(style);

  async function request(url, options = {}) {
    const response = await fetch(url, options);
    let data = {};
    try { data = await response.json(); } catch {}
    if (!response.ok) throw new Error(data.detail || `So'rov amalga oshmadi (HTTP ${response.status})`);
    return data;
  }

  const originalApi = window.api;
  if (typeof originalApi === "function") {
    window.api = (url, options = {}) => {
      const headers = { ...(options.headers || {}) };
      if (csrfToken && !["GET", "HEAD", "OPTIONS"].includes((options.method || "GET").toUpperCase())) {
        headers["X-CSRF-Token"] = csrfToken;
      }
      return originalApi(url, { ...options, headers });
    };
  }

  function showAuth(configured, message = "") {
    authLayer.style.display = "grid";
    authLayer.innerHTML = `<section class="auth-card" role="dialog" aria-modal="true">
      <h2>DataFlow AI — ${configured ? "tizimga kirish" : "birinchi administrator"}</h2>
      <p>${configured
        ? "Davom etish uchun hisobingiz bilan kiring."
        : "Xavfsiz parol bilan birinchi administratorni yarating. Parol xeshlangan holda saqlanadi."}</p>
      ${!configured ? `<label>Administrator yaratish kodi (server talab qilsa)<input id="setupToken" type="password" autocomplete="off"></label>` : ""}
      ${!configured ? `<label>Login<input id="authUsername" autocomplete="username" minlength="3" maxlength="64"></label>` : ""}
      ${configured ? `<label>Login<input id="authUsername" autocomplete="username" autofocus></label>` : ""}
      <label>Parol<input id="authPassword" type="password" autocomplete="${configured ? "current-password" : "new-password"}" minlength="12" maxlength="256"></label>
      <div id="authError" class="auth-error">${message}</div>
      <div class="auth-actions"><button class="btn primary" id="authSubmit">${configured ? "Kirish" : "Administrator yaratish"}</button></div>
    </section>`;
    const submit = async () => {
      const error = $("authError");
      const button = $("authSubmit");
      button.disabled = true;
      error.textContent = "";
      try {
        const credentials = {
          username: $("authUsername").value,
          password: $("authPassword").value,
        };
        if (configured) {
          await request("/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(credentials) });
          window.location.reload();
        } else {
          const result = await request("/auth/setup", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ...credentials, setup_token: $("setupToken").value }),
          });
          showAuth(true, result.message || "Administrator yaratildi. Tizimga kiring.");
        }
      } catch (e) {
        error.textContent = e.message;
      } finally {
        if (document.body.contains(button)) button.disabled = false;
      }
    };
    $("authSubmit").addEventListener("click", submit);
    $("authPassword").addEventListener("keydown", (event) => {
      if (event.key === "Enter") submit();
    });
  }

  function showOnboarding(user) {
    let seen = false;
    try { seen = localStorage.getItem(`dataflow-onboarding:${user.id}`) === "done"; } catch {}
    if (seen) return;
    const steps = [
      ["1 / 4 · Til va loyiha", "Tilni yuqoridagi tanlagichdan belgilang, faol loyiha esa jadvallar va panellarni ajratib saqlaydi."],
      ["2 / 4 · Ma'lumot yuklash", "CSV yoki Excel faylini tanlang. Excel'da bitta yoki barcha varaqlarni yuklashingiz mumkin."],
      ["3 / 4 · Tekshirish va tozalash", "Jadvalni ko'ring, sahifalang va amallarni qo'llashdan oldin natijani oldindan ko'ring."],
      ["4 / 4 · Tahlil va xavfsizlik", "SQL, AI, grafik va hisobotlardan foydalaning. AI maxfiylik sozlamalarini tekshiring; administratorlar foydalanuvchi va audit jurnalini boshqaradi."],
    ];
    let index = 0;
    const render = () => {
      onboardingLayer.innerHTML = `<section class="auth-card" role="dialog" aria-modal="true">
        <h2>DataFlow AI bilan tanishing</h2><h3>${steps[index][0]}</h3><p>${steps[index][1]}</p>
        <div class="auth-actions">
          ${index ? `<button class="btn" id="onboardBack">Orqaga</button>` : ""}
          <button class="btn primary" id="onboardNext">${index === steps.length - 1 ? "Boshlash" : "Keyingi"}</button>
        </div></section>`;
      onboardingLayer.style.display = "grid";
      const next = () => {
        if (index < steps.length - 1) {
          index += 1;
          render();
        } else {
          onboardingLayer.style.display = "none";
          try { localStorage.setItem(`dataflow-onboarding:${user.id}`, "done"); } catch {}
        }
      };
      $("onboardNext").addEventListener("click", next);
      if ($("onboardBack")) $("onboardBack").addEventListener("click", () => { index -= 1; render(); });
    };
    render();
  }

  async function openUsers() {
    const layer = document.createElement("div");
    layer.style.cssText = authLayer.style.cssText;
    layer.style.display = "grid";
    layer.innerHTML = `<section class="auth-card" role="dialog" aria-modal="true" style="width:min(760px,100%)">
      <div style="display:flex;justify-content:space-between;align-items:center"><h2>Foydalanuvchilar va audit</h2><button class="btn" id="usersClose">Yopish</button></div>
      <form id="userCreate" class="clean-form">
        <label>Login<input name="username" minlength="3" maxlength="64" required></label>
        <label>Parol<input name="password" type="password" minlength="12" maxlength="256" required></label>
        <label>Rol<select name="role"><option value="analyst">Analitik</option><option value="viewer">Ko'ruvchi</option><option value="admin">Administrator</option></select></label>
        <button class="btn primary" type="submit">Foydalanuvchi qo'shish</button>
      </form><div id="userError" class="auth-error"></div><div id="userRows" class="auth-table"></div>
      <h3>Oxirgi audit hodisalari</h3><div id="auditRows" class="auth-table"></div>
    </section>`;
    document.body.appendChild(layer);
    $("usersClose").addEventListener("click", () => layer.remove());
    $("userCreate").addEventListener("submit", async (event) => {
      event.preventDefault();
      const formElement = event.currentTarget;
      const form = new FormData(formElement);
      try {
        await window.api("/auth/users", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ username: form.get("username"), password: form.get("password"), role: form.get("role") }),
        });
        await loadUsers();
        formElement.reset();
      } catch (e) { $("userError").textContent = e.message; }
    });

    async function loadUsers() {
      const [users, audit] = await Promise.all([window.api("/auth/users"), window.api("/auth/audit?limit=50")]);
      const table = (headers, rows) => {
        const element = document.createElement("table");
        const head = element.createTHead().insertRow();
        headers.forEach((text) => { const cell = document.createElement("th"); cell.textContent = text; head.appendChild(cell); });
        const body = element.createTBody();
        rows.forEach((values) => {
          const row = body.insertRow();
          values.forEach((value) => { const cell = row.insertCell(); cell.textContent = value == null ? "" : String(value); });
        });
        return element;
      };
      const userTable = document.createElement("table");
      const head = userTable.createTHead().insertRow();
      ["Login", "Rol", "Holat", "Amal"].forEach((value) => { const cell = document.createElement("th"); cell.textContent = value; head.appendChild(cell); });
      const body = userTable.createTBody();
      users.forEach((user) => {
        const row = body.insertRow();
        [user.username, user.role, user.enabled ? "Faol" : "O'chirilgan"].forEach((value) => {
          const cell = row.insertCell(); cell.textContent = value;
        });
        const action = row.insertCell();
        if (user.id !== currentUser.id) {
          const toggle = document.createElement("button");
          toggle.className = "btn";
          toggle.textContent = user.enabled ? "O'chirish" : "Yoqish";
          toggle.addEventListener("click", async () => {
            try { await window.api(`/auth/users/${user.id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ enabled: !user.enabled }) }); await loadUsers(); }
            catch (e) { $("userError").textContent = e.message; }
          });
          action.appendChild(toggle);
          const reset = document.createElement("input");
          reset.type = "password"; reset.placeholder = "Yangi parol (12+)";
          reset.autocomplete = "new-password";
          reset.style.cssText = "width:155px;margin-left:6px;padding:6px";
          action.appendChild(reset);
          const change = document.createElement("button");
          change.className = "btn"; change.textContent = "Parol";
          change.addEventListener("click", async () => {
            try { await window.api(`/auth/users/${user.id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ password: reset.value }) }); reset.value = ""; $("userError").textContent = "Parol yangilandi; foydalanuvchi qayta kirishi kerak."; }
            catch (e) { $("userError").textContent = e.message; }
          });
          action.appendChild(change);
        }
      });
      $("userRows").replaceChildren(userTable);
      $("auditRows").replaceChildren(table(
        ["Vaqt (UTC)", "Foydalanuvchi", "Rol", "Amal", "Resurs", "Holat"],
        audit.map((item) => [item.created_at, item.username, item.role, item.action, item.resource, item.status_code]),
      ));
    }

    try { await loadUsers(); } catch (e) { $("userError").textContent = e.message; }
  }

  $("usersOpen").addEventListener("click", openUsers);
  $("logoutBtn").addEventListener("click", async () => {
    try {
      await window.api("/auth/logout", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
      window.location.reload();
    } catch (e) { accountName.textContent = e.message; }
  });
  $("helpOpen").addEventListener("click", () => {
    const button = document.querySelector('.nav-btn[data-view="view-help"]');
    if (button) button.click();
  });

  (async () => {
    try {
      const status = await request("/auth/status");
      if (!status.auth_enabled) {
        accountName.textContent = "Mahalliy foydalanuvchi";
        return;
      }
      if (!status.configured) {
        showAuth(false);
        return;
      }
      const session = await request("/auth/me");
      currentUser = session.user;
      csrfToken = session.csrf_token;
      accountName.textContent = `${currentUser.username} · ${currentUser.role}`;
      $("logoutBtn").classList.remove("hidden");
      $("usersOpen").classList.toggle("hidden", currentUser.role !== "admin");
      if (currentUser.role !== "viewer" && typeof window.loadAiSettings === "function") {
        window.loadAiSettings().catch((e) => {
          const statusBox = $("aiSettingsStatus");
          if (statusBox) { statusBox.textContent = e.message; statusBox.className = "msg err"; }
        });
      }
      if (typeof window.refreshProjects === "function") {
        window.refreshProjects().then(() => window.refreshTables()).catch(() => {});
      }
      showOnboarding(currentUser);
    } catch (e) {
      showAuth(true, e.message);
    }
  })();
})();
