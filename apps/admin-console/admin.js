const byId = (id) => document.getElementById(id);
const safeText = (node, value) => {
  node.textContent = typeof value === "string" ? value : JSON.stringify(value, null, 2);
};
let lastStatus = null;

async function request(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options
  });
  const data = await res.json();
  return { status: res.status, data };
}

async function refresh() {
  const { data } = await request("/v1/runtime/status");
  lastStatus = data;
  safeText(byId("runtime"), data.display?.runtime_mode_zh || data.runtime_mode);
  safeText(byId("paused"), data.display?.agent_paused_zh || String(data.agent_paused));
  safeText(byId("ledger"), String(data.ledger.records));
  safeText(byId("appeals"), String(data.pending_appeals));
  byId("runtime").className = "value " + (data.runtime_mode === "auto" ? "good" : "warn");
  safeText(byId("statusText"), "Core Service 已连接");
  safeText(byId("output"), data);
}

async function setMode(mode) {
  const { data } = await request("/v1/admin/mode", { method: "POST", body: JSON.stringify({ mode }) });
  safeText(byId("result"), data);
  await refresh();
}

async function pauseResume() {
  const paused = !(lastStatus && lastStatus.agent_paused);
  const { data } = await request("/v1/admin/pause-agent", { method: "POST", body: JSON.stringify({ paused }) });
  safeText(byId("result"), data);
  await refresh();
}

async function testSafe() {
  const body = {
    method: "GET",
    path: "/posts/hello",
    headers: {},
    remote_addr: "198.51.100.8",
    body: { text: "这是一条普通中文浏览请求" }
  };
  const { data } = await request("/v1/check", { method: "POST", body: JSON.stringify(body) });
  safeText(byId("result"), data);
  await refresh();
}

async function testAttack() {
  const body = {
    method: "POST",
    path: "/comment",
    event_type: "comment_create",
    body: { text: "<script>alert(1)</script>" },
    remote_addr: "198.51.100.9"
  };
  const { data } = await request("/v1/check", { method: "POST", body: JSON.stringify(body) });
  safeText(byId("result"), data);
  await refresh();
}

async function testAppeal() {
  const body = { punishment_id: "demo-punishment", reason: "我认为这次封禁可能是误判，请管理员复核。" };
  const { data } = await request("/v1/appeal", { method: "POST", body: JSON.stringify(body) });
  safeText(byId("result"), data);
  await refresh();
}

async function breakGlass() {
  const { data } = await request("/v1/admin/break-glass/status", { method: "POST", body: "{}" });
  safeText(byId("result"), data);
}

async function showConfig() {
  const { data } = await request("/v1/admin/config");
  safeText(byId("result"), data);
}

async function loadOnboarding() {
  const { data } = await request("/v1/onboarding/steps");
  const list = byId("guideList");
  list.textContent = "";
  for (const step of data.steps || []) {
    const item = document.createElement("li");
    const title = document.createElement("strong");
    title.className = "guide-title";
    title.textContent = step.title_zh;
    const plain = document.createElement("span");
    plain.className = "guide-text";
    plain.textContent = step.plain_text_zh;
    const recommendation = document.createElement("span");
    recommendation.className = "guide-text";
    recommendation.textContent = `推荐：${step.recommended_default_zh}`;
    const risk = document.createElement("span");
    risk.className = "guide-text";
    risk.textContent = `风险：${step.risk_zh}`;
    item.append(title, plain, recommendation, risk);
    list.appendChild(item);
  }
}

byId("refreshBtn").addEventListener("click", refresh);
byId("observeBtn").addEventListener("click", () => setMode("observe"));
byId("autoBtn").addEventListener("click", () => setMode("auto"));
byId("pauseBtn").addEventListener("click", pauseResume);
byId("testSafeBtn").addEventListener("click", testSafe);
byId("testAttackBtn").addEventListener("click", testAttack);
byId("testAppealBtn").addEventListener("click", testAppeal);
byId("configBtn").addEventListener("click", showConfig);
byId("breakGlassBtn").addEventListener("click", breakGlass);
refresh().catch((error) => safeText(byId("statusText"), error.message));
loadOnboarding().catch((error) => safeText(byId("guideList"), error.message));
