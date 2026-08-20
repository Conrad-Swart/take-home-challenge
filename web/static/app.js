const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

// ── API helper ───────────────────────────────────────────────

async function api(path, opts = {}) {
  const r = await fetch(path, { credentials: "same-origin", ...opts });
  if (!r.ok) {
    let msg = r.statusText || "request failed";
    try {
      const j = await r.json();
      if (j.detail) msg = j.detail;
    } catch {}
    throw new Error(msg);
  }
  const ct = r.headers.get("content-type") || "";
  return ct.includes("application/json") ? r.json() : r.blob();
}

async function apiJSON(path, body, method = "POST") {
  return api(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

// ── Toasts ────────────────────────────────────────────────────

function toast(message, kind = "info", ms = 2600) {
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.textContent = message;
  $("#toasts").appendChild(el);
  setTimeout(() => {
    el.style.transition = "opacity 0.2s, transform 0.2s";
    el.style.opacity = "0";
    el.style.transform = "translateX(10px)";
    setTimeout(() => el.remove(), 220);
  }, ms);
}

function show(sel, on = true) {
  const el = typeof sel === "string" ? $(sel) : sel;
  if (el) el.hidden = !on;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}

// ── Auth ──────────────────────────────────────────────────────

let currentUser = null;

async function refreshMe() {
  try {
    currentUser = await api("/api/me");
    $("#user-bar").innerHTML =
      `<span>${escapeHtml(currentUser.email)}</span>` +
      `<button id="logout">Sign out</button>`;
    $("#logout").addEventListener("click", async () => {
      await fetch("/api/logout", { method: "POST" });
      location.reload();
    });
    show("#auth", false);
    show("#dictate", true);
    show("#open-settings", true);
    $("#cleanup-slider").value = currentUser.cleanup_level;
    updateCleanupLabel(currentUser.cleanup_level);
    applyTheme(currentUser.theme);
    applyTalkMode(currentUser.talk_mode);
    updateHotkeyDisplay(currentUser.hotkey);
    hydrateSettingsUI();
    loadHistory();
  } catch {
    show("#auth", true);
    show("#dictate", false);
    show("#open-settings", false);
  }
}

$("#show-register").addEventListener("click", () => {
  show("#login-form", false);
  show("#register-form", true);
});
$("#show-login").addEventListener("click", () => {
  show("#register-form", false);
  show("#login-form", true);
});

$("#login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  try {
    await api("/api/login", { method: "POST", body: fd });
    location.reload();
  } catch (err) {
    $("#login-error").textContent = err.message;
  }
});

$("#register-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  try {
    await api("/api/register", { method: "POST", body: fd });
    location.reload();
  } catch (err) {
    $("#register-error").textContent = err.message;
  }
});

// ── Cleanup slider ────────────────────────────────────────────

function cleanupLabel(level) {
  if (level === 0)    return "Off";
  if (level <= 25)    return "Light";
  if (level <= 50)    return "Medium";
  if (level <= 75)    return "Heavy";
  return "Full";
}

function updateCleanupLabel(level) {
  $("#cleanup-label").textContent = cleanupLabel(level);
}

let cleanupSaveTimer = null;
$("#cleanup-slider").addEventListener("input", (e) => {
  const level = parseInt(e.target.value, 10);
  updateCleanupLabel(level);
  clearTimeout(cleanupSaveTimer);
  cleanupSaveTimer = setTimeout(async () => {
    try {
      await apiJSON("/api/prefs", { cleanup_level: level }, "PATCH");
    } catch (err) {
      toast(`Could not save: ${err.message}`, "error");
    }
  }, 350);
});

// ── Recording + live waveform ────────────────────────────────
// The record button is looked up freshly inside startRec/stopRec because
// applyTalkMode() replaces the button node when the talk mode changes.

const statusEl = $("#status");
const timerEl = $("#timer");
const canvas = $("#waveform");
const ctx2d = canvas.getContext("2d");

let canvasCssW = 300;
const canvasCssH = 40;

