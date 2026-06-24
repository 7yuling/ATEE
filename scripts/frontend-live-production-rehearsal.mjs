import { chromium } from "playwright-core";
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import net from "node:net";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const args = parseArgs(process.argv.slice(2));
const durationSeconds = intArg(args, "duration-seconds", 3600);
const intervalSeconds = intArg(args, "interval-seconds", 60);
const budgetCents = nonNegativeIntArg(args, "budget-cents", 1000);
const stopBudgetRemainingCents = nonNegativeIntArg(args, "stop-budget-remaining-cents", 25);
const requestedCorePort = optionalIntArg(args, "core-port");
const requestedDemoPort = optionalIntArg(args, "demo-port");
const useExistingCore = Boolean(args["use-existing-core"]);
const adapterTimeoutSeconds = intArg(args, "adapter-timeout-seconds", 25);
const adminToken = stringArg(args, "admin-token", process.env.ATEE_ADMIN_TOKEN || "");
const reportPath = path.resolve(root, args.report || "reports/frontend-live-production-rehearsal.md");
const statusPath = path.resolve(root, args.status || "reports/frontend-live-production-rehearsal.status.json");
const pythonExe = process.env.PYTHON || (existsSync("C:\\Python314\\python.exe") ? "C:\\Python314\\python.exe" : "python");
const chromePath = findChrome();

let core;
let demo;
let browser;
let page;

const summary = {
  ok: false,
  mode: "live_frontend_production_rehearsal",
  live_used: true,
  generated_at: new Date().toISOString(),
  duration_target_seconds: durationSeconds,
  interval_seconds: intervalSeconds,
  budget_cents: budgetCents,
  stop_budget_remaining_cents: stopBudgetRemainingCents,
  core_port: null,
  demo_port: null,
  browser_visible: !args.headless,
  started_at: null,
  completed_at: null,
  elapsed_seconds: 0,
  stop_reason: null,
  cycles_completed: 0,
  frontend_submissions: 0,
  frontend_failures: 0,
  scenario_counts: {},
  route_counts: {},
  rule_counts: {},
  action_counts: {},
  llm_reason_counts: {},
  admin_ai_checks: [],
  async_review: {},
  llm_budget: {},
  llm_circuit: {},
  latency_ms: { values: [], min: 0, max: 0, avg: 0 },
  issues: [],
  samples: [],
};

