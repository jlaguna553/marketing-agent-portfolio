/* ── State ─────────────────────────────────────────────────── */
let ws = null;
let isStreaming = false;
let currentBubble = null;
let currentText = "";

/* ── Init ──────────────────────────────────────────────────── */
document.addEventListener("DOMContentLoaded", () => {
  initWebSocket();
  loadConfig();
  setupTabs();
  setupInput();
  refreshTicketBadge();
  initCrmTabs();
  // Permite abrir una pestaña directo: http://localhost:8000/#crm
  const hash = location.hash.slice(1);
  if (hash) setTimeout(() => document.querySelector(`.nav-btn[data-tab="${hash}"]`)?.click(), 300);
  // Refrescar badge de tickets cada 30 segundos
  setInterval(refreshTicketBadge, 30000);
});

/* ── WebSocket ─────────────────────────────────────────────── */
function initWebSocket() {
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${protocol}://${location.host}/api/chat/ws`);

  ws.onopen = () => setConnectionStatus(true);
  ws.onclose = () => {
    setConnectionStatus(false);
    setTimeout(initWebSocket, 3000); // Reconectar automáticamente
  };
  ws.onerror = () => setConnectionStatus(false);

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    handleServerMessage(data);
  };
}

function setConnectionStatus(connected) {
  const dot = document.getElementById("connection-status");
  const label = document.getElementById("connection-label");
  dot.className = "status-dot " + (connected ? "connected" : "disconnected");
  label.textContent = connected ? "Conectado" : "Desconectado";
}

function handleServerMessage(data) {
  if (data.type === "delta") {
    if (!currentBubble) {
      currentBubble = appendMessage("assistant", "");
    }
    currentText += data.text;
    currentBubble.innerHTML = renderMarkdown(currentText);
    scrollToBottom();
  } else if (data.type === "done") {
    currentBubble = null;
    currentText = "";
    setStreaming(false);
  } else if (data.type === "tool_result") {
    appendToolNotification(data.message);
  }
}

/* ── Send ──────────────────────────────────────────────────── */
function sendMessage() {
  const input = document.getElementById("chat-input");
  const text = input.value.trim();
  if (!text || isStreaming || !ws || ws.readyState !== WebSocket.OPEN) return;

  // Ocultar welcome si existe
  const welcome = document.querySelector(".welcome-message");
  if (welcome) welcome.remove();

  appendMessage("user", text);
  input.value = "";
  autoResizeInput(input);

  // Typing indicator
  appendTypingIndicator();

  ws.send(JSON.stringify({ message: text }));
  setStreaming(true);
}

function sendQuick(text) {
  const input = document.getElementById("chat-input");
  input.value = text;
  sendMessage();
}

/* ── Message Rendering ─────────────────────────────────────── */
function appendMessage(role, content) {
  removeTypingIndicator();
  const container = document.getElementById("chat-messages");
  const msg = document.createElement("div");
  msg.className = `message ${role}`;

  const avatar = document.createElement("div");
  avatar.className = "message-avatar";
  avatar.textContent = role === "assistant" ? "🤖" : "👤";

  const bubble = document.createElement("div");
  bubble.className = "message-bubble";
  bubble.innerHTML = renderMarkdown(content);

  msg.appendChild(avatar);
  msg.appendChild(bubble);
  container.appendChild(msg);
  scrollToBottom();
  return bubble;
}

function appendToolNotification(message) {
  removeTypingIndicator();
  const container = document.getElementById("chat-messages");
  const notif = document.createElement("div");
  notif.className = "tool-notification";
  notif.textContent = message;
  container.appendChild(notif);
  scrollToBottom();
}

function appendTypingIndicator() {
  removeTypingIndicator();
  const container = document.getElementById("chat-messages");
  const msg = document.createElement("div");
  msg.className = "message assistant";
  msg.id = "typing-indicator-msg";

  const avatar = document.createElement("div");
  avatar.className = "message-avatar";
  avatar.textContent = "🤖";

  const bubble = document.createElement("div");
  bubble.className = "message-bubble";
  bubble.innerHTML = `<div class="typing-indicator"><span></span><span></span><span></span></div>`;

  msg.appendChild(avatar);
  msg.appendChild(bubble);
  container.appendChild(msg);
  scrollToBottom();
}

