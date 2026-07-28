(function () {
  "use strict";

  const TOKEN_KEY = "captcha-solver-token";
  const POLL_MS = 5000;

  let config = null;
  let activePanel = "overview";

  // ── Helpers ──────────────────────────────────────────────────────────

  function $(sel) { return document.querySelector(sel); }
  function $$(sel) { return document.querySelectorAll(sel); }

  function headers() {
    const h = { "Content-Type": "application/json" };
    const token = $("#bearer-token")?.value || localStorage.getItem(TOKEN_KEY);
    if (token) h["Authorization"] = "Bearer " + token;
    return h;
  }

  async function api(path, opts = {}) {
    try {
      const res = await fetch(path, { ...opts, headers: { ...headers(), ...opts.headers } });
      const text = await res.text();
      let body;
      try { body = JSON.parse(text); } catch { body = text; }
      return { ok: res.ok, status: res.status, body };
    } catch (err) {
      return { ok: false, status: 0, body: { detail: err.message || String(err) } };
    }
  }

  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  function fmtTime(ts) {
    if (!ts) return "—";
    return new Date(ts * 1000).toLocaleString();
  }

  function copyText(text, btn) {
    navigator.clipboard.writeText(text).then(() => {
      const orig = btn.textContent;
      btn.textContent = "Copied!";
      setTimeout(() => { btn.textContent = orig; }, 1500);
    });
  }

  // ── Navigation ─────────────────────────────────────────────────────

  function showPanel(id) {
    activePanel = id;
    $$(".panel").forEach(p => p.classList.remove("active"));
    const panel = document.getElementById("panel-" + id);
    if (panel) panel.classList.add("active");
    $$("nav.sidebar button[data-panel]").forEach(b => {
      b.classList.toggle("active", b.dataset.panel === id);
    });
    const mobile = $("#mobile-nav-select");
    if (mobile && mobile.value !== id) mobile.value = id;
  }

  function initNav() {
    $$("nav.sidebar button[data-panel]").forEach(btn => {
      btn.addEventListener("click", () => showPanel(btn.dataset.panel));
    });
    $("#mobile-nav-select")?.addEventListener("change", e => showPanel(e.target.value));
  }

  // ── Health & monitoring ──────────────────────────────────────────────

  async function refreshHealth() {
    const badge = $("#health-badge");
    const { ok, body } = await api("/health");
    if (ok && body.status === "ok") {
      badge.className = "badge ok";
      badge.innerHTML = '<span class="dot"></span> online';
      $("#stat-types").textContent = (body.supported_types || []).length;
    } else {
      badge.className = "badge err";
      badge.innerHTML = '<span class="dot"></span> offline';
      $("#stat-types").textContent = "—";
    }
  }

  async function refreshStatus() {
    const { ok, body } = await api("/status");
    const modeEl = $("#browser-mode");
    if (!ok) {
      $("#stat-running").textContent = "?";
      if (modeEl) modeEl.textContent = "unknown";
      $("#current-tasks").innerHTML = '<p class="empty">Could not reach /status (token required on remote?)</p>';
      return;
    }
    const current = body.current || [];
    $("#stat-running").textContent = current.length;
    if (modeEl) modeEl.textContent = body.browser_mode || "—";
    if (!current.length) {
      $("#current-tasks").innerHTML = '<p class="empty">No tasks running</p>';
      return;
    }
    let html = "<table><thead><tr><th>Type</th><th>URL</th><th>Started</th></tr></thead><tbody>";
    for (const t of current) {
      html += `<tr><td><span class="tag">${esc(t.type)}</span></td>
        <td>${esc(t.url || "—")}</td>
        <td>${fmtTime(t.started_at)}</td></tr>`;
    }
    html += "</tbody></table>";
    $("#current-tasks").innerHTML = html;
  }

  async function refreshLogs() {
    const { ok, body } = await api("/logs?lines=30");
    if (!ok) {
      $("#stat-logs").textContent = "?";
      $("#logs-table").innerHTML = '<p class="empty">Could not reach /logs</p>';
      return;
    }
    $("#stat-logs").textContent = body.total ?? 0;
    const logs = body.logs || [];
    if (!logs.length) {
      $("#logs-table").innerHTML = '<p class="empty">No solve events yet</p>';
      return;
    }
    let html = "<table><thead><tr><th>Time</th><th>Type</th><th>URL</th><th>Result</th><th>Elapsed</th></tr></thead><tbody>";
    for (const e of logs) {
      const tag = e.success ? 'tag ok' : 'tag fail';
      const label = e.success ? "solved" : (e.error || "failed");
      html += `<tr>
        <td>${fmtTime(e.timestamp)}</td>
        <td><span class="tag">${esc(e.type)}</span></td>
        <td title="${esc(e.url)}">${esc((e.url || "").slice(0, 40))}${(e.url || "").length > 40 ? "…" : ""}</td>
        <td><span class="${tag}">${esc(String(label).slice(0, 30))}</span></td>
        <td>${e.elapsed != null ? e.elapsed.toFixed(1) + "s" : "—"}</td>
      </tr>`;
    }
    html += "</tbody></table>";
    $("#logs-table").innerHTML = html;
  }

  async function refreshAll() {
    await Promise.all([refreshHealth(), refreshStatus(), refreshLogs()]);
  }

  // ── Build tutorials from solvers.json ────────────────────────────────

  function renderGlobalSetup(global) {
    let html = '<div class="card section"><h3>Response Contract</h3><p style="color:var(--text-muted);font-size:0.875rem">' + esc(global.responseRule) + '</p></div>';

    html += '<div class="card section env-table"><h3>Optional Environment Overrides</h3><p style="font-size:0.85rem;color:var(--text-muted);margin-bottom:0.75rem">Not required — defaults work out of the box. See <code>deploy/env.optional.example</code> for systemd/shell overrides.</p><table class="field-table"><thead><tr><th>Variable</th><th>Default</th><th>Effect</th></tr></thead><tbody>';
    for (const v of global.envVars) {
      html += `<tr><td><code>${esc(v.name)}</code></td><td>${esc(v.default)}</td><td>${esc(v.description)}</td></tr>`;
    }
    html += "</tbody></table></div>";

    if (global.mistralSetup) {
      const ms = global.mistralSetup;
      html += `<div class="card section" id="mistral-setup-card"><h3>${esc(ms.title)}</h3>`;
      html += `<p style="font-size:0.85rem;color:var(--text-muted);margin-bottom:0.75rem">Keys: <code>${esc(ms.keyfile || "common/apikey.txt")}</code> · Models: <code>${esc(ms.configfile || "common/mistral.json")}</code></p>`;
      html += `<div id="mistral-status" class="mistral-status"><p class="empty">Loading Mistral status…</p></div>`;
      html += '<div class="mistral-keys-form">';
      html += '<h4 style="margin:0.75rem 0 0.5rem;font-size:0.9rem">API keys</h4>';
      html += '<p style="font-size:0.8rem;color:var(--text-muted);margin-bottom:0.5rem">One key per line. Keys are stored in <code>common/apikey.txt</code> — only last 4 chars shown after save.</p>';
      html += '<div class="form-group"><label for="mistral-keys-input">Add keys</label>';
      html += '<textarea id="mistral-keys-input" rows="3" spellcheck="false" placeholder="paste Mistral API keys here (one per line)"></textarea></div>';
      html += '<div class="btn-row">';
      html += '<button class="btn primary" id="btn-add-mistral-keys">Add keys</button>';
      html += '<button class="btn" id="btn-replace-mistral-keys">Replace all</button>';
      html += '<button class="btn danger" id="btn-clear-mistral-keys">Clear all</button>';
      html += '</div>';
      html += '<div id="mistral-keys-result"></div>';
      html += '<div id="mistral-keys-list" class="mistral-keys-list"></div>';
      html += '</div>';
      html += "<ol>";
      for (const step of ms.steps) {
        html += `<li>${esc(step)}</li>`;
      }
      html += "</ol>";
      if (ms.models?.length) {
        html += '<div class="mistral-models-form">';
        for (const m of ms.models) {
          html += `<div class="form-group"><label for="mistral-${m.id}">${esc(m.label)}</label>
            <input type="text" id="mistral-${m.id}" data-field="${esc(m.field)}" placeholder="mistral-medium-latest"></div>`;
        }
        html += '<div class="btn-row"><button class="btn primary" id="btn-save-mistral">Save models</button></div>';
        html += '<div id="mistral-save-result"></div></div>';
      }
      html += "</div>";
    }

    html += `<div class="card section"><h3>Quick Start</h3>
      <pre><code># Install deps
pip install -r requirements.txt
python -m playwright install chromium

# Run server (headed browser — recommended)
set BROWSER_HEADLESS=0
python server.py
# Windows: run.bat   Linux: ./run.sh

# Dashboard
http://127.0.0.1:8877/dashboard

# Quick test (reCAPTCHA v3 — no Mistral keys needed)
curl -X POST http://127.0.0.1:8877/solve -H "Content-Type: application/json" \\
  -d '{"type":"recaptcha","version":"v3","sitekey":"6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI","url":"https://www.google.com/recaptcha/api2/demo","action":"homepage"}'</code></pre></div>`;

    $("#global-setup").innerHTML = html;
    initMistralConfig(global.mistralSetup);
  }

  async function loadMistralStatus() {
    const box = $("#mistral-status");
    if (!box) return;
    try {
      const { ok, body } = await api("/config/mistral");
      if (!ok || !body) {
        box.innerHTML = "<p class=\"empty\">Could not load Mistral config (is the server running?)</p>";
        return;
      }
      const keyTag = body.keys_configured
        ? `<span class="chip ok">${body.keys_count} key(s) in apikey.txt</span>`
        : `<span class="chip warn">No keys in apikey.txt</span>`;
      const cfgTag = body.config_exists
        ? `<span class="chip ok">mistral.json present</span>`
        : `<span class="chip warn">mistral.json missing — using defaults</span>`;
      let envWarn = "";
      const overrides = body.env_override_active || {};
      const active = Object.entries(overrides).filter(([, v]) => v).map(([k]) => k);
      if (active.length) {
        envWarn = `<p style="font-size:0.8rem;color:var(--warn);margin-top:0.5rem">Env overrides active: ${active.map(e => "<code>" + esc(e) + "</code>").join(", ")}</p>`;
      }
      box.innerHTML = `<div class="tutorial-meta">${keyTag} ${cfgTag}</div>${envWarn}`;
      renderKeyList(body.key_hints || []);
      if (body.models) {
        for (const [solver, model] of Object.entries(body.models)) {
          const inp = $("#mistral-" + solver);
          if (inp && !inp.dataset.userEdited) inp.value = model;
        }
      }
    } catch (err) {
      box.innerHTML = "<p class=\"empty\">" + esc(err.message) + "</p>";
    }
  }

  function renderKeyList(hints) {
    const list = $("#mistral-keys-list");
    if (!list) return;
    if (!hints.length) {
      list.innerHTML = "<p class=\"empty\" style=\"margin-top:0.75rem\">No keys saved yet</p>";
      return;
    }
    let html = "<ul class=\"key-hint-list\">";
    for (const item of hints) {
      html += `<li><code>${esc(item.hint)}</code>
        <button type="button" class="btn btn-sm danger btn-remove-key" data-index="${item.index}">Remove</button></li>`;
    }
    html += "</ul>";
    list.innerHTML = html;
    list.querySelectorAll(".btn-remove-key").forEach(btn => {
      btn.addEventListener("click", () => removeMistralKey(parseInt(btn.dataset.index, 10)));
    });
  }

  function parseKeysInput(text) {
    return text.split(/\r?\n/).map(s => s.trim()).filter(s => s && !s.startsWith("#"));
  }

  async function removeMistralKey(index) {
    const result = $("#mistral-keys-result");
    try {
      const { ok, body } = await api(`/config/mistral/keys?index=${index}`, { method: "DELETE" });
      result.className = "result-box " + (ok ? "success" : "error");
      result.innerHTML = ok ? "<p>Key removed</p>" : "<pre>" + esc(JSON.stringify(body, null, 2)) + "</pre>";
      await loadMistralStatus();
    } catch (err) {
      result.className = "result-box error";
      result.innerHTML = "<pre>" + esc(err.message) + "</pre>";
    }
  }

  function initMistralConfig(mistralSetup) {
    if (!mistralSetup) return;
    loadMistralStatus();
    document.querySelectorAll(".mistral-models-form input").forEach(inp => {
      inp.addEventListener("input", () => { inp.dataset.userEdited = "1"; });
    });
    $("#btn-save-mistral")?.addEventListener("click", async () => {
      const payload = {};
      for (const m of mistralSetup.models || []) {
        const inp = document.querySelector(`[data-field="${m.field}"]`);
        if (inp) payload[m.field] = inp.value.trim();
      }
      const result = $("#mistral-save-result");
      const btn = $("#btn-save-mistral");
      btn.disabled = true;
      try {
        const { ok, body } = await api("/config/mistral", {
          method: "PUT",
          body: JSON.stringify(payload),
        });
        result.className = "result-box " + (ok ? "success" : "error");
        result.innerHTML = ok
          ? "<p>Models saved to <code>common/mistral.json</code></p>"
          : "<pre>" + esc(JSON.stringify(body, null, 2)) + "</pre>";
        document.querySelectorAll(".mistral-models-form input").forEach(inp => {
          delete inp.dataset.userEdited;
        });
        await loadMistralStatus();
      } catch (err) {
        result.className = "result-box error";
        result.innerHTML = "<pre>" + esc(err.message) + "</pre>";
      } finally {
        btn.disabled = false;
      }
    });

    async function submitKeys(method, confirmMsg) {
      const input = $("#mistral-keys-input");
      const result = $("#mistral-keys-result");
      const keys = parseKeysInput(input?.value || "");
      if (!keys.length) {
        result.className = "result-box error";
        result.innerHTML = "<p>Paste at least one API key (one per line)</p>";
        return;
      }
      if (confirmMsg && !confirm(confirmMsg)) return;
      try {
        const { ok, body } = await api("/config/mistral/keys", {
          method,
          body: JSON.stringify({ keys }),
        });
        result.className = "result-box " + (ok ? "success" : "error");
        if (ok) {
          const added = body.added != null ? ` (${body.added} new)` : "";
          result.innerHTML = `<p>${method === "POST" ? "Keys added" : "Keys replaced"}${added} — ${body.keys_count} total</p>`;
          input.value = "";
          await loadMistralStatus();
        } else {
          result.innerHTML = "<pre>" + esc(JSON.stringify(body, null, 2)) + "</pre>";
        }
      } catch (err) {
        result.className = "result-box error";
        result.innerHTML = "<pre>" + esc(err.message) + "</pre>";
      }
    }

    $("#btn-add-mistral-keys")?.addEventListener("click", () => submitKeys("POST"));
    $("#btn-replace-mistral-keys")?.addEventListener("click", () =>
      submitKeys("PUT", "Replace ALL keys with the pasted list? Existing keys not in the list will be removed."));
    $("#btn-clear-mistral-keys")?.addEventListener("click", async () => {
      if (!confirm("Remove ALL Mistral API keys from apikey.txt?")) return;
      const result = $("#mistral-keys-result");
      try {
        const { ok, body } = await api("/config/mistral/keys", { method: "DELETE" });
        result.className = "result-box " + (ok ? "success" : "error");
        result.innerHTML = ok ? "<p>All keys cleared</p>" : "<pre>" + esc(JSON.stringify(body, null, 2)) + "</pre>";
        const input = $("#mistral-keys-input");
        if (input) input.value = "";
        await loadMistralStatus();
      } catch (err) {
        result.className = "result-box error";
        result.innerHTML = "<pre>" + esc(err.message) + "</pre>";
      }
    });
  }

  function renderSolverTutorial(s) {
    const exampleJson = JSON.stringify(s.example, null, 2);
    const curl = `curl -X POST http://127.0.0.1:8877/solve \\
  -H "Content-Type: application/json" \\
  -d '${JSON.stringify(s.example)}'`;

    let html = `<section id="panel-${s.id}" class="panel">
      <div class="tutorial-header">
        <div class="tutorial-icon">${s.icon}</div>
        <div>
          <h2>${esc(s.name)}</h2>
          <p class="subtitle">${esc(s.summary)}</p>
          <div class="tutorial-meta">
            <span class="chip">Returns: ${esc(s.returns)}</span>
            ${s.needsSitekey ? '<span class="chip">Requires sitekey</span>' : '<span class="chip">No sitekey</span>'}
            ${s.needsUrl ? '<span class="chip">Requires url</span>' : '<span class="chip">No url</span>'}
          </div>
        </div>
      </div>`;

    if (s.modes?.length) {
      html += '<div class="section"><h4>Solving Modes</h4><div class="mode-list">';
      for (const m of s.modes) {
        html += `<div class="mode-item"><strong>${esc(m.name)}</strong><p>${esc(m.description)}</p></div>`;
      }
      html += "</div></div>";
    }

    html += '<div class="section"><h4>Required Fields</h4><table class="field-table"><tbody>';
    for (const f of s.required) {
      html += `<tr><td>${esc(f.field)}</td><td>${esc(f.value || f.description || "")}</td></tr>`;
    }
    html += "</tbody></table></div>";

    if (s.optional?.length) {
      html += '<div class="section"><h4>Optional Fields</h4><table class="field-table"><tbody>';
      for (const f of s.optional) {
        html += `<tr><td>${esc(f.field)}</td><td>${esc(f.description || f.value || "")}</td></tr>`;
      }
      html += "</tbody></table></div>";
    }

    if (s.env?.length) {
      html += `<div class="section"><h4>Environment</h4><p style="font-size:0.85rem;color:var(--text-muted)">Uses: ${s.env.map(e => '<code>' + esc(e) + '</code>').join(", ")}</p></div>`;
    }

    html += `<div class="section"><h4>Example Request</h4>
      <div class="code-block"><button class="copy-btn">Copy</button>
      <pre><code>${esc(exampleJson)}</code></pre></div></div>`;

    html += `<div class="section"><h4>cURL</h4>
      <div class="code-block"><button class="copy-btn">Copy</button>
      <pre><code>${esc(curl)}</code></pre></div></div>`;

    if (s.tips?.length) {
      html += '<div class="section"><h4>Tips & Limitations</h4><ul>';
      for (const t of s.tips) html += `<li>${esc(t)}</li>`;
      html += "</ul></div>";
    }

    html += `<div class="btn-row">
      <button class="btn primary btn-load-example" data-solver="${s.id}">Load in Test Solve</button>
    </div></section>`;

    return html;
  }

  function buildTutorials(data) {
    const nav = $("#solver-nav");
    const panels = $("#solver-panels");
    const preset = $("#solver-preset");
    const mobile = $("#mobile-nav-select");

    for (const s of data.solvers) {
      const btn = document.createElement("button");
      btn.dataset.panel = s.id;
      btn.textContent = s.icon + " " + s.name;
      btn.addEventListener("click", () => showPanel(s.id));
      nav.appendChild(btn);

      const opt = document.createElement("option");
      opt.value = s.id;
      opt.textContent = s.name;
      preset.appendChild(opt);

      const mopt = document.createElement("option");
      mopt.value = s.id;
      mopt.textContent = s.icon + " " + s.name;
      mobile.appendChild(mopt);

      panels.innerHTML += renderSolverTutorial(s);
    }

    renderGlobalSetup(data.global);

    $$(".copy-btn").forEach(btn => {
      const pre = btn.parentElement.querySelector("pre code");
      if (pre) btn.addEventListener("click", () => copyText(pre.textContent, btn));
    });

    $$(".btn-load-example").forEach(btn => {
      btn.addEventListener("click", () => {
        const solver = data.solvers.find(x => x.id === btn.dataset.solver);
        if (solver) {
          $("#solve-payload").value = JSON.stringify(solver.example, null, 2);
          showPanel("test");
        }
      });
    });

    // Re-bind sidebar buttons for dynamically added solver nav
    $$("nav.sidebar button[data-panel]").forEach(btn => {
      if (!btn._bound) {
        btn._bound = true;
        btn.addEventListener("click", () => showPanel(btn.dataset.panel));
      }
    });
  }

  // ── Test solve ───────────────────────────────────────────────────────

  function initTestSolve() {
    const tokenInput = $("#bearer-token");
    const saved = localStorage.getItem(TOKEN_KEY);
    if (saved) tokenInput.value = saved;
    tokenInput.addEventListener("change", () => {
      localStorage.setItem(TOKEN_KEY, tokenInput.value);
    });

    $("#solver-preset")?.addEventListener("change", e => {
      const id = e.target.value;
      if (!id || !config) return;
      const s = config.solvers.find(x => x.id === id);
      if (s) $("#solve-payload").value = JSON.stringify(s.example, null, 2);
    });

    $("#btn-format")?.addEventListener("click", () => {
      try {
        const obj = JSON.parse($("#solve-payload").value);
        $("#solve-payload").value = JSON.stringify(obj, null, 2);
      } catch (err) {
        alert("Invalid JSON: " + err.message);
      }
    });

    $("#btn-solve")?.addEventListener("click", async () => {
      const box = $("#solve-result");
      const btn = $("#btn-solve");
      const payloadText = $("#solve-payload").value;
      let payload;
      try {
        payload = JSON.parse(payloadText);
      } catch (err) {
        box.className = "result-box error";
        box.innerHTML = "<pre>Invalid JSON: " + esc(err.message) + "</pre>";
        return;
      }

      const timeoutS = payload.timeout_s || 60;
      btn.disabled = true;
      btn.textContent = "Solving…";
      box.className = "result-box";
      box.innerHTML = `<p class="empty solving-msg">
        <span class="spinner"></span>
        Running solve (type: <strong>${esc(payload.type || "?")}</strong>) —
        may take up to <strong>${timeoutS}s</strong>. A Chromium window may open (headed mode).
      </p>`;

      const t0 = Date.now();
      try {
        const { ok, status, body } = await api("/solve", {
          method: "POST",
          body: JSON.stringify(payload),
        });
        const elapsed = ((Date.now() - t0) / 1000).toFixed(1);
        const solved = ok && body && body.solved === true;
        const display = typeof body === "object" ? body : { detail: body };
        box.className = "result-box " + (solved ? "success" : "error");
        const headline = solved ? "Solved" : (ok ? "Finished (not solved)" : "Request failed");
        box.innerHTML = `<p style="margin-bottom:0.5rem;font-size:0.9rem">
          <strong>${headline}</strong> · HTTP ${status} · ${elapsed}s
        </p><pre><code>${esc(JSON.stringify(display, null, 2))}</code></pre>`;
        refreshLogs();
        refreshStatus();
      } catch (err) {
        box.className = "result-box error";
        box.innerHTML = "<pre>Unexpected error: " + esc(err.message) + "</pre>";
      } finally {
        btn.disabled = false;
        btn.textContent = "Run Solve";
      }
    });
  }

  // ── Boot ─────────────────────────────────────────────────────────────

  async function init() {
    initNav();
    initTestSolve();

    try {
      const res = await fetch("/dashboard/static/solvers.json");
      config = await res.json();
      buildTutorials(config);
    } catch (err) {
      console.error("Failed to load solvers.json", err);
    }

    await refreshAll();
    setInterval(refreshAll, POLL_MS);
  }

  document.addEventListener("DOMContentLoaded", init);
})();
