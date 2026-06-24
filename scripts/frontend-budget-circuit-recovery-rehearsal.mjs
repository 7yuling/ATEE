import { chromium } from "playwright-core";
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import net from "node:net";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const args = parseArgs(process.argv.slice(2));
const durationSeconds = intArg(args, "duration-seconds", 7200);
const intervalSeconds = intArg(args, "interval-seconds", 60);
const budgetCents = nonNegativeIntArg(args, "budget-cents", 1000);
const corePort = optionalIntArg(args, "core-port") || 8787;
const demoPort = optionalIntArg(args, "demo-port") || 8790;
const adapterTimeoutSeconds = intArg(args, "adapter-timeout-seconds", 25);
const reportPath = path.resolve(root, args.report || "reports/frontend-budget-circuit-recovery-rehearsal.md");
const statusPath = path.resolve(root, args.status || "reports/frontend-budget-circuit-recovery-rehearsal.status.json");
const pythonExe = process.env.PYTHON || (existsSync("C:\\Python314\\python.exe") ? "C:\\Python314\\python.exe" : "python");
const chromePath = findChrome();

let core;
let demo;
let browser;
let page;
let originalConfig = {};
let originalRuntimeMode = "";
let originalProxyUrl = null;

const summary = {
  ok: false,
  mode: "frontend_budget_circuit_recovery",
  live_used: true,
  generated_at: new Date().toISOString(),
  duration_target_seconds: durationSeconds,
  interval_seconds: intervalSeconds,
  budget_cents: budgetCents,
  core_port: corePort,
  demo_port: demoPort,
  started_at: null,
  completed_at: null,
  elapsed_seconds: 0,
  stop_reason: null,
  cycles_completed: 0,
  frontend_submissions: 0,
  frontend_failures: 0,
  phase_counts: {},
  scenario_counts: {},
  route_counts: {},
  rule_counts: {},
  action_counts: {},
  llm_reason_counts: {},
  phase_results: [],
  issues: [],
  code_findings: [],
  samples: [],
  latency_ms: { values: [], min: 0, max: 0, avg: 0 },
  llm_budget: {},
  llm_circuit: {},
};

try {
  await mkdir(path.dirname(reportPath), { recursive: true });
  await mkdir(path.dirname(statusPath), { recursive: true });
  await ensurePortsFree();
  await writeStatus("starting_services");

  core = startProcess(pythonExe, ["services/core-service/run_server.py"], {
    ATEE_HOST: "127.0.0.1",
    ATEE_PORT: String(corePort),
  });
  await waitForHealth(`http://127.0.0.1:${corePort}/health`, "core");

  demo = startProcess(pythonExe, ["apps/demo-site/server.py"], {
    ATEE_DEMO_HOST: "127.0.0.1",
    ATEE_DEMO_PORT: String(demoPort),
    ATEE_CORE_URL: `http://127.0.0.1:${corePort}`,
    ATEE_ADAPTER_TIMEOUT_SECONDS: String(adapterTimeoutSeconds),
  });
  await waitForHealth(`http://127.0.0.1:${demoPort}/health`, "demo");

  await captureAndPrepareConfig();
  browser = await chromium.launch({ executablePath: chromePath, headless: true });
  page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  await page.goto(`http://127.0.0.1:${demoPort}/`, { waitUntil: "domcontentloaded" });
  await expectText(page, "Dining Hall Forum");

  summary.started_at = new Date().toISOString();
  await writeStatus("running");

  await baselinePhase();
  await circuitPhase();
  await recoveryPhase();
  await longRunPhase();

  summary.stop_reason ||= "duration_complete";
  summary.completed_at = new Date().toISOString();
  summary.elapsed_seconds = Math.round((Date.now() - Date.parse(summary.started_at)) / 1000);
  updateRuntimeSummary(await runtimeStatus());
  await inspectProblemCode();
  summary.ok = summary.frontend_failures === 0 && summary.phase_results.every((item) => item.ok);
  await writeStatus("completed");
  await writeReport();
  console.log(JSON.stringify(publicSummary(), null, 2));
  process.exitCode = summary.ok ? 0 : 1;
} catch (error) {
  summary.stop_reason = "exception";
  summary.completed_at = new Date().toISOString();
  summary.issues.push({ title: "rehearsal_exception", detail: String(error?.message || error).slice(0, 500), risk: "high" });
  await writeStatus("failed").catch(() => {});
  await writeReport().catch(() => {});
  console.error(JSON.stringify(publicSummary(), null, 2));
  process.exitCode = 1;
} finally {
  await restoreConfig().catch(() => {});
  if (browser) await browser.close().catch(() => {});
  if (demo) demo.kill();
  if (core) core.kill();
}