function removeTypingIndicator() {
  const indicator = document.getElementById("typing-indicator-msg");
  if (indicator) indicator.remove();
}

/* ── Simple Markdown renderer ──────────────────────────────── */
function renderMarkdown(text) {
  return text
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    // Code blocks
    .replace(/```json([\s\S]*?)```/g, (_, code) => {
      try {
        const parsed = JSON.parse(code.trim());
        return renderPostCard(parsed);
      } catch {
        return `<pre><code>${code}</code></pre>`;
      }
    })
    .replace(/```[\w]*\n?([\s\S]*?)```/g, "<pre><code>$1</code></pre>")
    // Inline code
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    // Bold
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    // Italic
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    // Line breaks
    .replace(/\n/g, "<br>");
}

function renderPostCard(data) {
  if (!data.post_content) return "";
  const platform = data.platform || "all";
  const hashtags = (data.hashtags || []).join(" ");
  return `
    <div style="background:rgba(99,102,241,0.08);border:1px solid rgba(99,102,241,0.25);border-radius:10px;padding:14px;margin:6px 0;">
      <div style="font-size:12px;color:#8b90b5;margin-bottom:8px;">📝 Post generado · <span class="badge badge-${platform}">${platform}</span></div>
      <div style="white-space:pre-wrap;font-size:14px;">${data.post_content}</div>
      ${hashtags ? `<div style="margin-top:8px;color:#6366f1;font-size:13px;">${hashtags}</div>` : ""}
      ${data.image_suggestion ? `<div style="margin-top:6px;font-size:12px;color:#8b90b5;">🖼️ Imagen sugerida: ${data.image_suggestion}</div>` : ""}
      ${data.best_time ? `<div style="margin-top:4px;font-size:12px;color:#eab308;">⏰ Mejor hora: ${data.best_time}</div>` : ""}
    </div>`;
}

/* ── Posts Tab ─────────────────────────────────────────────── */
async function loadPosts(status = "") {
  document.querySelectorAll(".filter-btn").forEach(b => b.classList.remove("active"));
  event?.target?.classList?.add("active");

  const list = document.getElementById("posts-list");
  list.innerHTML = '<div class="loading">Cargando...</div>';

  const url = status ? `/api/posts/?status=${status}` : "/api/posts/";
  const res = await fetch(url);
  const posts = await res.json();

  if (!posts.length) {
    list.innerHTML = '<div class="empty-state"><div class="empty-icon">📭</div><p>No hay posts aún. ¡Pídeselos al agente!</p></div>';
    return;
  }

  list.innerHTML = "";
  for (const post of posts) {
    list.appendChild(buildPostCard(post));
  }
}

function buildPostCard(post) {
  const card = document.createElement("div");
  card.className = "post-card";
  card.id = `post-${post.id}`;

  const scheduledDate = post.scheduled_at ? new Date(post.scheduled_at).toLocaleString("es") : null;
  const publishedDate = post.published_at ? new Date(post.published_at).toLocaleString("es") : null;

  card.innerHTML = `
    <div class="post-card-header">
      <div class="post-meta">
        <span class="badge badge-${post.status}">${statusLabel(post.status)}</span>
        <span class="badge badge-${post.platform}">${post.platform}</span>
      </div>
      <span class="post-date">${new Date(post.created_at).toLocaleDateString("es")}</span>
    </div>
    <div class="post-content">${esc(post.content)}</div>
    ${scheduledDate ? `<div class="post-date" style="margin-top:8px;">📅 Programado: ${scheduledDate}</div>` : ""}
    ${publishedDate ? `<div class="post-date" style="margin-top:8px;">✅ Publicado: ${publishedDate}</div>` : ""}
    ${post.error_message ? `<div style="color:#ef4444;font-size:12px;margin-top:8px;">⚠️ ${post.error_message}</div>` : ""}
    <div class="post-actions">
      ${post.status !== "published" ? `<button class="btn-sm btn-publish" onclick="publishPost(${post.id})">🚀 Publicar ahora</button>` : ""}
      ${post.status !== "published" ? `<button class="btn-sm btn-delete" onclick="deletePost(${post.id})">🗑️ Eliminar</button>` : ""}
    </div>
  `;
  return card;
}