function resizeCanvas() {
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvasCssW = Math.max(160, Math.floor(rect.width));
  canvas.width = Math.floor(canvasCssW * dpr);
  canvas.height = Math.floor(canvasCssH * dpr);
  canvas.style.height = `${canvasCssH}px`;
  ctx2d.setTransform(dpr, 0, 0, dpr, 0, 0);
}

window.addEventListener("resize", () => {
  resizeCanvas();
  if (!recording) drawFlatWaveform();
});

let mediaStream = null;
let mediaRecorder = null;
let audioCtx = null;
let analyser = null;
let chunks = [];
let recording = false;
let recStart = 0;
let animFrame = null;
let timerInterval = null;

async function ensureMic() {
  if (mediaRecorder) return;
  mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  mediaRecorder = new MediaRecorder(mediaStream);
  mediaRecorder.addEventListener("dataavailable", (e) => chunks.push(e.data));
  mediaRecorder.addEventListener("stop", onRecStop);

  audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  const source = audioCtx.createMediaStreamSource(mediaStream);
  analyser = audioCtx.createAnalyser();
  analyser.fftSize = 128;
  source.connect(analyser);
}

function drawWaveform() {
  if (!analyser) return;
  animFrame = requestAnimationFrame(drawWaveform);

  const bufferLen = analyser.frequencyBinCount;
  const data = new Uint8Array(bufferLen);
  analyser.getByteFrequencyData(data);

  const w = canvasCssW;
  const h = canvasCssH;
  ctx2d.clearRect(0, 0, w, h);

  const barCount = Math.max(16, Math.min(40, Math.floor(w / 10)));
  const step = Math.floor(bufferLen / barCount);
  const gap = 3;
  const barW = (w - gap * (barCount - 1)) / barCount;

  const accent = getComputedStyle(document.body).getPropertyValue("--accent").trim() || "#040B4D";

  for (let i = 0; i < barCount; i++) {
    let sum = 0;
    for (let j = 0; j < step; j++) sum += data[i * step + j] || 0;
    const avg = sum / step;
    const norm = Math.min(1, avg / 200);
    const barH = Math.max(2, norm * (h - 4));
    const x = i * (barW + gap);
    const y = (h - barH) / 2;
    ctx2d.fillStyle = accent;
    ctx2d.globalAlpha = 0.35 + norm * 0.65;
    ctx2d.beginPath();
    const r = Math.min(2, barW / 2);
    ctx2d.roundRect(x, y, barW, barH, r);
    ctx2d.fill();
  }
  ctx2d.globalAlpha = 1;
}

function drawFlatWaveform() {
  const w = canvasCssW;
  const h = canvasCssH;
  ctx2d.clearRect(0, 0, w, h);

  const muted = getComputedStyle(document.body).getPropertyValue("--text-subtle").trim() || "#8a919d";
  ctx2d.strokeStyle = muted;
  ctx2d.globalAlpha = 0.5;
  ctx2d.lineWidth = 2;
  ctx2d.beginPath();
  ctx2d.moveTo(6, h / 2);
  ctx2d.lineTo(w - 6, h / 2);
  ctx2d.stroke();
  ctx2d.globalAlpha = 1;
}

function setStatus(text, working = false) {
  statusEl.textContent = text;
  statusEl.classList.toggle("working", working);
}

function updateTimer() {
  const sec = (performance.now() - recStart) / 1000;
  timerEl.textContent = `${sec.toFixed(1)}s`;
}

async function startRec() {
  if (recording) return;
  try {
    await ensureMic();
    if (audioCtx.state === "suspended") await audioCtx.resume();
  } catch {
    setStatus("Microphone permission denied.");
    toast("Microphone permission denied.", "error");
    return;
  }
  chunks = [];
  recStart = performance.now();
  recording = true;
  mediaRecorder.start();
  const btn = document.getElementById("record-btn");
  btn.classList.add("hot");
  const mode = currentUser && currentUser.talk_mode === "toggle" ? "toggle" : "hold";
  btn.querySelector(".record-label").textContent =
    mode === "toggle" ? "Stop" : "Recording...";
  $(".record-meta").classList.remove("idle");
  setStatus("Listening.");
  timerEl.textContent = "0.0s";
  timerInterval = setInterval(updateTimer, 100);
  drawWaveform();
}

