const resultList = document.getElementById("resultList");
const statusText = document.getElementById("statusText");
const topicList = document.getElementById("topicList");
const postList = document.getElementById("postList");
const topicCount = document.getElementById("topicCount");
const topicTotal = document.getElementById("topicTotal");
const postTotal = document.getElementById("postTotal");
const userTotal = document.getElementById("userTotal");
const topicIdInput = document.getElementById("topicIdInput");
const activeTopicLabel = document.getElementById("activeTopicLabel");

let activeTopicId = 1;
let topicsCache = [];

function formData(form) {
  return Object.fromEntries(new FormData(form).entries());
}

async function getJson(path) {
  const response = await fetch(path, { headers: { "Accept": "application/json" } });
  return response.json();
}

async function postJson(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  const data = await response.json();
  if (!response.ok && response.status !== 429) {
    throw new Error(data.error || data.detail || response.statusText);
  }
  return data;
}

function safeText(node, value) {
  node.textContent = value == null ? "" : String(value);
}

function setStatus(value) {
  safeText(statusText, value);
}

function restoreStatus() {
  setStatus("ATEE Core: http://127.0.0.1:8787");
}

function appendResult(title, payload) {
  const security = payload.security || {};
  const appeal = payload.appeal || {};
  const held = Boolean(security.executed || appeal.status === 429 || (payload.ok === false && security.route));
  const item = document.createElement("article");
  item.className = `event${held ? " held" : ""}`;

  const heading = document.createElement("div");
  heading.className = "event-title";
  safeText(heading, title);

  const grid = document.createElement("div");
  grid.className = "event-grid";
  const rows = [
    ["route", security.route || "-"],
    ["action", security.effective_action || appeal.status || payload.error || "-"],
    ["executed", security.executed ? "true" : "false"],
    ["ok", payload.ok ? "true" : "false"]
  ];
  for (const [label, value] of rows) {
    const cell = document.createElement("div");
    safeText(cell, `${label}: ${value}`);
    grid.appendChild(cell);
  }

  const message = document.createElement("div");
  message.className = "event-message";
  safeText(message, security.message_zh || appeal.reason || payload.demo_action || payload.error || "-");

  item.append(heading, grid, message);
  resultList.prepend(item);
}

function renderStats(stats) {
  safeText(topicTotal, stats.topics ?? "-");
  safeText(postTotal, stats.posts ?? "-");
  safeText(userTotal, stats.users ?? "-");
}

function renderTopics(topics) {
  topicsCache = Array.isArray(topics) ? topics : [];
  safeText(topicCount, topicsCache.length);
  topicList.replaceChildren();

  if (!topicsCache.length) {
    const empty = document.createElement("p");
    empty.className = "empty";
    safeText(empty, "暂无话题");
    topicList.appendChild(empty);
    return;
  }

  if (!topicsCache.some((topic) => topic.id === activeTopicId)) {
    activeTopicId = topicsCache[0].id;
  }

  for (const topic of topicsCache) {
    const card = document.createElement("button");
    card.type = "button";
    card.className = `topic-card${topic.id === activeTopicId ? " active" : ""}`;
    card.addEventListener("click", () => selectTopic(topic.id));

    const title = document.createElement("span");
    title.className = "topic-title";
    safeText(title, topic.title);

    const meta = document.createElement("span");
    meta.className = "topic-meta";
    safeText(meta, `${topic.author_name || "system"} · ${topic.post_count || 0} 条发言`);

    const desc = document.createElement("span");
    desc.className = "topic-desc";
    safeText(desc, topic.description || "无描述");

    card.append(title, meta, desc);
    topicList.appendChild(card);
  }
}

function renderPosts(posts) {
  postList.replaceChildren();
  const activeTopic = topicsCache.find((topic) => topic.id === activeTopicId);
  safeText(activeTopicLabel, activeTopic ? `#${activeTopic.id} ${activeTopic.title}` : "请选择话题");
  topicIdInput.value = String(activeTopicId);

  if (!Array.isArray(posts) || !posts.length) {
    const empty = document.createElement("p");
    empty.className = "empty";
    safeText(empty, "这个话题还没有发言");
    postList.appendChild(empty);
    return;
  }

  for (const post of posts) {
    const item = document.createElement("article");
    item.className = "post";

    const author = document.createElement("div");
    author.className = "post-author";
    safeText(author, post.author_name || "anonymous");

    const content = document.createElement("p");
    content.className = "post-content";
    safeText(content, post.content);

    item.append(author, content);
    postList.appendChild(item);
  }
}

async function loadStats() {
  try {
    renderStats(await getJson("/api/stats"));
  } catch (_error) {
    renderStats({});
  }
}

async function loadTopics() {
  try {
    const topics = await getJson("/api/topics");
    renderTopics(topics);
    await loadPosts(activeTopicId);
  } catch (_error) {
    renderTopics([]);
  }
}

async function loadPosts(topicId) {
  activeTopicId = Number(topicId) || 1;
  try {
    renderPosts(await getJson(`/api/topics/${activeTopicId}/posts`));
  } catch (_error) {
    renderPosts([]);
  }
}

async function selectTopic(topicId) {
  activeTopicId = topicId;
  renderTopics(topicsCache);
  await loadPosts(topicId);
}

function bind(formId, handler) {
  document.getElementById(formId).addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      setStatus("正在请求 ATEE Core Service...");
      await handler(event.currentTarget);
      restoreStatus();
    } catch (error) {
      appendResult("请求失败", { ok: false, security: { message_zh: error.message } });
      setStatus(error.message);
    }
  });
}

bind("loginForm", async (form) => {
  const payload = await postJson("/api/login", formData(form));
  appendResult("登录链路", payload);
});

bind("topicForm", async (form) => {
  const payload = await postJson("/api/topics", formData(form));
  appendResult("发起话题", payload);
  if (payload.topic) {
    activeTopicId = payload.topic.id;
  }
  await loadStats();
  await loadTopics();
});

bind("commentForm", async (form) => {
  const body = formData(form);
  const topicId = Number(body.topic_id) || activeTopicId;
  const payload = await postJson(`/api/topics/${topicId}/posts`, { content: body.text });
  appendResult("发布发言", payload);
  activeTopicId = topicId;
  await loadStats();
  await loadTopics();
});

bind("uploadForm", async (form) => {
  const payload = await postJson("/api/upload", formData(form));
  appendResult("上传菜单", payload);
});

bind("appealForm", async (form) => {
  const payload = await postJson("/api/appeal", formData(form));
  appendResult("申诉复核", payload);
});

loadStats();
loadTopics();