function statusLabel(s) {
  return { draft: "Borrador", scheduled: "Programado", published: "Publicado", failed: "Error" }[s] || s;
}

async function publishPost(id) {
  const btn = document.querySelector(`#post-${id} .btn-publish`);
  if (btn) { btn.disabled = true; btn.textContent = "Publicando..."; }

  const res = await fetch(`/api/posts/${id}/publish`, { method: "POST" });
  const data = await res.json();

  if (data.status === "published") {
    showToast("✅ Post publicado exitosamente");
  } else {
    showToast("⚠️ Error al publicar: " + (data.errors?.join(", ") || "desconocido"), true);
  }
  loadPosts();
}

async function deletePost(id) {
  if (!confirm("¿Eliminar este post?")) return;
  await fetch(`/api/posts/${id}`, { method: "DELETE" });
  document.getElementById(`post-${id}`)?.remove();
  showToast("🗑️ Post eliminado");
}

/* ── Messages Tab ──────────────────────────────────────────── */
async function loadMessages(platform = "") {
  document.querySelectorAll("#tab-messages .filter-btn").forEach(b => b.classList.remove("active"));
  event?.target?.classList?.add("active");

  const list = document.getElementById("messages-list");
  list.innerHTML = '<div class="loading">Cargando...</div>';

  const url = platform ? `/webhook/messages?platform=${platform}` : "/webhook/messages";
  const res = await fetch(url);
  const messages = await res.json();

  if (!messages.length) {
    list.innerHTML = '<div class="empty-state"><div class="empty-icon">💬</div><p>No hay mensajes de clientes aún.</p></div>';
    return;
  }

  list.innerHTML = "";
  for (const msg of messages) {
    const card = document.createElement("div");
    card.className = "message-card";
    card.innerHTML = `
      <div class="message-card-header">
        <div style="display:flex;align-items:center;gap:10px;">
          <span class="badge badge-${msg.platform}">${msg.platform}</span>
          <span style="font-weight:600;font-size:14px;">${esc(msg.sender_name || msg.sender_id)}</span>
        </div>
        <span class="post-date">${new Date(msg.created_at).toLocaleString("es")}</span>
      </div>
      <div class="message-text">${msg.direction === "out" ? "📤 (enviado por nosotros) " : "💬 "}${esc(msg.message)}</div>
      ${msg.response ? `<div class="message-response">🤖 ${esc(msg.response)}</div>` : '<div style="font-size:12px;color:var(--text-muted);margin-top:8px;">Sin respuesta automática</div>'}
    `;
    list.appendChild(card);
  }
}

/* ── Tickets Tab ───────────────────────────────────────────── */
async function loadTickets(status = "open") {
  document.querySelectorAll("#tab-tickets .filter-btn").forEach(b => b.classList.remove("active"));
  event?.target?.classList?.add("active");

  const list = document.getElementById("tickets-list");
  list.innerHTML = '<div class="loading">Cargando...</div>';

  const res = await fetch(`/api/tickets/?status=${status}`);
  const tickets = await res.json();

  if (!tickets.length) {
    const label = status === "open" ? "No hay tickets abiertos. El agente está respondiendo todo 🎉" : "No hay tickets en esta categoría.";
    list.innerHTML = `<div class="empty-state"><div class="empty-icon">🎫</div><p>${label}</p></div>`;
    return;
  }

  list.innerHTML = "";
  for (const t of tickets) {
    list.appendChild(buildTicketCard(t));
  }
}