try {
  await mkdir(path.dirname(reportPath), { recursive: true });
  await mkdir(path.dirname(statusPath), { recursive: true });
  const corePort = requestedCorePort || await freePort();
  const demoPort = requestedDemoPort || await freePort();
  summary.core_port = corePort;
  summary.demo_port = demoPort;
  await writeStatus("starting_services");

  if (!useExistingCore) {
    core = startProcess(pythonExe, ["services/core-service/run_server.py"], {
      ATEE_HOST: "127.0.0.1",
      ATEE_PORT: String(corePort),
    });
  }
  await waitForHealth(`http://127.0.0.1:${corePort}/health`, "core");
  await applyRuntimeBudget(corePort);

  demo = startProcess(pythonExe, ["apps/demo-site/server.py"], {
    ATEE_DEMO_HOST: "127.0.0.1",
    ATEE_DEMO_PORT: String(demoPort),
    ATEE_CORE_URL: `http://127.0.0.1:${corePort}`,
    ATEE_ADAPTER_TIMEOUT_SECONDS: String(adapterTimeoutSeconds),
  });
  await waitForHealth(`http://127.0.0.1:${demoPort}/health`, "demo");

  await assertRuntimeConfig(corePort);
  await verifyAdminAiFunctions(corePort);

  browser = await chromium.launch({
    executablePath: chromePath,
    headless: Boolean(args.headless),
    slowMo: args.headless ? 0 : 80,
  });
  page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  await page.goto(`http://127.0.0.1:${demoPort}/`, { waitUntil: "domcontentloaded" });
  await expectText(page, "Dining Hall Forum");
  await expectSelector(page, "#loginForm");
  await expectSelector(page, "#topicForm");
  await expectSelector(page, "#commentForm");
  await expectSelector(page, "#uploadForm");

  summary.started_at = new Date().toISOString();
  await writeStatus("running");
  const startedMs = Date.now();
  const deadlineMs = startedMs + durationSeconds * 1000;
  let cycle = 0;

  while (Date.now() < deadlineMs) {
    cycle += 1;
    const cycleStarted = Date.now();
    await runCycle(cycle, corePort);
    summary.cycles_completed = cycle;

    const runtime = await runtimeStatus(corePort);
    updateRuntimeSummary(runtime);
    await writeStatus("running");

    const remaining = runtime?.llm_gateway?.budget?.daily_remaining_cents;
    if (remaining !== null && remaining !== undefined && Number(remaining) <= stopBudgetRemainingCents) {
      summary.stop_reason = "budget_guard";
      break;
    }
    if (runtime?.llm_gateway?.circuit?.open) {
      summary.stop_reason = "llm_circuit_open";
      break;
    }

    const sleepMs = Math.max(0, intervalSeconds * 1000 - (Date.now() - cycleStarted));
    await delay(Math.min(sleepMs, Math.max(0, deadlineMs - Date.now())));
  }

  summary.stop_reason ||= "duration_complete";
  summary.completed_at = new Date().toISOString();
  summary.elapsed_seconds = Math.round((Date.now() - Date.parse(summary.started_at)) / 1000);
  const finalRuntime = await runtimeStatus(corePort);
  updateRuntimeSummary(finalRuntime);
  summary.ok = summary.frontend_failures === 0 && adminAiChecksOk() && summary.stop_reason !== "llm_circuit_open";
  await writeStatus("completed");
  await writeReport();
  console.log(JSON.stringify(publicSummary(), null, 2));
  process.exitCode = summary.ok ? 0 : 1;
} catch (error) {
  summary.stop_reason = "exception";
  summary.completed_at = new Date().toISOString();
  summary.issues.push({
    title: "frontend_live_rehearsal_exception",
    detail: String(error?.message || error).slice(0, 500),
    risk: "high",
  });
  await writeStatus("failed").catch(() => {});
  await writeReport().catch(() => {});
  console.error(JSON.stringify(publicSummary(), null, 2));
  process.exitCode = 1;
} finally {
  if (browser) {
    await browser.close().catch(() => {});
  }
  if (demo) {
    demo.kill();
  }
  if (core) {
    core.kill();
  }
}

async function assertRuntimeConfig(corePort) {
  const runtime = await runtimeStatus(corePort);
  const gateway = runtime.llm_gateway || {};
  const config = runtime.config || {};
  if (gateway.mode !== "openai_compatible" && gateway.mode !== "remote") {
    throw new Error(`live llm mode is not enabled: ${gateway.mode}`);
  }
  if (!gateway.api_key_configured || !gateway.api_base_configured) {
    throw new Error("live llm api base/key is not configured");
  }
  if (Number(gateway.budget?.daily_budget_cents ?? 0) !== budgetCents) {
    throw new Error(`runtime budget mismatch: ${gateway.budget?.daily_budget_cents}`);
  }
  if (config.agent_paused) {
    throw new Error("agent is paused");
  }
  if (!config.async_review_worker_enabled) {
    throw new Error("async review worker is disabled");
  }
  updateRuntimeSummary(runtime);
}

async function applyRuntimeBudget(corePort) {
  const runtime = await runtimeStatus(corePort);
  const currentBudget = Number(runtime?.llm_gateway?.budget?.daily_budget_cents ?? 0);
  if (currentBudget === budgetCents) {
    updateRuntimeSummary(runtime);
    return;
  }
  const result = await postJson(
    `http://127.0.0.1:${corePort}/v1/admin/config`,
    { llm_daily_budget_cents: budgetCents },
    adminHeaders(),
  );
  if (!result?.ok) {
    throw new Error(`failed to update runtime budget to ${budgetCents}: ${result?.reason || result?.error || "unknown"}`);
  }
  const updated = await runtimeStatus(corePort);
  const updatedBudget = Number(updated?.llm_gateway?.budget?.daily_budget_cents ?? 0);
  if (updatedBudget !== budgetCents) {
    throw new Error(`runtime budget mismatch after update: ${updatedBudget}`);
  }
  updateRuntimeSummary(updated);
}