function stopRec() {
  if (!recording) return;
  recording = false;
  mediaRecorder.stop();
  const btn = document.getElementById("record-btn");
  btn.classList.remove("hot");
  const mode = currentUser && currentUser.talk_mode === "toggle" ? "toggle" : "hold";
  btn.querySelector(".record-label").textContent =
    mode === "toggle" ? "Tap to talk" : "Hold to talk";
  $(".record-meta").classList.add("idle");
  clearInterval(timerInterval);
  cancelAnimationFrame(animFrame);
  drawFlatWaveform();
}

let continueTargetId = null;
let continueTargetTitle = null;

function startContinueMode(entry) {
  continueTargetId = entry.id;
  continueTargetTitle = entry.title;
  $("#continue-title").textContent = entry.title;
  show("#continue-chip", true);
  document.getElementById("record-btn").scrollIntoView({ behavior: "smooth", block: "center" });
  setStatus("Ready to add to this note. Hold to talk.");
}

function cancelContinueMode() {
  continueTargetId = null;
  continueTargetTitle = null;
  show("#continue-chip", false);
  setStatus("Ready.");
}

$("#continue-cancel").addEventListener("click", cancelContinueMode);

async function onRecStop() {
  const duration = (performance.now() - recStart) / 1000;
  const blob = new Blob(chunks, { type: mediaRecorder.mimeType || "audio/webm" });
  chunks = [];
  if (duration < 0.4) {
    setStatus("Too short. Try holding a bit longer.");
    return;
  }
  setStatus(continueTargetId ? "Appending" : "Transcribing", true);
  const fd = new FormData();
  fd.append("audio", blob, "clip.webm");
  fd.append("duration_s", duration.toFixed(2));

  const endpoint = continueTargetId
    ? `/api/history/${continueTargetId}/continue`
    : "/api/transcribe";

  try {
    const r = await api(endpoint, { method: "POST", body: fd });
    if (continueTargetId) {
      setStatus(`Added to "${continueTargetTitle}".`);
      toast(`Extended: ${continueTargetTitle}`, "ok");
      cancelContinueMode();
    } else {
      setStatus(`Done. ${r.mode === "cleaned" ? "Cleaned by LLM." : "Raw transcription."}`);
      toast(`Saved: ${r.title}`, "ok");
    }
    loadHistory();
  } catch (e) {
    setStatus(`Error: ${e.message}`);
    toast(e.message, "error", 4000);
  }
}

function isTypingTarget() {
  const el = document.activeElement;
  if (!el) return false;
  if (el.tagName === "INPUT" || el.tagName === "TEXTAREA") return true;
  return el.isContentEditable;
}

function toggleRec() {
  if (recording) stopRec();
  else startRec();
}

function applyTalkMode(mode) {
  // Remove any previous listeners by replacing the button node.
  const oldBtn = document.getElementById("record-btn");
  const newBtn = oldBtn.cloneNode(true);
  oldBtn.parentNode.replaceChild(newBtn, oldBtn);

  if (mode === "toggle") {
    newBtn.querySelector(".record-label").textContent =
      recording ? "Stop" : "Tap to talk";
    newBtn.addEventListener("click", toggleRec);
  } else {
    newBtn.querySelector(".record-label").textContent =
      recording ? "Recording..." : "Hold to talk";
    newBtn.addEventListener("mousedown", startRec);
    newBtn.addEventListener("touchstart", (e) => { e.preventDefault(); startRec(); });
    newBtn.addEventListener("mouseup", stopRec);
    newBtn.addEventListener("mouseleave", stopRec);
    newBtn.addEventListener("touchend", stopRec);
  }
  updateHotkeyHint();
}