async function captureAndPrepareConfig() {
  const runtime = await runtimeStatus();
  originalConfig = runtime.config || {};
  originalRuntimeMode = originalConfig.runtime_mode || "";
  originalProxyUrl = originalConfig.llm_proxy_configured ? "configured" : null;
  const configPayload = {
    runtime_mode: "auto",
    agent_paused: false,
    async_review_worker_enabled: true,
    llm_daily_budget_cents: budgetCents,
  };
  if (originalConfig.llm_proxy_configured) {
    const raw = await readLocalConfig();
    originalProxyUrl = raw.llm_proxy_url || null;
    configPayload.llm_proxy_url = originalProxyUrl;
  }
  await updateConfig(configPayload);
  const updated = await runtimeStatus();
  if (updated.llm_gateway?.mode !== "openai_compatible" && updated.llm_gateway?.mode !== "remote") {
    throw new Error(`live llm mode is not enabled: ${updated.llm_gateway?.mode}`);
  }
  if (!updated.llm_gateway?.api_key_configured || !updated.llm_gateway?.api_base_configured) {
    throw new Error("live llm api base/key is not configured");
  }
  updateRuntimeSummary(updated);
}

async function baselinePhase() {
  const before = await runtimeStatus();
  const result = await submitScenario("budget_10yuan", "normal_login", async () => submitLogin("budget-baseline", "ok-password"));
  const after = await runtimeStatus();
  const ok = result.route === "sync_agent" && result.llm_reason === "provider_json_decision" && Number(after.llm_gateway?.budget?.daily_budget_cents) === budgetCents;
  recordPhase("10元预算正常调用", ok, {
    before_budget: before.llm_gateway?.budget,
    after_budget: after.llm_gateway?.budget,
    sample: result,
  });
}

async function circuitPhase() {
  await updateConfig({ llm_proxy_url: "http://127.0.0.1:1", llm_daily_budget_cents: budgetCents, runtime_mode: "auto" });
  const attempts = [];
  for (let index = 1; index <= 4; index += 1) {
    attempts.push(await submitScenario("circuit_breaker", `fault_login_${index}`, async () => submitLogin(`fault-${index}`, "bad-proxy")));
  }
  const runtime = await runtimeStatus();
  const reasons = attempts.map((item) => item.llm_reason);
  const ok = reasons.slice(0, 3).every((reason) => reason === "provider_request_failed") && reasons[3] === "llm_circuit_open" && runtime.llm_gateway?.circuit?.open;
  recordPhase("切坏 provider 触发熔断", ok, {
    reasons,
    circuit: runtime.llm_gateway?.circuit,
    budget: runtime.llm_gateway?.budget,
  });
}