function buildTicketCard(t) {
  const card = document.createElement("div");
  card.className = `ticket-card ${t.status}`;
  card.id = `ticket-${t.id}`;

  const date = new Date(t.created_at).toLocaleString("es");
  const platformBadge = `<span class="badge badge-${t.platform}">${t.platform}</span>`;
  const statusBadge = {
    open: '<span class="badge badge-scheduled">Abierto</span>',
    answered: '<span class="badge badge-published">Respondido</span>',
    dismissed: '<span class="badge badge-draft">Descartado</span>',
  }[t.status] || "";

  const answerSection = t.status === "open" ? `
    <div class="ticket-answer-form">
      <textarea id="ta-${t.id}" placeholder="Escribe aquí la respuesta para el cliente y se le enviará por ${t.platform}..."></textarea>
      <div class="ticket-answer-actions">
        <button class="btn-sm btn-publish" onclick="answerTicket(${t.id})">📤 Enviar al cliente</button>
        <button class="btn-sm btn-delete" onclick="dismissTicket(${t.id})">✗ Descartar</button>
        <label class="ticket-kb-check">
          <input type="checkbox" id="kb-${t.id}" checked />
          Guardar en Base de Conocimiento
        </label>
      </div>
    </div>` : (t.operator_answer ? `
    <div class="ticket-answered-text">
      ✅ <strong>Respuesta enviada:</strong> ${esc(t.operator_answer)}
    </div>` : "");

  card.innerHTML = `
    <div class="ticket-header">
      <div class="ticket-meta">
        ${platformBadge}
        ${statusBadge}
        <span style="font-weight:600;font-size:14px;">${esc(t.sender_name || t.sender_id)}</span>
      </div>
      <span class="post-date">${date}</span>
    </div>
    <div class="ticket-question">❓ ${esc(t.extracted_question)}</div>
    <div class="ticket-original">Mensaje original: "${esc(t.original_message)}"</div>
    ${answerSection}
  `;
  return card;
}

async function answerTicket(id) {
  const textarea = document.getElementById(`ta-${id}`);
  const saveKb = document.getElementById(`kb-${id}`)?.checked ?? true;
  const answer = textarea?.value.trim();
  if (!answer) { showToast("Escribe una respuesta antes de enviar", true); return; }

  const btn = document.querySelector(`#ticket-${id} .btn-publish`);
  if (btn) { btn.disabled = true; btn.textContent = "Enviando..."; }

  const res = await fetch(`/api/tickets/${id}/answer`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ answer, save_to_kb: saveKb })
  });
  const data = await res.json();

  if (data.status === "answered") {
    showToast(data.answer_sent ? "✅ Respuesta enviada al cliente" : "⚠️ Guardado pero no se pudo enviar al cliente");
    if (saveKb) showToast("📚 Guardado en Base de Conocimiento");
  } else {
    showToast("Error al responder", true);
  }
  loadTickets("open");
  refreshTicketBadge();
}

async function dismissTicket(id) {
  await fetch(`/api/tickets/${id}/dismiss`, { method: "POST" });
  document.getElementById(`ticket-${id}`)?.remove();
  refreshTicketBadge();
  showToast("Ticket descartado");
}

async function refreshTicketBadge() {
  try {
    const res = await fetch("/api/tickets/count");
    const data = await res.json();
    const badge = document.getElementById("ticket-badge");
    if (data.open > 0) {
      badge.textContent = data.open;
      badge.style.display = "inline-block";
    } else {
      badge.style.display = "none";
    }
  } catch {}
}

