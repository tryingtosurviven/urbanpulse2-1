// static/script.js
// UrbanPulse Demo Controller
// - Calls your backend for scenario execution
// - Normalizes outputs for UI
// - Supports ADMIN/DEMO panels + CLINIC portal auto-dispatch (severe haze only)

// ==========================================
// 1. AUTHENTICATION HELPERS (New)
// ==========================================
function getAuthToken() {
  return localStorage.getItem("urbanpulse_token") || null;
}

function authHeaders() {
  const token = getAuthToken();
  return token ? { "Authorization": `Bearer ${token}` } : {};
}

/**
 * Wrapper around fetch that auto-attaches JWT and handles 401/403.
 */
async function authedFetch(url, options = {}) {
  const mergedOptions = {
    ...options,
    headers: {
      ...(options.headers || {}),
      ...authHeaders(),
      "Content-Type": "application/json",
    },
  };

  const res = await fetch(url, mergedOptions);

  if (res.status === 401) {
    localStorage.removeItem("urbanpulse_token");
    window.location.href = `/login?next=${encodeURIComponent(window.location.pathname)}&reason=expired`;
    throw new Error("Session expired");
  }

  if (res.status === 403) {
    window.location.href = "/access-denied";
    throw new Error("Access denied");
  }

  return res;
}

async function runScenario(scenarioName) {
  const logContainer = document.getElementById("log");
  const statusDiv = document.getElementById("status");
  const summaryDiv = document.getElementById("summary");

  // If this page doesn't have these elements (e.g., citizen / clinic), no-op safely
  const hasUI = !!(logContainer && statusDiv && summaryDiv);

  if (hasUI) {
    statusDiv.className = "status-running";
    statusDiv.innerText = `🤖 Agents Coordinating: ${prettyName(scenarioName)}...`;
    logContainer.innerHTML =
      '<p class="log-loading">Agents are processing live data and calculating surge risks...</p>';
    summaryDiv.innerHTML = "";
  }

  try {
    const data = await callScenarioBackend(scenarioName);

    // Normalize fields across possible backend responses
    const risk = normalizeRisk(data);
    const alerts = normalizeAlerts(data);
    const supply = normalizeSupply(data);
    const logs = normalizeLogs(data);

    // ✅ NEW: Auto-dispatch hook (only triggers in severe haze when backend says autonomous)
    await maybeAutoDispatch(scenarioName, data);

    if (hasUI) {
      // Status
      statusDiv.className = "status-ok";
      statusDiv.innerText = "✅ Action Protocol Executed";

      // Summary (judge-friendly)
      summaryDiv.innerHTML = `
        <div class="summary-box">
          <p><strong>Highest PSI:</strong> ${safe(risk.current_psi)} (${safe(risk.risk_level)})</p>
          <p><strong>Affected:</strong> ${Array.isArray(risk.affected_regions) ? risk.affected_regions.join(", ") : safe(risk.affected_regions)}</p>
          <p><strong>Trigger:</strong> ${safe(risk.trigger_reason)}</p>
          <p><strong>Action:</strong> ${safe(alerts.alert_message)}</p>
          <p><strong>Supply Action:</strong> ${safe(supply.summary)}</p>
          <p><strong>Autonomy:</strong> ${data?.supply_chain_actions?.autonomous ? "⚡ Autonomous (Severe only)" : "👤 Human-in-loop"}</p>
        </div>
      `;

      // Logs (agentic feel)
      logContainer.innerHTML = "";

      if (Array.isArray(logs) && logs.length > 0) {
        for (const entry of logs.slice().reverse()) {
          addLogEntry(
            entry.agent || entry.actor || "Agent",
            entry.action || entry.event || "Step",
            entry.data ?? entry.payload ?? entry
          );
        }
      } else {
        addLogEntry("EnvironmentSentinel", "Triggered Health Surge Protocol", risk);
        addLogEntry("DynamiqMedicalAgent", "Generated Public Health Advisory", alerts);
        addLogEntry("SupplyChainAgent", "Prepared Inventory / Procurement Actions", supply);
      }
    }

    return data;
  } catch (e) {
    if (hasUI) {
      statusDiv.className = "status-error";
      statusDiv.innerText = "❌ System Error";
      logContainer.innerHTML = `<p class="log-error">${safe(e.message)}</p>`;
    }
    throw e;
  }
}