async function runCycle(cycle, corePort) {
  await submitScenario("normal_login", async () => {
    await page.locator('#loginForm input[name="username"]').fill(`prod-user-${cycle}`);
    await page.locator('#loginForm input[name="password"]').fill(`correct-horse-${cycle}`);
    return submitAndRead("/api/login", "#loginForm button");
  });

  await submitScenario("normal_topic", async () => {
    await page.locator('#topicForm input[name="title"]').fill(`Production topic ${cycle}`);
    await page.locator('#topicForm textarea[name="description"]').fill(`Normal production topic ${cycle}: live AI rehearsal.`);
    return submitAndRead("/api/topics", "#topicForm button");
  });

  await submitScenario("normal_comment", async () => {
    await page.locator('#commentForm textarea[name="text"]').fill(`Normal production comment ${cycle}: zh-CN English emoji ok.`);
    return submitAndRead("/posts", "#commentForm button");
  });

  await submitScenario("normal_upload", async () => {
    await page.locator('#uploadForm input[name="filename"]').fill(`quarterly-report-${cycle}.txt`);
    await page.locator('#uploadForm textarea[name="text"]').fill("Business document summary without sensitive data.");
    return submitAndRead("/api/upload", "#uploadForm button");
  });

  if (cycle % 5 === 0) {
    await submitAttack(cycle);
  }

  if (cycle % 10 === 0) {
    await fetchJson(`http://127.0.0.1:${corePort}/v1/admin/async-reviews?status=all&limit=20`).catch(() => null);
  }
}

async function submitAttack(cycle) {
  const selector = cycle % 20 === 0 ? "xss_comment" : cycle % 15 === 0 ? "webshell_upload" : "sqli_login";
  if (selector === "xss_comment") {
    await submitScenario("attack_xss_comment", async () => {
      await page.locator('#commentForm textarea[name="text"]').fill("<script>alert(1)</script>");
      return submitAndRead("/posts", "#commentForm button");
    });
    return;
  }
  if (selector === "webshell_upload") {
    await submitScenario("attack_webshell_upload", async () => {
      await page.locator('#uploadForm input[name="filename"]').fill("shell.php");
      await page.locator('#uploadForm textarea[name="text"]').fill('eval(Request.Item["pass"])');
      return submitAndRead("/api/upload", "#uploadForm button");
    });
    return;
  }
  await submitScenario("attack_sqli_login", async () => {
    await page.locator('#loginForm input[name="username"]').fill("' OR 1=1 --");
    await page.locator('#loginForm input[name="password"]').fill("bad-password");
    return submitAndRead("/api/login", "#loginForm button");
  });
}

async function submitScenario(name, submitter) {
  summary.scenario_counts[name] = (summary.scenario_counts[name] || 0) + 1;
  try {
    const payload = await submitter();
    summary.frontend_submissions += 1;
    recordPayload(name, payload);
    const expectation = scenarioExpectation(name, payload);
    if (!expectation.ok) {
      summary.frontend_failures += 1;
      summary.issues.push({
        title: `${name}_unexpected_result`,
        detail: expectation.reason,
        risk: name.startsWith("normal_") ? "high" : "medium",
      });
    }
  } catch (error) {
    summary.frontend_failures += 1;
    summary.issues.push({
      title: `${name}_failed`,
      detail: String(error?.message || error).slice(0, 500),
      risk: "medium",
    });
  }
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
  await page.waitForFunction((count) => document.querySelectorAll("#resultList article").length > count, before, {
    timeout: 10000,
  });
  return payload;
}