async function recoveryPhase() {
  await updateConfig({ llm_proxy_url: originalProxyUrl, llm_daily_budget_cents: budgetCents, runtime_mode: "auto" });
  const runtimeAfterConfig = await runtimeStatus();
  const recovery = await submitScenario("recovery_10yuan", "recovery_login", async () => submitLogin("recovery", "ok-password"));
  const runtimeAfterLogin = await runtimeStatus();
  const ok = recovery.route === "sync_agent" && recovery.llm_reason === "provider_json_decision" && runtimeAfterLogin.llm_gateway?.circuit?.open === false;
  recordPhase("恢复 provider 并恢复 10元预算", ok, {
    budget_after_config_update: runtimeAfterConfig.llm_gateway?.budget,
    circuit_after_config_update: runtimeAfterConfig.llm_gateway?.circuit,
    recovery_sample: recovery,
    budget_after_recovery_login: runtimeAfterLogin.llm_gateway?.budget,
  });
  if (Number(runtimeAfterConfig.llm_gateway?.budget?.daily_spend_cents || 0) === 0) {
    summary.code_findings.push({
      title: "配置更新会清零模型预算计数",
      file: "services/core-service/atee_core/core.py",
      risk: "high",
      evidence: "恢复 llm_proxy_url/llm_daily_budget_cents 后，RemoteLLMGateway 被重建，daily_spend_cents 回到 0。",
    });
  }
  if (runtimeAfterConfig.llm_gateway?.circuit?.open === false) {
    summary.code_findings.push({
      title: "配置更新会立即清除熔断窗口",
      file: "services/core-service/atee_core/core.py",
      risk: "medium",
      evidence: "熔断打开后更新 llm_proxy_url，RemoteLLMGateway 被重建，circuit_opened_until 回到 0。",
    });
  }
}

async function longRunPhase() {
  const deadlineMs = Date.parse(summary.started_at) + durationSeconds * 1000;
  while (Date.now() < deadlineMs) {
    const cycle = summary.cycles_completed + 1;
    const cycleStarted = Date.now();
    await submitScenario("post_recovery_long_run", "normal_login", async () => submitLogin(`long-${cycle}`, "ok-password"));
    await submitScenario("post_recovery_long_run", "normal_comment", async () => submitComment(`post recovery comment ${cycle}`));
    await submitScenario("post_recovery_long_run", "normal_upload", async () => submitUpload(`recovery-${cycle}.txt`, "normal file"));
    if (cycle % 5 === 0) {
      await submitScenario("post_recovery_long_run", "attack_sqli_login", async () => submitLogin("' OR 1=1 --", "attack"));
    }
    summary.cycles_completed = cycle;
    const runtime = await runtimeStatus();
    updateRuntimeSummary(runtime);
    await writeStatus("running");
    const sleepMs = Math.max(0, intervalSeconds * 1000 - (Date.now() - cycleStarted));
    await delay(Math.min(sleepMs, Math.max(0, deadlineMs - Date.now())));
  }
  const runtime = await runtimeStatus();
  const ok = summary.frontend_failures === 0 && runtime.llm_gateway?.circuit?.open === false;
  recordPhase("恢复后长时前台运行", ok, {
    cycles_completed: summary.cycles_completed,
    frontend_failures: summary.frontend_failures,
    budget: runtime.llm_gateway?.budget,
    circuit: runtime.llm_gateway?.circuit,
  });
}

async function submitLogin(username, password) {
  await page.locator('#loginForm input[name="username"]').fill(String(username));
  await page.locator('#loginForm input[name="password"]').fill(String(password));
  return submitAndRead("/api/login", "#loginForm button");
}

async function submitComment(text) {
  await page.locator('#commentForm textarea[name="text"]').fill(String(text));
  return submitAndRead("/posts", "#commentForm button");
}

async function submitUpload(filename, text) {
  await page.locator('#uploadForm input[name="filename"]').fill(String(filename));
  await page.locator('#uploadForm textarea[name="text"]').fill(String(text));
  return submitAndRead("/api/upload", "#uploadForm button");
}