/**
 * Citizen page helper:
 * Used by citizen map when clicking regions; doesn't require admin DOM elements.
 */
async function runRegionScenario(scenarioName) {
  return await callScenarioBackend(scenarioName);
}

// Expose functions globally (so HTML onclick can call them)
window.runScenario = runScenario;
window.runRegionScenario = runRegionScenario;

/* --------------------------
   Backend call + fallbacks
--------------------------- */
async function callScenarioBackend(scenarioName) {
  // Check if user is admin
  const role = localStorage.getItem("urbanpulse_role") || "";
  const isAdmin = role === "admin";

  if (isAdmin) {
    // Admin uses protected endpoint
    try {
      const res = await authedFetch(`/api/run-scenario/${encodeURIComponent(scenarioName)}`, {
        method: "POST",
        headers: { Accept: "application/json" },
      });
      if (res.ok) return await safeJson(res);
    } catch (e) {
      if (e.message === "Session expired") throw e;
      // fall through to watsonx
    }

    // Admin fallback
    const res2 = await authedFetch(`/api/watsonx-scenario`, {
      method: "POST",
      headers: { Accept: "application/json" },
      body: JSON.stringify({ scenario_key: scenarioName }),
    });
    const data2 = await safeJson(res2);
    if (!res2.ok) throw new Error(data2?.error || "Failed to run scenario");
    return data2;

  } else {
    // Clinic manager + citizen use public endpoint (no admin required)
    const res = await fetch(`/api/public/run-scenario/${encodeURIComponent(scenarioName)}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        ...authHeaders(),
      },
    });
    const data = await safeJson(res);
    if (!res.ok) throw new Error(data?.error || "Failed to run scenario");
    return data;
  }
}

async function safeJson(res) {
  const text = await res.text();
  try {
    return JSON.parse(text);
  } catch {
    if (!res.ok) throw new Error(text || `HTTP ${res.status}`);
    return { raw: text };
  }
}

/* --------------------------
   ✅ AUTO DISPATCH (Severe only)
--------------------------- */

// Prevent repeated auto orders if the user clicks severe multiple times
let autoDispatchLock = false;

/**
 * Auto dispatch requirement:
 * - ONLY severe_haze
 * - ONLY when backend explicitly says autonomous
 * - Calls /api/clinic-confirm-order
 * - Emits an event so clinic.html can show purple UI/modal if it wants
 */
async function maybeAutoDispatch(scenarioName, data) {
  const key = String(scenarioName || "").trim().toLowerCase();

  const autonomous =
    data?.supply_chain_actions?.autonomous === true ||
    data?.raw_data?.supply_chain_actions?.autonomous === true;

  // Only trigger on severe haze AND autonomous true
  if (key !== "severe_haze" || !autonomous) return;

  // If not on clinic page, do nothing (no need to order)
  // Clinic page has draft panel elements. This is a soft check.
  const onClinic =
    !!document.getElementById("draft-panel") || window.location.pathname.includes("/clinic");
  if (!onClinic) return;

  // Lock to prevent spam
  if (autoDispatchLock) return;
  autoDispatchLock = true;

  // Determine qty from backend (preferred), fallback safe
  const s = data?.supply_chain_actions || data?.raw_data?.supply_chain_actions || {};
  const qty =
    parseInt(s.recommended_qty ?? s.qty ?? data?.recommended_qty ?? 0, 10) ||
    1200;

  try {
    // Confirm order via backend
    const res = await authedFetch("/api/clinic-confirm-order", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ confirmed_qty: qty }),
    });

    const payload = await safeJson(res);
    if (!res.ok) throw new Error(payload?.error || "Auto dispatch failed");

    // Emit an event for clinic.html to react (purple modal, toast, etc.)
    window.dispatchEvent(
      new CustomEvent("urbanpulse:auto-dispatch", {
        detail: {
          scenario: "severe_haze",
          qty,
          po_id: s.po_id || "AUTO",
          message: "⚡ Autonomous dispatch completed (severe haze).",
        },
      })
    );
  } finally {
    // unlock after a short cooldown to avoid duplicate orders on rapid clicks
    setTimeout(() => {
      autoDispatchLock = false;
    }, 4000);
  }
}

/* --------------------------
   Normalizers (robust demo)
--------------------------- */

function normalizeRisk(data) {
  const r = data?.risk_assessment || data?.risk || data?.assessment || {};
  return {
    current_psi: r.current_psi ?? data?.current_psi ?? data?.psi ?? "N/A",
    risk_level: r.risk_level ?? data?.risk_level ?? "N/A",
    affected_regions: r.affected_regions ?? data?.affected_regions ?? [],
    trigger_reason: r.trigger_reason ?? data?.trigger_reason ?? "Threshold / scenario trigger",
  };
}

function normalizeAlerts(data) {
  const a = data?.healthcare_alerts || data?.alerts || data?.advisory || {};
  return {
    alert_message:
      a.alert_message ??
      a.message ??
      data?.alert_message ??
      "Clinics advised to prepare for surge (inhalers/N95/nebulizers).",
    details: a,
  };
}

function normalizeSupply(data) {
  const s = data?.supply_chain_actions || data?.supply || data?.procurement || {};
  const poId = s.po_id || s.purchase_order_id || s.order_id || s.id;
  const createdFor = s.clinics || s.targets || s.affected_clinics;
  return {
    po_id: poId ?? "N/A",
    summary:
      s.summary ??
      (poId ? `PO/Request created: ${poId}` : "Inventory readiness actions prepared"),
    clinics: createdFor ?? [],
    details: s,
  };
}

function normalizeLogs(data) {
  return data?.logs || data?.reasoning_log || data?.audit_log || data?.agent_logs || [];
}

/* --------------------------
   UI helpers
--------------------------- */

function addLogEntry(agent, action, data) {
  const logContainer = document.getElementById("log");
  if (!logContainer) return;

  const entry = document.createElement("div");
  entry.className = "log-entry";
  entry.innerHTML = `
    <div class="log-header">
      <span class="log-time">${new Date().toLocaleTimeString()}</span>
      <span class="log-agent">${safe(agent)}</span>
      <span class="log-action">${safe(action)}</span>
    </div>
    <pre class="log-data">${escapeHtml(JSON.stringify(data, null, 2))}</pre>
  `;
  logContainer.prepend(entry);
}

function prettyName(key) {
  return String(key || "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function safe(v) {
  if (v === null || v === undefined) return "";
  if (typeof v === "object") return escapeHtml(JSON.stringify(v));
  return escapeHtml(String(v));
}

function escapeHtml(str) {
  return String(str)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

// ==========================================
// 2. USER UI & LOGOUT (New)
// ==========================================
async function doLogout() {
  const token = getAuthToken();
  if (token) {
    await fetch("/api/auth/logout", {
      method: "POST",
      headers: { "Authorization": `Bearer ${token}` },
    }).catch(() => {});
  }
  localStorage.removeItem("urbanpulse_token");
  localStorage.removeItem("urbanpulse_role");
  localStorage.removeItem("urbanpulse_name");
  document.cookie = "urbanpulse_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  window.location.href = "/login";
}

function renderUserBadge(containerId = "user-badge") {
  const name = localStorage.getItem("urbanpulse_name") || "Guest";
  const role = localStorage.getItem("urbanpulse_role") || "";
  const el = document.getElementById(containerId);
  if (!el) return;
  el.innerHTML = `
    <span style="font-size:0.82rem; color:#94a3b8;">
      👤 ${name}
      <span style="background:rgba(99,102,241,0.2); color:#a5b4fc; border-radius:999px; padding:2px 8px; font-size:0.72rem; margin-left:4px;">${role}</span>
    </span>
    <button onclick="doLogout()" style="margin-left:12px; font-size:0.75rem; padding:4px 10px; border-radius:6px; border:1px solid rgba(255,255,255,0.15); background:rgba(239,68,68,0.15); color:#fca5a5; cursor:pointer;">
      Sign Out
    </button>
  `;
}

// Expose to window for HTML access
window.doLogout = doLogout;
window.renderUserBadge = renderUserBadge;

// Auto-render the badge if the container exists on the page
document.addEventListener("DOMContentLoaded", () => {
  renderUserBadge("user-badge");
});