// Global keyboard handler: uses currentUser.hotkey + talk_mode dynamically.
window.addEventListener("keydown", (e) => {
  if (!currentUser) return;
  if (isTypingTarget()) return;
  if (e.repeat) return;
  if (e.code !== currentUser.hotkey) return;
  e.preventDefault();
  if (currentUser.talk_mode === "toggle") {
    toggleRec();
  } else {
    startRec();
  }
});
window.addEventListener("keyup", (e) => {
  if (!currentUser) return;
  if (isTypingTarget()) return;
  if (e.code !== currentUser.hotkey) return;
  if (currentUser.talk_mode === "hold") stopRec();
});

// ── History ──────────────────────────────────────────────────

function formatWhen(iso) {
  const then = new Date(iso);
  const diff = (Date.now() - then.getTime()) / 1000;
  if (diff < 60)     return "just now";
  if (diff < 3600)   return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400)  return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 604800) return `${Math.floor(diff / 86400)}d ago`;
  return then.toLocaleDateString();
}

function formatDuration(s) {
  if (s < 60) return `${s.toFixed(1)}s`;
  const m = Math.floor(s / 60);
  const rem = Math.round(s - m * 60);
  return `${m}m ${rem}s`;
}

function makeRow(entry) {
  const li = document.createElement("li");
  li.dataset.id = entry.id;
  if (entry.pinned) li.classList.add("pinned");
  const starIcon = entry.pinned
    ? `<svg viewBox="0 0 24 24" width="16" height="16"><path fill="currentColor" d="M12 2l3.09 6.26L22 9.27l-5 4.87L18.18 22 12 18.56 5.82 22 7 14.14l-5-4.87 6.91-1.01L12 2z"/></svg>`
    : `<svg viewBox="0 0 24 24" width="16" height="16"><path fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" d="M12 3.5l2.9 5.88 6.5.94-4.7 4.58 1.11 6.47L12 18.32l-5.81 3.05L7.3 14.9 2.6 10.32l6.5-.94L12 3.5z"/></svg>`;
  li.innerHTML = `
    <div class="row-head">
      <button class="pin ${entry.pinned ? "pinned" : ""}" title="${entry.pinned ? "Unpin" : "Pin"}">${starIcon}</button>
      <div class="row-title" title="Click to edit">${escapeHtml(entry.title)}</div>
      <div class="row-time">${escapeHtml(formatWhen(entry.created_at))}</div>
    </div>
    <p class="row-text" title="Click to edit">${escapeHtml(entry.text)}</p>
    <div class="row-foot">
      <div class="badges">
        <span class="badge ${entry.mode}">${entry.mode}</span>
        <span class="badge dur">${escapeHtml(formatDuration(entry.duration_s))}</span>
      </div>
      <div class="row-actions">
        <button class="continue">Continue</button>
        <button class="copy">Copy</button>
        <button class="export">Format &amp; export</button>
        <button class="delete danger">Delete</button>
      </div>
    </div>
  `;
  wireRow(li, entry);
  return li;
}

function wireRow(li, entry) {
  const title = $(".row-title", li);
  const body = $(".row-text", li);

  const makeEditable = (el, field) => {
    el.addEventListener("click", () => {
      if (el.isContentEditable) return;
      el.contentEditable = "true";
      el.focus();
      // put caret at end
      const range = document.createRange();
      range.selectNodeContents(el);
      range.collapse(false);
      const sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
    });
    el.addEventListener("blur", async () => {
      if (!el.isContentEditable) return;
      el.contentEditable = "false";
      const value = el.textContent.trim();
      if (value === entry[field]) return;
      try {
        const patch = {};
        patch[field] = value;
        const updated = await apiJSON(`/api/history/${entry.id}`, patch, "PATCH");
        entry[field] = updated[field];
        toast(`${field === "title" ? "Title" : "Text"} updated.`, "ok", 1600);
      } catch (err) {
        toast(`Could not save: ${err.message}`, "error");
        el.textContent = entry[field];
      }
    });
    el.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && field === "title") {
        e.preventDefault();
        el.blur();
      }
      if (e.key === "Escape") {
        el.textContent = entry[field];
        el.blur();
      }
    });
  };

  makeEditable(title, "title");
  makeEditable(body, "text");

  $(".copy", li).addEventListener("click", async () => {
    await navigator.clipboard.writeText(entry.text);
    toast("Copied to clipboard.", "ok", 1400);
  });

  $(".delete", li).addEventListener("click", async () => {
    if (!confirm("Delete this transcription?")) return;
    try {
      await fetch(`/api/history/${entry.id}`, { method: "DELETE" });
      li.style.transition = "opacity 0.15s, transform 0.15s";
      li.style.opacity = "0";
      li.style.transform = "translateX(20px)";
      setTimeout(loadHistory, 150);
    } catch (err) {
      toast(`Delete failed: ${err.message}`, "error");
    }
  });

  $(".export", li).addEventListener("click", () => openExportModal(entry));

  $(".continue", li).addEventListener("click", () => startContinueMode(entry));

  $(".pin", li).addEventListener("click", async () => {
    const nowPinned = !entry.pinned;
    try {
      const updated = await apiJSON(
        `/api/history/${entry.id}`,
        { pinned: nowPinned },
        "PATCH"
      );
      entry.pinned = updated.pinned;
      loadHistory();
    } catch (err) {
      toast(`Could not update: ${err.message}`, "error");
    }
  });
}