function scenarioExpectation(name, payload) {
  const core = payload.core_response || {};
  const route = core.route?.route || payload.security?.route || "";
  const llmReason = core.llm_gateway?.reason || "";
  const rule = core.fast_path?.rule_id || "";
  const status = payload._response_status;
  if (name === "normal_login") {
    if (status !== 200 || !payload.ok || route !== "sync_agent" || llmReason !== "provider_json_decision") {
      return {
        ok: false,
        reason: `expected successful sync live login, got status=${status}; ok=${payload.ok}; route=${route || "-"}; llm_reason=${llmReason || "-"}; error=${payload.error || "-"}`,
      };
    }
  } else if (name === "normal_topic" || name === "normal_comment" || name === "normal_upload") {
    if (status !== 200 || !payload.ok || route !== "async_agent") {
      return {
        ok: false,
        reason: `expected accepted async frontend event, got status=${status}; ok=${payload.ok}; route=${route || "-"}; error=${payload.error || "-"}`,
      };
    }
  } else if (name.startsWith("attack_")) {
    if (status !== 200 || payload.ok || route !== "fast_path_block" || !rule) {
      return {
        ok: false,
        reason: `expected held fast-path attack, got status=${status}; ok=${payload.ok}; route=${route || "-"}; rule=${rule || "-"}; error=${payload.error || "-"}`,
      };
    }
  }
  return { ok: true, reason: "expected" };
}

async function verifyAdminAiFunctions(corePort) {
  const checks = [
    aiCheck(
      "admin_llm_test_get",
      await fetchJson(`http://127.0.0.1:${corePort}/v1/admin/llm/test`, adminHeaders()),
      "provider_json_decision",
    ),
    aiCheck(
      "admin_llm_test_post",
      await postJson(`http://127.0.0.1:${corePort}/v1/admin/llm/test`, {}, adminHeaders()),
      "provider_json_decision",
    ),
    aiCheck(
      "admin_agent_chat",
      await postJson(
        `http://127.0.0.1:${corePort}/v1/admin/agent/chat`,
        {
          message: "Confirm ATEE live AI connectivity in one short sentence.",
          site_type: "Dining Hall Forum",
          adapter_type: "HTTP API",
        },
        adminHeaders(),
      ),
      "provider_chat",
    ),
  ];
  summary.admin_ai_checks = checks;
  for (const check of checks) {
    if (!check.ok) {
      summary.issues.push({
        title: `${check.name}_unexpected_result`,
        detail: `expected reason=${check.expected_reason}; got ok=${check.ok}; reason=${check.reason || "-"}`,
        risk: "high",
      });
    }
  }
}

function aiCheck(name, payload, expectedReason) {
  const reason = payload?.reason || "";
  const reply = typeof payload?.reply_zh === "string" ? payload.reply_zh : "";
  return {
    name,
    ok: Boolean(payload?.ok) && reason === expectedReason,
    reason,
    expected_reason: expectedReason,
    latency_ms: payload?.latency_ms || payload?.provider_latency_ms || 0,
    raw_reply_omitted: Boolean(reply) || undefined,
  };
}

function adminAiChecksOk() {
  return summary.admin_ai_checks.length > 0 && summary.admin_ai_checks.every((check) => check.ok);
}

function recordPayload(name, payload) {
  const core = payload.core_response || {};
  const route = core.route?.route || payload.security?.route || "unknown";
  const rule = core.fast_path?.rule_id || "-";
  const action = core.tool_gateway?.effective_action || payload.security?.effective_action || "-";
  const llmReason = core.llm_gateway?.reason || "-";
  const latency = Number(core.llm_gateway?.latency_ms || core.llm_gateway?.provider_latency_ms || 0);

  summary.route_counts[route] = (summary.route_counts[route] || 0) + 1;
  summary.rule_counts[rule] = (summary.rule_counts[rule] || 0) + 1;
  summary.action_counts[action] = (summary.action_counts[action] || 0) + 1;
  summary.llm_reason_counts[llmReason] = (summary.llm_reason_counts[llmReason] || 0) + 1;
  if (latency > 0) {
    summary.latency_ms.values.push(latency);
    updateLatency();
  }
  if (summary.samples.length < 20) {
    summary.samples.push({
      scenario: name,
      route,
      rule,
      action,
      llm_reason: llmReason,
      executed: Boolean(core.action_result?.executed || payload.security?.executed),
      ok: Boolean(payload.ok),
    });
  }
}