async function submitScenario(phase, name, submitter) {
  summary.phase_counts[phase] = (summary.phase_counts[phase] || 0) + 1;
  summary.scenario_counts[name] = (summary.scenario_counts[name] || 0) + 1;
  const payload = await submitter();
  summary.frontend_submissions += 1;
  const sample = recordPayload(phase, name, payload);
  if (name.startsWith("normal_") || name === "budget_10yuan" || name === "recovery_login") {
    if (payload._response_status !== 200 || !payload.ok) {
      summary.frontend_failures += 1;
      summary.issues.push({ title: `${name}_frontend_failed`, detail: `status=${payload._response_status}; ok=${payload.ok}; error=${payload.error || "-"}`, risk: "high" });
    }
  }
  return sample;
}

async function submitAndRead(endpoint, buttonSelector) {
  const before = await page.locator("#resultList article").count();
  const responsePromise = page.waitForResponse(
    (response) => response.url().includes(endpoint) && response.request().method() === "POST",
    { timeout: 45000 },
  );
  await page.locator(buttonSelector).click();
  const response = await responsePromise;
  const payload = await response.json();
  payload._response_status = response.status();
  await page.waitForFunction((count) => document.querySelectorAll("#resultList article").length > count, before, { timeout: 10000 });
  return payload;
}

function recordPayload(phase, name, payload) {
  const core = payload.core_response || {};
  const route = core.route?.route || payload.security?.route || "unknown";
  const rule = core.fast_path?.rule_id || "-";
  const action = core.tool_gateway?.effective_action || payload.security?.effective_action || "-";
  const llmReason = core.llm_gateway?.reason || "-";
  const latency = Number(core.llm_gateway?.latency_ms || core.llm_gateway?.provider_latency_ms || 0);
  const sample = { phase, scenario: name, status: payload._response_status, route, rule, action, llm_reason: llmReason, ok: Boolean(payload.ok) };
  summary.route_counts[route] = (summary.route_counts[route] || 0) + 1;
  summary.rule_counts[rule] = (summary.rule_counts[rule] || 0) + 1;
  summary.action_counts[action] = (summary.action_counts[action] || 0) + 1;
  summary.llm_reason_counts[llmReason] = (summary.llm_reason_counts[llmReason] || 0) + 1;
  if (latency > 0) {
    summary.latency_ms.values.push(latency);
    updateLatency();
  }
  if (summary.samples.length < 30) summary.samples.push(sample);
  return sample;
}

function recordPhase(name, ok, details) {
  summary.phase_results.push({ name, ok: Boolean(ok), details });
  if (!ok) summary.issues.push({ title: `${name}_failed`, detail: JSON.stringify(details).slice(0, 500), risk: "high" });
}

async function updateConfig(payload) {
  const result = await postJson(`http://127.0.0.1:${corePort}/v1/admin/config`, payload);
  if (!result?.ok) throw new Error(`config update failed: ${result?.reason || result?.error || "unknown"}`);
  return result;
}

async function restoreConfig() {
  if (!originalConfig || !Object.keys(originalConfig).length) return;
  const payload = {
    runtime_mode: originalRuntimeMode || originalConfig.runtime_mode || "observe",
    llm_daily_budget_cents: Number(originalConfig.llm_daily_budget_cents ?? budgetCents),
  };
  if (originalProxyUrl !== "configured") payload.llm_proxy_url = originalProxyUrl;
  await updateConfig(payload).catch(() => {});
}

async function inspectProblemCode() {
  summary.code_findings.push({
    title: "预算和熔断状态保存在 RemoteLLMGateway 内存字段中",
    file: "services/core-service/atee_core/llm_gateway.py",
    risk: "high",
    evidence: "daily_spend_cents/circuit_opened_until 在 __init__ 中初始化，未持久化到 config 或 ledger。",
  });
  summary.code_findings.push({
    title: "任意配置变更会重建 RemoteLLMGateway",
    file: "services/core-service/atee_core/core.py",
    risk: "high",
    evidence: "CoreService.update_config 在 changed 后执行 self.llm_gateway = RemoteLLMGateway(...)，会重置预算和熔断状态。",
  });
}