/* ── Knowledge Base Tab ────────────────────────────────────── */
async function loadKnowledge() {
  const list = document.getElementById("knowledge-list");
  list.innerHTML = '<div class="loading">Cargando...</div>';

  const res = await fetch("/api/knowledge/");
  const entries = await res.json();

  if (!entries.length) {
    list.innerHTML = '<div class="empty-state"><div class="empty-icon">📚</div><p>La base de conocimiento está vacía.<br>Agrega entradas manuales o responde tickets para llenarla.</p></div>';
    return;
  }

  list.innerHTML = "";
  for (const e of entries) {
    const card = document.createElement("div");
    card.className = "kb-card";
    card.id = `kb-entry-${e.id}`;
    card.innerHTML = `
      <div class="kb-card-body">
        <div class="kb-cat">${e.category}</div>
        <div class="kb-question">P: ${esc(e.question)}</div>
        <div class="kb-answer">R: ${esc(e.answer)}</div>
      </div>
      <div class="kb-actions">
        <button class="btn-sm btn-delete" onclick="deleteKBEntry(${e.id})">🗑️</button>
      </div>
    `;
    list.appendChild(card);
  }
}

function showAddKBForm() {
  document.getElementById("kb-form").style.display = "block";
  document.getElementById("kb-question").focus();
}

function hideAddKBForm() {
  document.getElementById("kb-form").style.display = "none";
  document.getElementById("kb-question").value = "";
  document.getElementById("kb-answer").value = "";
}

async function saveKBEntry() {
  const question = document.getElementById("kb-question").value.trim();
  const answer = document.getElementById("kb-answer").value.trim();
  const category = document.getElementById("kb-category").value;
  if (!question || !answer) { showToast("Completa la pregunta y la respuesta", true); return; }

  const res = await fetch("/api/knowledge/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, answer, category })
  });
  if (res.ok) {
    hideAddKBForm();
    loadKnowledge();
    showToast("📚 Entrada agregada a la Base de Conocimiento");
  }
}

async function deleteKBEntry(id) {
  if (!confirm("¿Eliminar esta entrada?")) return;
  await fetch(`/api/knowledge/${id}`, { method: "DELETE" });
  document.getElementById(`kb-entry-${id}`)?.remove();
  showToast("Entrada eliminada");
}

/* ── Tabs ──────────────────────────────────────────────────── */
function setupTabs() {
  document.querySelectorAll(".nav-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const tab = btn.dataset.tab;
      document.querySelectorAll(".nav-btn").forEach(b => b.classList.remove("active"));
      document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById(`tab-${tab}`)?.classList.add("active");
      if (tab === "posts") loadPosts();
      if (tab === "messages") loadMessages();
      if (tab === "tickets") loadTickets("open");
      if (tab === "knowledge") loadKnowledge();
      if (tab === "crm") loadCrm();
      if (tab === "sim") loadSim();
      if (tab === "studio") initStudio();
    });
  });
}

/* ── Input auto-resize & keyboard ─────────────────────────── */
function setupInput() {
  const input = document.getElementById("chat-input");
  input.addEventListener("input", () => autoResizeInput(input));
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });
}

function autoResizeInput(el) {
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, 160) + "px";
}

/* ── Helpers ───────────────────────────────────────────────── */
function setStreaming(val) {
  isStreaming = val;
  document.getElementById("send-btn").disabled = val;
}

function scrollToBottom() {
  const c = document.getElementById("chat-messages");
  c.scrollTop = c.scrollHeight;
}

async function loadConfig() {
  try {
    const res = await fetch("/api/config");
    const data = await res.json();
    document.getElementById("business-name").textContent = data.business_name || "Mi Negocio";

    // Mostrar proveedor IA activo
    const label = document.getElementById("connection-label");
    if (data.llm_provider === "ollama") {
      label.textContent = `Ollama · ${data.ollama_model || "local"}`;
      // Verificar que Ollama responde
      try {
        const health = await fetch("/api/health/ollama");
        const hdata = await health.json();
        if (!hdata.ok) {
          showToast("⚠️ " + hdata.message, true);
        }
      } catch {}
    } else {
      label.textContent = "Claude (Anthropic)";
    }
  } catch {}
}