function updateRuntimeSummary(runtime) {
  if (!runtime) {
    return;
  }
  summary.async_review = runtime.async_review || {};
  summary.async_review_worker = runtime.async_review_worker || {};
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

async function runtimeStatus(corePort) {
  return fetchJson(`http://127.0.0.1:${corePort}/v1/runtime/status`);
}

async function fetchJson(url, headers = {}) {
  const response = await fetch(url, { headers });
  return response.json();
}

async function postJson(url, payload, headers = {}) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: JSON.stringify(payload),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(`POST ${new URL(url).pathname} failed with status=${response.status}: ${data?.reason || data?.error || "unknown"}`);
  }
  return data;
}

function adminHeaders() {
  if (!adminToken) {
    return {};
  }
  return { Authorization: `Bearer ${adminToken}` };
}

async function writeStatus(state) {
  if (summary.started_at) {
    summary.elapsed_seconds = Math.round((Date.now() - Date.parse(summary.started_at)) / 1000);
  }
  await writeFile(statusPath, JSON.stringify({ state, ...publicSummary() }, null, 2), "utf8");
}

async function writeReport() {
  await writeFile(reportPath, markdownReport(), "utf8");
}

function publicSummary() {
  const { values, ...latency } = summary.latency_ms;
  return {
    ok: summary.ok,
    mode: summary.mode,
    live_used: summary.live_used,
    browser_visible: summary.browser_visible,
    generated_at: summary.generated_at,
    started_at: summary.started_at,
    completed_at: summary.completed_at,
    elapsed_seconds: summary.elapsed_seconds,
    duration_target_seconds: summary.duration_target_seconds,
    interval_seconds: summary.interval_seconds,
    budget_cents: summary.budget_cents,
    stop_reason: summary.stop_reason,
    cycles_completed: summary.cycles_completed,
    frontend_submissions: summary.frontend_submissions,
    frontend_failures: summary.frontend_failures,
    scenario_counts: summary.scenario_counts,
    route_counts: summary.route_counts,
    rule_counts: summary.rule_counts,
    action_counts: summary.action_counts,
    llm_reason_counts: summary.llm_reason_counts,
    admin_ai_checks: summary.admin_ai_checks,
    latency_ms: latency,
    llm_budget: summary.llm_budget,
    llm_circuit: summary.llm_circuit,
    llm_gateway: summary.llm_gateway,
    async_review: summary.async_review,
    async_review_worker: summary.async_review_worker,
    ledger: summary.ledger,
    actions_executed: summary.actions_executed,
    issues: summary.issues,
    samples: summary.samples,
    report_path: reportPath,
    status_path: statusPath,
    core_url: `http://127.0.0.1:${summary.core_port}`,
    demo_url: `http://127.0.0.1:${summary.demo_port}`,
  };
}