function updateRuntimeSummary(runtime) {
  if (!runtime) return;
  summary.async_review = runtime.async_review || {};
  summary.ledger = runtime.ledger || {};
  summary.actions_executed = runtime.actions_executed;
  summary.llm_budget = runtime.llm_gateway?.budget || {};
  summary.llm_circuit = runtime.llm_gateway?.circuit || {};
  summary.llm_gateway = {
    mode: runtime.llm_gateway?.mode,
    provider: runtime.llm_gateway?.provider,
    model: runtime.llm_gateway?.model,
    calls: runtime.llm_gateway?.calls,
    failures: runtime.llm_gateway?.failures,
    last_ok: runtime.llm_gateway?.last_ok,
    api_key_configured: runtime.llm_gateway?.api_key_configured,
    api_base_configured: runtime.llm_gateway?.api_base_configured,
    proxy_configured: runtime.llm_gateway?.proxy_configured,
    raw_prompt_storage: runtime.llm_gateway?.raw_prompt_storage,
  };
}

function updateLatency() {
  const values = summary.latency_ms.values;
  summary.latency_ms.min = Math.min(...values);
  summary.latency_ms.max = Math.max(...values);
  summary.latency_ms.avg = Math.round((values.reduce((total, value) => total + value, 0) / values.length) * 100) / 100;
}

async function runtimeStatus() {
  return fetchJson(`http://127.0.0.1:${corePort}/v1/runtime/status`);
}

async function fetchJson(url) {
  const response = await fetch(url);
  return response.json();
}

async function postJson(url, payload) {
  const response = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(`POST ${new URL(url).pathname} failed with status=${response.status}: ${data?.reason || data?.error || "unknown"}`);
  return data;
}

async function readLocalConfig() {
  const fs = await import("node:fs/promises");
  return JSON.parse(await fs.readFile(path.join(root, "config", "config.json"), "utf8"));
}

async function ensurePortsFree() {
  for (const port of [corePort, demoPort]) {
    if (await isPortOpen(port)) throw new Error(`port ${port} is already in use`);
  }
}

async function isPortOpen(port) {
  return new Promise((resolve) => {
    const socket = net.createConnection({ host: "127.0.0.1", port });
    socket.once("connect", () => { socket.destroy(); resolve(true); });
    socket.once("error", () => resolve(false));
    socket.setTimeout(1000, () => { socket.destroy(); resolve(false); });
  });
}

async function waitForHealth(url, label) {
  const deadline = Date.now() + 30000;
  let lastError = "";
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
      lastError = `HTTP ${response.status}`;
    } catch (error) {
      lastError = error.message;
    }
    await delay(250);
  }
  throw new Error(`${label} did not become healthy: ${lastError}`);
}

async function expectText(targetPage, text) {
  const content = await targetPage.locator("body").textContent({ timeout: 15000 });
  if (!String(content || "").includes(text)) throw new Error(`page did not contain text: ${text}`);
}

function startProcess(command, commandArgs, extraEnv) {
  const child = spawn(command, commandArgs, { cwd: root, env: { ...process.env, ...extraEnv }, stdio: ["ignore", "ignore", "pipe"] });
  let stderr = "";
  child.stderr.on("data", (chunk) => { stderr = `${stderr}${String(chunk)}`.slice(-2000); });
  child.on("exit", (code) => {
    if (code && summary.stop_reason === null) summary.issues.push({ title: `${commandArgs[0]}_exited`, detail: `exit_code=${code}; stderr=${stderr}`, risk: "high" });
  });
  return child;
}

async function writeStatus(state) {
  if (summary.started_at) summary.elapsed_seconds = Math.round((Date.now() - Date.parse(summary.started_at)) / 1000);
  await writeFile(statusPath, JSON.stringify({ state, ...publicSummary() }, null, 2), "utf8");
}

async function writeReport() {
  await writeFile(reportPath, markdownReport(), "utf8");
}

