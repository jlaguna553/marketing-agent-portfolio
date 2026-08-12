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
    <div class="post-content">${post.content}</div>
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
          <span style="font-weight:600;font-size:14px;">${msg.sender_name || msg.sender_id}</span>
        </div>
        <span class="post-date">${new Date(msg.created_at).toLocaleString("es")}</span>
      </div>
      <div class="message-text">💬 ${msg.message}</div>
      ${msg.response ? `<div class="message-response">🤖 ${msg.response}</div>` : '<div style="font-size:12px;color:var(--text-muted);margin-top:8px;">Sin respuesta automática</div>'}
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
      ✅ <strong>Respuesta enviada:</strong> ${t.operator_answer}
    </div>` : "");

  card.innerHTML = `
    <div class="ticket-header">
      <div class="ticket-meta">
        ${platformBadge}
        ${statusBadge}
        <span style="font-weight:600;font-size:14px;">${t.sender_name || t.sender_id}</span>
      </div>
      <span class="post-date">${date}</span>
    </div>
    <div class="ticket-question">❓ ${t.extracted_question}</div>
    <div class="ticket-original">Mensaje original: "${t.original_message}"</div>
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
        <div class="kb-question">P: ${e.question}</div>
        <div class="kb-answer">R: ${e.answer}</div>
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