function showToast(message, isError = false) {
  const toast = document.createElement("div");
  toast.textContent = message;
  Object.assign(toast.style, {
    position: "fixed", bottom: "24px", right: "24px",
    background: isError ? "#7f1d1d" : "#14532d",
    color: "white", padding: "12px 20px",
    borderRadius: "10px", fontSize: "14px",
    zIndex: 9999, boxShadow: "0 4px 20px rgba(0,0,0,0.4)",
    transition: "opacity 0.3s"
  });
  document.body.appendChild(toast);
  setTimeout(() => { toast.style.opacity = "0"; setTimeout(() => toast.remove(), 300); }, 3000);
}


/* ── Utilidades ────────────────────────────────────────────── */
function esc(v) {
  return String(v ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/* ── CRM ───────────────────────────────────────────────────── */
const CRM_STATUSES = { new: "Nuevo", contacted: "Contactado", scheduled: "Agendado", won: "Cliente", lost: "Perdido" };
let crmFilter = "";
let crmOpenId = null;

async function initCrmTabs() {
  try {
    const cfg = await (await fetch("/api/config")).json();
    if (cfg.mock_mode) {
      document.getElementById("nav-sim").style.display = "";
      document.getElementById("mock-banner").style.display = "";
    }
  } catch (_) {}
}

async function loadCrm(status = crmFilter) {
  crmFilter = status;
  document.querySelectorAll("#crm-filters .filter-btn").forEach(b => b.classList.toggle("active", b.dataset.status === status));
  const [stats, leads] = await Promise.all([
    fetch("/api/leads/stats").then(r => r.json()),
    fetch("/api/leads/" + (status ? `?status=${status}` : "")).then(r => r.json()),
  ]);
  document.getElementById("crm-stats").innerHTML = Object.entries(CRM_STATUSES).map(([k, label]) =>
    `<div class="crm-stat"><div class="crm-stat-n">${stats.by_status[k] ?? 0}</div><div>${label}</div></div>`
  ).join("") + `<div class="crm-stat crm-stat-hot"><div class="crm-stat-n">${stats.booking_intent}</div><div>Pidieron agendar</div></div>`;

  const list = document.getElementById("crm-list");
  if (!leads.length) {
    list.innerHTML = '<div class="empty-state"><div class="empty-icon">👥</div><p>Aún no hay contactos. Cuando alguien escriba aparecerá aquí.</p></div>';
    return;
  }
  list.innerHTML = leads.map(l => `
    <div class="lead-card" data-id="${l.id}">
      <div class="lead-row" onclick="toggleLead(${l.id})">
        <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
          <span class="badge badge-${esc(l.platform)}">${esc(l.platform)}</span>
          <strong>${esc(l.sender_name || l.sender_id)}</strong>
          ${l.intent === "booking" ? '<span class="badge badge-scheduled">📅 quiere agendar</span>' : ""}
          ${l.followups_sent ? `<span class="badge badge-draft">seguimientos: ${l.followups_sent}</span>` : ""}
        </div>
        <select onclick="event.stopPropagation()" onchange="setLeadStatus(${l.id}, this.value)">
          ${Object.entries(CRM_STATUSES).map(([k, v]) => `<option value="${k}" ${k === l.status ? "selected" : ""}>${v}</option>`).join("")}
        </select>
      </div>
      <div class="lead-first">“${esc(l.first_message)}”</div>
      <div class="lead-detail" id="lead-detail-${l.id}" style="display:none"></div>
    </div>`).join("");
  if (crmOpenId) toggleLead(crmOpenId, true);
}

async function setLeadStatus(id, status) {
  await fetch(`/api/leads/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status }) });
  showToast("Estado actualizado");
  loadCrm();
}

async function toggleLead(id, forceOpen = false) {
  const box = document.getElementById(`lead-detail-${id}`);
  if (!box) return;
  if (!forceOpen && box.style.display !== "none") { box.style.display = "none"; crmOpenId = null; return; }
  crmOpenId = id;
  const d = await (await fetch(`/api/leads/${id}`)).json();
  const who = { client: "👤", bot: "🤖", owner: "🧑‍💻" };
  box.innerHTML = `
    <div class="thread">${d.thread.map(t => `<div class="thread-msg thread-${t.from}"><span>${who[t.from]}</span> ${esc(t.text)}</div>`).join("") || "<em>Sin mensajes</em>"}</div>
    <textarea id="lead-notes-${id}" rows="2" placeholder="Notas internas...">${esc(d.notes || "")}</textarea>
    <div class="lead-actions">
      <button class="btn-secondary" onclick="saveLeadNotes(${id})">Guardar notas</button>
      <input id="lead-reply-${id}" type="text" placeholder="Responder por ${esc(d.platform)}..." onkeydown="if(event.key==='Enter')replyLead(${id})" />
      <button class="btn-primary" onclick="replyLead(${id})">Enviar</button>
    </div>`;
  box.style.display = "block";
}

async function saveLeadNotes(id) {
  const notes = document.getElementById(`lead-notes-${id}`).value;
  await fetch(`/api/leads/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ notes }) });
  showToast("Notas guardadas");
}