function publicSummary() {
  const { values, ...latency } = summary.latency_ms;
  return {
    ...summary,
    latency_ms: latency,
    report_path: reportPath,
    status_path: statusPath,
    core_url: `http://127.0.0.1:${corePort}`,
    demo_url: `http://127.0.0.1:${demoPort}`,
  };
}

function markdownReport() {
  const data = publicSummary();
  const lines = [
    "# ATEE Frontend Budget-Circuit-Recovery Rehearsal",
    "",
    `- Generated at UTC: ${new Date().toISOString()}`,
    `- Overall OK: ${data.ok}`,
    `- Elapsed seconds: ${data.elapsed_seconds}`,
    `- Stop reason: ${data.stop_reason}`,
    `- Frontend submissions: ${data.frontend_submissions}`,
    `- Frontend failures: ${data.frontend_failures}`,
    `- Budget cents: ${data.budget_cents}`,
    `- Budget spend cents: ${data.llm_budget?.daily_spend_cents}`,
    `- Budget remaining cents: ${data.llm_budget?.daily_remaining_cents}`,
    `- LLM calls: ${data.llm_gateway?.calls}`,
    `- LLM failures: ${data.llm_gateway?.failures}`,
    `- LLM circuit open: ${data.llm_circuit?.open}`,
    `- Latency avg ms: ${data.latency_ms?.avg}`,
    "",
    "## Phase Results",
    "",
    "| Phase | OK | Details |",
    "|---|---|---|",
    ...data.phase_results.map((item) => `| ${item.name} | ${item.ok} | ${JSON.stringify(item.details).replaceAll("|", "/").slice(0, 500)} |`),
    "",
    "## Counts",
    "",
    "| Item | Value |",
    "|---|---:|",
    ...countLines("phase", data.phase_counts),
    ...countLines("scenario", data.scenario_counts),
    ...countLines("route", data.route_counts),
    ...countLines("rule", data.rule_counts),
    ...countLines("action", data.action_counts),
    ...countLines("llm_reason", data.llm_reason_counts),
    "",
    "## Problem Code Findings",
    "",
    "| Finding | File | Risk | Evidence |",
    "|---|---|---|---|",
    ...data.code_findings.map((item) => `| ${item.title} | ${item.file} | ${item.risk} | ${item.evidence} |`),
    "",
    "## Issues",
    "",
  ];
  if (!data.issues.length) lines.push("No frontend failure was found.");
  for (const issue of data.issues) lines.push(`- [${issue.risk}] ${issue.title}: ${issue.detail}`);
  lines.push("", "## Security Notes", "", "- API keys, key file paths, proxy URLs, API base URLs, auth headers, raw prompts, and raw request bodies are intentionally omitted.");
  return `${lines.join("\n")}\n`;
}

function countLines(prefix, counts) {
  return Object.entries(counts || {}).sort(([a], [b]) => a.localeCompare(b)).map(([key, value]) => `| ${prefix}:${key} | ${value} |`);
}

function findChrome() {
  const candidates = [process.env.CHROME_PATH, "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe", "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe", "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe", "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe"].filter(Boolean);
  for (const candidate of candidates) if (existsSync(candidate)) return path.resolve(candidate);
  throw new Error("Chrome or Edge executable was not found.");
}

function parseArgs(argv) {
  const result = {};
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (!arg.startsWith("--")) continue;
    const key = arg.slice(2);
    result[key] = argv[index + 1];
    index += 1;
  }
  return result;
}

function intArg(source, key, fallback) {
  const value = Number.parseInt(source[key] ?? "", 10);
  return Number.isFinite(value) && value > 0 ? value : fallback;
}

function nonNegativeIntArg(source, key, fallback) {
  const value = Number.parseInt(source[key] ?? "", 10);
  return Number.isFinite(value) && value >= 0 ? value : fallback;
}

function optionalIntArg(source, key) {
  const value = Number.parseInt(source[key] ?? "", 10);
  return Number.isFinite(value) && value > 0 ? value : null;
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