async function loadHistory() {
  const ul = $("#history-list");
  try {
    const rows = await api("/api/history");
    $("#history-count").textContent = rows.length
      ? `${rows.length} entr${rows.length === 1 ? "y" : "ies"}`
      : "";
    ul.innerHTML = "";
    if (!rows.length) {
      const li = document.createElement("li");
      li.className = "empty";
      li.textContent = "No dictations yet. Hold the button (or Space) and speak.";
      ul.appendChild(li);
      return;
    }
    const pinned = rows.filter((r) => r.pinned);
    const rest = rows.filter((r) => !r.pinned);

    if (pinned.length) {
      const h = document.createElement("li");
      h.className = "pinned-header";
      h.textContent = "Pinned";
      ul.appendChild(h);
      pinned.forEach((r) => ul.appendChild(makeRow(r)));
      if (rest.length) {
        const div = document.createElement("li");
        div.className = "divider";
        ul.appendChild(div);
      }
    }
    rest.forEach((r) => ul.appendChild(makeRow(r)));
  } catch {
    // silently ignored — user might not be logged in yet
  }
}

// ── Export modal ─────────────────────────────────────────────

const modalBackdrop = $("#modal-backdrop");
let modalEntry = null;
let currentStyle = "raw";

function openExportModal(entry) {
  modalEntry = entry;
  currentStyle = "raw";
  $$("#style-picker .chip").forEach((c) =>
    c.classList.toggle("active", c.dataset.style === "raw")
  );
  $("#preview").value = entry.text;
  $("#preview-status").textContent = "";
  show(modalBackdrop, true);
}

function closeExportModal() {
  show(modalBackdrop, false);
  modalEntry = null;
}

$("#modal-close").addEventListener("click", closeExportModal);
modalBackdrop.addEventListener("click", (e) => {
  if (e.target === modalBackdrop) closeExportModal();
});
window.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !modalBackdrop.hidden) closeExportModal();
});

$$("#style-picker .chip").forEach((chip) => {
  chip.addEventListener("click", async () => {
    if (!modalEntry) return;
    const style = chip.dataset.style;
    $$("#style-picker .chip").forEach((c) => c.classList.toggle("active", c === chip));
    currentStyle = style;

    if (style === "raw") {
      $("#preview").value = modalEntry.text;
      $("#preview-status").textContent = "";
      return;
    }

    $("#preview-status").textContent = "Reformatting...";
    $$("#style-picker .chip").forEach((c) => (c.disabled = true));
    try {
      const r = await apiJSON("/api/reformat", {
        text: modalEntry.text,
        style,
      });
      $("#preview").value = r.text;
      if (r.changed) {
        $("#preview-status").textContent = "";
      } else {
        $("#preview-status").textContent =
          "No change. The LLM endpoint may be unreachable (check OLLAMA_URL in web/.env).";
      }
    } catch (err) {
      $("#preview-status").textContent = `Reformat failed: ${err.message}`;
    } finally {
      $$("#style-picker .chip").forEach((c) => (c.disabled = false));
    }
  });
});