async function replyLead(id) {
  const input = document.getElementById(`lead-reply-${id}`);
  const text = input.value.trim();
  if (!text) return;
  const res = await fetch(`/api/leads/${id}/reply`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }) });
  if (!res.ok) { showToast((await res.json()).detail || "No se pudo enviar", true); return; }
  showToast("Mensaje enviado");
  loadCrm();
}

/* ── Simulador (solo modo local) ───────────────────────────── */
async function loadSim() { refreshOutbox(); }

async function simSend() {
  const channel = document.getElementById("sim-channel").value;
  const sender_id = document.getElementById("sim-sender").value.trim() || "5210000000001";
  const name = document.getElementById("sim-name").value.trim() || "Cliente de prueba";
  const text = document.getElementById("sim-text").value.trim();
  if (!text) return;
  const res = await fetch("/api/dev/simulate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ channel, sender_id, name, text }) });
  if (!res.ok) { showToast("Error al simular", true); return; }
  document.getElementById("sim-text").value = "";
  await refreshOutbox();
  refreshTicketBadge();
}

async function simFollowups() {
  const r = await (await fetch("/api/dev/run-followups?force=true", { method: "POST" })).json();
  showToast(`Seguimientos enviados: ${r.sent}`);
  refreshOutbox();
}

async function refreshOutbox() {
  const rows = await (await fetch("/api/dev/outbox?limit=30")).json();
  const icon = { message: "💬", post: "📣", owner_alert: "🔔", read: "👁️" };
  document.getElementById("sim-outbox").innerHTML = rows.length
    ? rows.map(r => `<div class="outbox-row"><span class="badge badge-${esc(r.channel)}">${esc(r.channel)}</span> ${icon[r.kind] || ""} <span class="outbox-to">→ ${esc(r.recipient || "página")}</span><div>${esc(r.content)}</div></div>`).join("")
    : '<div class="empty-state"><p>Aún no se ha “enviado” nada.</p></div>';
}


/* ── Estudio de posts ──────────────────────────────────────── */
let stImages = [];      // File[]
let stId = null;        // id de la plantilla generada
let stInit = false;

async function initStudio() {
  if (stInit) return;
  stInit = true;
  const drop = document.getElementById("st-drop");
  const files = document.getElementById("st-files");
  files.addEventListener("change", () => { stAddFiles(files.files); files.value = ""; });
  drop.addEventListener("dragover", e => { e.preventDefault(); drop.classList.add("over"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("over"));
  drop.addEventListener("drop", e => { e.preventDefault(); drop.classList.remove("over"); stAddFiles(e.dataTransfer.files); });
  document.addEventListener("paste", e => {
    if (!document.getElementById("tab-studio").classList.contains("active")) return;
    const imgs = [...(e.clipboardData?.files || [])].filter(f => f.type.startsWith("image/"));
    if (imgs.length) { e.preventDefault(); stAddFiles(imgs); }
  });
  try {
    const s = await (await fetch("/api/studio/status")).json();
    document.getElementById("studio-badge").textContent = s.worker_configured ? "Worker conectado" : (s.simulated ? "🧪 Texto simulado (local)" : "⚠️ Falta STUDIO_WORKER_URL");
  } catch (_) {}
}

function stAddFiles(list) {
  for (const f of list) {
    if (!f.type.startsWith("image/")) continue;
    if (stImages.length >= 4) { showToast("Máximo 4 imágenes"); break; }
    if (f.size > 8 * 1024 * 1024) { showToast(`${f.name} pesa más de 8 MB`); continue; }
    stImages.push(f);
  }
  stRenderThumbs();
}

function stRenderThumbs() {
  const box = document.getElementById("st-thumbs");
  box.innerHTML = "";
  stImages.forEach((f, i) => {
    const wrap = document.createElement("div");
    wrap.className = "studio-thumb";
    const img = document.createElement("img");
    img.src = URL.createObjectURL(f);
    img.alt = "";
    const x = document.createElement("button");
    x.type = "button"; x.textContent = "×"; x.title = "Quitar";
    x.onclick = () => { stImages.splice(i, 1); stRenderThumbs(); };
    wrap.append(img, x);
    box.appendChild(wrap);
  });
}

function stError(msg) { document.getElementById("st-error").textContent = msg || ""; }

async function studioGenerate() {
  const campaign = document.getElementById("st-campaign").value.trim();
  if (campaign.length < 10) return stError("Describe la campaña (mínimo 10 caracteres).");
  stError("");
  const btn = document.getElementById("st-go");
  btn.disabled = true; btn.textContent = "Generando...";
  const fd = new FormData();
  fd.append("campaign", campaign);
  fd.append("network", document.getElementById("st-network").value);
  fd.append("tone", document.getElementById("st-tone").value);
  fd.append("cta", document.getElementById("st-cta").value.trim());
  stImages.forEach(f => fd.append("images", f));
  try {
    const r = await fetch("/api/studio/generate", { method: "POST", body: fd });
    const j = await r.json();
    if (!r.ok) throw new Error(j.detail?.message || "No se pudo generar el post");
    stId = j.id;
    const p = j.post;
    document.getElementById("st-headline").value = p.headline;
    document.getElementById("st-cta2").value = p.cta;
    document.getElementById("st-fb").value = p.facebook || "";
    document.getElementById("st-ig").value = [p.instagram, (p.hashtags || []).join(" ")].filter(Boolean).join("\n\n");
    stShowImage(j.image_url);
    const warn = document.getElementById("st-warn");
    warn.textContent = (j.warnings || []).length ? "⚠️ " + j.warnings.join(" · ") + " — revisa antes de publicar." : "";
    const facts = document.getElementById("st-facts");
    facts.textContent = j.facts_used?.length ? "Datos de tu base usados: " + j.facts_used.join(" | ") : "";
    document.getElementById("st-result").style.display = "";
  } catch (e) {
    stError(e.message);
  } finally {
    btn.disabled = false; btn.textContent = "✨ Generar post";
  }
}

function stShowImage(url) {
  document.getElementById("st-preview").src = "/" + url + "?t=" + Date.now();
}

async function studioRender() {
  if (!stId) return;
  const r = await fetch("/api/studio/render", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: stId, headline: document.getElementById("st-headline").value, cta: document.getElementById("st-cta2").value }),
  });
  if (r.ok) stShowImage((await r.json()).image_url); else showToast("No se pudo actualizar la imagen");
}

async function studioSave(platform) {
  if (!stId) return;
  const content = document.getElementById(platform === "facebook" ? "st-fb" : "st-ig").value.trim();
  if (!content) return showToast("El texto está vacío");
  const when = document.getElementById("st-when").value;
  const r = await fetch("/api/studio/save", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: stId, content, platform, scheduled_at: when || null }),
  });
  const j = await r.json();
  showToast(r.ok ? (j.status === "scheduled" ? "Post programado ✅" : "Borrador guardado ✅") : (j.detail?.message || "No se pudo guardar"));
}