function markdownReport() {
  const data = publicSummary();
  const lines = [
    "# ATEE Frontend Live Production Rehearsal",
    "",
    `- Generated at UTC: ${new Date().toISOString()}`,
    `- Overall OK: ${data.ok}`,
    `- Live provider used: ${data.live_used}`,
    `- Browser visible: ${data.browser_visible}`,
    `- Target duration seconds: ${data.duration_target_seconds}`,
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
    "## Counts",
    "",
    "| Item | Value |",
    "|---|---:|",
    ...countLines("scenario", data.scenario_counts),
    ...countLines("route", data.route_counts),
    ...countLines("rule", data.rule_counts),
    ...countLines("action", data.action_counts),
    ...countLines("llm_reason", data.llm_reason_counts),
    "",
    "## Admin AI Checks",
    "",
    "| Check | OK | Reason | Latency ms | Raw reply omitted |",
    "|---|---|---|---:|---|",
    ...data.admin_ai_checks.map((check) => (
      `| ${check.name} | ${check.ok} | ${check.reason || "-"} | ${check.latency_ms || 0} | ${Boolean(check.raw_reply_omitted)} |`
    )),
    "",
    "## Runtime",
    "",
    `- Async review status: ${JSON.stringify(data.async_review)}`,
    `- Ledger persisted records: ${data.ledger?.persisted_records}`,
    `- Actions executed: ${data.actions_executed}`,
    "",
    "## Samples",
    "",
    "| Scenario | Route | Rule | Action | LLM Reason | Executed | OK |",
    "|---|---|---|---|---|---|---|",
    ...data.samples.map((sample) => (
      `| ${sample.scenario} | ${sample.route} | ${sample.rule} | ${sample.action} | ${sample.llm_reason} | ${sample.executed} | ${sample.ok} |`
    )),
    "",
    "## Issues",
    "",
  ];
  if (!data.issues.length) {
    lines.push("No blocking issue was found in this rehearsal.");
  } else {
    for (const issue of data.issues) {
      lines.push(`- [${issue.risk}] ${issue.title}: ${issue.detail}`);
    }
  }
  lines.push(
    "",
    "## Security Notes",
    "",
    "- API keys, key file paths, proxy URLs, API base URLs, auth headers, raw prompts, and raw request bodies are intentionally omitted.",
    "- The visible browser uses the local demo frontend and submits through the same form-backed endpoints as a user session.",
  );
  return `${lines.join("\n")}\n`;
}

function countLines(prefix, counts) {
  return Object.entries(counts || {})
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([key, value]) => `| ${prefix}:${key} | ${value} |`);
}

async function expectText(targetPage, text) {
  const content = await targetPage.locator("body").textContent({ timeout: 15000 });
  if (!String(content || "").includes(text)) {
    throw new Error(`page did not contain text: ${text}`);
  }
}

async function expectSelector(targetPage, selector) {
  const count = await targetPage.locator(selector).count();
  if (count < 1) {
    throw new Error(`page did not contain selector: ${selector}`);
  }
}

function startProcess(command, commandArgs, extraEnv) {
  const child = spawn(command, commandArgs, {
    cwd: root,
    env: { ...process.env, ...extraEnv },
    stdio: ["ignore", "ignore", "pipe"],
  });
  let stderr = "";
  child.stderr.on("data", (chunk) => {
    stderr += String(chunk);
    if (stderr.length > 2000) {
      stderr = stderr.slice(-2000);
    }
  });
  child.on("exit", (code) => {
    if (code && summary.stop_reason === null) {
      summary.issues.push({ title: `${commandArgs[0]}_exited`, detail: `exit_code=${code}; stderr=${stderr}`, risk: "high" });
    }
  });
  return child;
}

async function waitForHealth(url, label) {
  const deadline = Date.now() + 30000;
  let lastError = "";
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) {
        return;
      }
      lastError = `HTTP ${response.status}`;
    } catch (error) {
      lastError = error.message;
    }
    await delay(250);
  }
  throw new Error(`${label} did not become healthy: ${lastError}`);
}

async function freePort() {
  const server = net.createServer();
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  const address = server.address();
  const port = address.port;
  await new Promise((resolve) => server.close(resolve));
  return port;
}

function findChrome() {
  const candidates = [
    process.env.CHROME_PATH,
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
    "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  ].filter(Boolean);
  for (const candidate of candidates) {
    if (existsSync(candidate)) {
      return path.resolve(candidate);
    }
  }
  throw new Error("Chrome or Edge executable was not found. Set CHROME_PATH to run the frontend rehearsal.");
}

function parseArgs(argv) {
  const result = {};
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (!arg.startsWith("--")) {
      continue;
    }
    const key = arg.slice(2);
    if (key === "headless") {
      result[key] = true;
      continue;
    }
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

function stringArg(source, key, fallback) {
  const value = source[key];
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