$$(".format-btn").forEach((btn) => {
  btn.addEventListener("click", async () => {
    if (!modalEntry) return;
    const format = btn.dataset.fmt;
    const text = $("#preview").value;
    const title = modalEntry.title || "Transcription";
    try {
      const blob = await api("/api/export", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, title, format }),
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${title.replace(/[^A-Za-z0-9 _.-]/g, "").replace(/\s+/g, "-") || "transcription"}.${format}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast(`Downloaded .${format}`, "ok");
    } catch (err) {
      toast(`Export failed: ${err.message}`, "error", 4000);
    }
  });
});

// ── Settings modal ──────────────────────────────────────────

const settingsBackdrop = $("#settings-backdrop");

function openSettings() {
  hydrateSettingsUI();
  show(settingsBackdrop, true);
}
function closeSettings() {
  show(settingsBackdrop, false);
  stopHotkeyCapture();
}

$("#open-settings").addEventListener("click", openSettings);
$("#settings-close").addEventListener("click", closeSettings);
settingsBackdrop.addEventListener("click", (e) => {
  if (e.target === settingsBackdrop) closeSettings();
});
window.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !settingsBackdrop.hidden) closeSettings();
});

async function savePref(patch) {
  try {
    const updated = await apiJSON("/api/prefs", patch, "PATCH");
    Object.assign(currentUser, updated);
  } catch (err) {
    toast(`Could not save: ${err.message}`, "error");
  }
}

// Pretty label for a KeyboardEvent.code.
function prettyKey(code) {
  if (!code) return "?";
  if (code === "Space") return "Space";
  if (code.startsWith("Key"))    return code.slice(3);
  if (code.startsWith("Digit"))  return code.slice(5);
  if (code === "ShiftLeft"   || code === "ShiftRight")   return "Shift";
  if (code === "ControlLeft" || code === "ControlRight") return "Ctrl";
  if (code === "AltLeft"     || code === "AltRight")     return "Alt";
  if (code === "MetaLeft"    || code === "MetaRight")    return "Meta";
  if (code === "Enter") return "Enter";
  if (code === "Tab")   return "Tab";
  if (code.startsWith("Arrow")) return code.slice(5) + " arrow";
  return code;
}

function updateHotkeyDisplay(code) {
  $("#hotkey-display").textContent = prettyKey(code);
}
function updateHotkeyHint() {
  const hint = $(".hint");
  if (!hint || !currentUser) return;
  const key = prettyKey(currentUser.hotkey);
  if (currentUser.talk_mode === "toggle") {
    hint.innerHTML = `or press <kbd>${escapeHtml(key)}</kbd>`;
  } else {
    hint.innerHTML = `or hold <kbd>${escapeHtml(key)}</kbd>`;
  }
}

// Theme
function applyTheme(theme) {
  if (theme === "light" || theme === "dark") {
    document.documentElement.setAttribute("data-theme", theme);
  } else {
    document.documentElement.removeAttribute("data-theme");
  }
}

// Hotkey capture
let capturing = false;
function startHotkeyCapture() {
  capturing = true;
  const btn = $("#hotkey-capture");
  btn.classList.add("capturing");
  $("#hotkey-display").textContent = "Press any key...";
}
function stopHotkeyCapture() {
  capturing = false;
  const btn = $("#hotkey-capture");
  btn.classList.remove("capturing");
  updateHotkeyDisplay(currentUser ? currentUser.hotkey : "Space");
}
$("#hotkey-capture").addEventListener("click", () => {
  if (capturing) stopHotkeyCapture();
  else startHotkeyCapture();
});
window.addEventListener("keydown", (e) => {
  if (!capturing) return;
  // Escape cancels capture.
  if (e.key === "Escape") {
    e.preventDefault();
    e.stopImmediatePropagation();
    stopHotkeyCapture();
    return;
  }
  // Skip pure Meta (Cmd/Windows) presses to avoid breaking browser shortcuts.
  if (e.code === "MetaLeft" || e.code === "MetaRight") return;
  e.preventDefault();
  e.stopImmediatePropagation();  // prevents the recording listener from also firing
  const code = e.code;
  currentUser.hotkey = code;
  updateHotkeyDisplay(code);
  updateHotkeyHint();
  savePref({ hotkey: code });
  stopHotkeyCapture();
}, true);  // capture phase so it runs before the recording listener

