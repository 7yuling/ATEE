const resultList = document.getElementById("resultList");
const statusText = document.getElementById("statusText");

function formData(form) {
  return Object.fromEntries(new FormData(form).entries());
}

async function postJson(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  const data = await response.json();
  if (!response.ok && response.status !== 429) {
    throw new Error(data.error || response.statusText);
  }
  return data;
}

function safeText(node, value) {
  node.textContent = value == null ? "" : String(value);
}

function appendResult(title, payload) {
  const security = payload.security || {};
  const appeal = payload.appeal || {};
  const held = security.executed || appeal.status === 429;
  const item = document.createElement("article");
  item.className = `event${held ? " held" : ""}`;

  const heading = document.createElement("div");
  heading.className = "event-title";
  safeText(heading, title);

  const grid = document.createElement("div");
  grid.className = "event-grid";
  for (const [label, value] of [
    ["route", security.route || "-"],
    ["action", security.effective_action || appeal.status || "-"],
    ["executed", security.executed ? "true" : "false"],
    ["ok", payload.ok ? "true" : "false"]
  ]) {
    const cell = document.createElement("div");
    safeText(cell, `${label}: ${value}`);
    grid.appendChild(cell);
  }

  const message = document.createElement("div");
  message.className = "event-message";
  safeText(message, security.message_zh || appeal.reason || payload.demo_action || "-");

  item.append(heading, grid, message);
  resultList.prepend(item);
}

function bind(formId, path, title) {
  document.getElementById(formId).addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      safeText(statusText, "正在请求 ATEE Core Service...");
      const payload = await postJson(path, formData(event.currentTarget));
      appendResult(title, payload);
      safeText(statusText, "Core Service: http://127.0.0.1:8787");
    } catch (error) {
      appendResult(title, { ok: false, security: { message_zh: error.message } });
      safeText(statusText, error.message);
    }
  });
}

bind("loginForm", "/api/login", "登录链路");
bind("commentForm", "/api/comment", "评论链路");
bind("uploadForm", "/api/upload", "上传链路");
bind("appealForm", "/api/appeal", "申诉链路");