// Segmented controls
function bindSegmented(sel, attr, onChange) {
  $$(`${sel} .seg`).forEach((btn) => {
    btn.addEventListener("click", () => {
      $$(`${sel} .seg`).forEach((b) => b.classList.toggle("active", b === btn));
      onChange(btn.dataset[attr]);
    });
  });
}

bindSegmented("#talk-mode-segmented", "mode", (mode) => {
  currentUser.talk_mode = mode;
  applyTalkMode(mode);
  updateTalkModeHint();
  savePref({ talk_mode: mode });
});
bindSegmented("#theme-segmented", "theme", (theme) => {
  currentUser.theme = theme;
  applyTheme(theme);
  savePref({ theme });
});

function updateTalkModeHint() {
  const el = $("#talk-mode-hint");
  if (!el || !currentUser) return;
  el.textContent = currentUser.talk_mode === "toggle"
    ? "Press once to start, press again to stop."
    : "Hold the key or button while speaking. Release to send.";
}

function hydrateSettingsUI() {
  if (!currentUser) return;
  updateHotkeyDisplay(currentUser.hotkey);
  $$("#talk-mode-segmented .seg").forEach((b) =>
    b.classList.toggle("active", b.dataset.mode === currentUser.talk_mode)
  );
  $$("#theme-segmented .seg").forEach((b) =>
    b.classList.toggle("active", b.dataset.theme === currentUser.theme)
  );
  updateTalkModeHint();
}

// ── Ask your notes ──────────────────────────────────────────

$("#ask-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const q = $("#ask-input").value.trim();
  if (!q) return;
  const btn = $(".ask-btn");
  btn.disabled = true;
  const oldLabel = btn.textContent;
  btn.textContent = "Thinking...";
  const answerBox = $("#ask-answer");
  answerBox.textContent = "";
  show(answerBox, true);
  answerBox.textContent = "Reading your notes...";
  try {
    const r = await apiJSON("/api/ask", { query: q });
    answerBox.textContent = r.answer || "No answer.";
  } catch (err) {
    answerBox.textContent = `Error: ${err.message}`;
  } finally {
    btn.disabled = false;
    btn.textContent = oldLabel;
  }
});

// ── Translate ──────────────────────────────────────────────

let languagesLoaded = false;
async function ensureLanguages() {
  if (languagesLoaded) return;
  try {
    const langs = await api("/api/languages");
    const sel = $("#translate-lang");
    for (const l of langs) {
      const opt = document.createElement("option");
      opt.value = l.code;
      opt.textContent = l.label;
      sel.appendChild(opt);
    }
    languagesLoaded = true;
  } catch {}
}

$("#translate-lang").addEventListener("change", async (e) => {
  const lang = e.target.value;
  if (!lang) return;  // "Keep language"
  const currentText = $("#preview").value.trim();
  if (!currentText) return;
  $("#preview-status").textContent = "Translating...";
  try {
    const r = await apiJSON("/api/translate", { text: currentText, language: lang });
    $("#preview").value = r.text;
    $("#preview-status").textContent = r.changed
      ? ""
      : "No change. The LLM endpoint may be unreachable.";
  } catch (err) {
    $("#preview-status").textContent = `Translate failed: ${err.message}`;
  }
});

// Reset the language select whenever the modal opens.
const origOpen = openExportModal;
openExportModal = function (entry) {
  origOpen(entry);
  $("#translate-lang").value = "";
  ensureLanguages();
};

// ── Startup ─────────────────────────────────────────────────

resizeCanvas();
drawFlatWaveform();
refreshMe();
