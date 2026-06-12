import { chromium } from "playwright-core";
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import net from "node:net";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const args = parseArgs(process.argv.slice(2));
const durationSeconds = intArg(args, "duration-seconds", 10800);
const intervalSeconds = intArg(args, "interval-seconds", 60);
const scenarioMode = args.scenario || "overrun_intrusion";
const initialBudgetCents = nonNegativeIntArg(args, "initial-budget-cents", 110);
const recoveryExtraBudgetCents = nonNegativeIntArg(args, "recovery-extra-budget-cents", 100);
const corePort = optionalIntArg(args, "core-port") || 8787;
const demoPort = optionalIntArg(args, "demo-port") || 8790;
const adapterTimeoutSeconds = intArg(args, "adapter-timeout-seconds", 25);
const burstSize = intArg(args, "burst-size", 160);
const burstConcurrency = intArg(args, "burst-concurrency", 24);
const ledgerSqlitePath = args["ledger-sqlite-path"] || "";
const reportPath = path.resolve(root, args.report || "reports/frontend-budget-overrun-intrusion-rehearsal.md");
const statusPath = path.resolve(root, args.status || "reports/frontend-budget-overrun-intrusion-rehearsal.status.json");
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
  mode: "frontend_budget_overrun_intrusion_rehearsal",
  scenario: scenarioMode,
  live_used: true,
  generated_at: new Date().toISOString(),
  duration_target_seconds: durationSeconds,
  interval_seconds: intervalSeconds,
  initial_budget_cents: initialBudgetCents,
  recovery_extra_budget_cents: recoveryExtraBudgetCents,
  ledger_sqlite_path: ledgerSqlitePath,
  core_port: corePort,
  demo_port: demoPort,
  started_at: null,
  completed_at: null,
  elapsed_seconds: 0,
  stop_reason: null,
  cycles_completed: 0,
  frontend_submissions: 0,
  frontend_failures: 0,
  batch_failures: 0,
  phase_counts: {},
  scenario_counts: {},
  route_counts: {},
  rule_counts: {},
  action_counts: {},
  llm_reason_counts: {},
  status_counts: {},
  phase_results: [],
  issues: [],
  code_findings: [],
  samples: [],
  latency_ms: { values: [], min: 0, max: 0, avg: 0 },
  batch_latency_ms: { values: [], min: 0, max: 0, avg: 0 },
  queue_high_water: { queued: 0, pending: 0, retry: 0, processing: 0, completed: 0, dead_letter: 0 },
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
  await expectPageReady(page);

  summary.started_at = new Date().toISOString();
  await writeStatus("running");

  await verifyPreviousFixPhase();
  await initialBudgetPhase();
  await budgetOverrunPhase();
  await degradedRunPhase();
  if (scenarioMode === "overrun_degraded") {
    await degradedLongRunPhase();
  } else {
    await recoveryBudgetPhase();
    await intrusionOverloadPhase();
  }

  summary.stop_reason ||= "duration_complete";
  summary.completed_at = new Date().toISOString();
  summary.elapsed_seconds = Math.round((Date.now() - Date.parse(summary.started_at)) / 1000);
  updateRuntimeSummary(await runtimeStatus());
  inspectProblemCode();
  summary.ok = summary.phase_results.every((item) => item.ok) && summary.frontend_failures === 0;
  await writeStatus("completed");
  await writeReport();
  console.log(JSON.stringify(publicSummary(), null, 2));
  process.exitCode = summary.ok ? 0 : 1;
} catch (error) {
  summary.stop_reason = "exception";
  summary.completed_at = new Date().toISOString();
  summary.issues.push({ title: "rehearsal_exception", detail: String(error?.message || error).slice(0, 700), risk: "high" });
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
    async_review_worker_interval_seconds: Number(originalConfig.async_review_worker_interval_seconds || 5),
    async_review_worker_batch_size: Number(originalConfig.async_review_worker_batch_size || 5),
    llm_daily_budget_cents: initialBudgetCents,
  };
  if (ledgerSqlitePath) {
    configPayload.ledger_sqlite_path = ledgerSqlitePath;
  }
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

async function verifyPreviousFixPhase() {
  const before = await runtimeStatus();
  const beforeSpend = Number(before.llm_gateway?.budget?.daily_spend_cents || 0);
  const beforeFailures = Number(before.llm_gateway?.circuit?.consecutive_failures || 0);
  await updateConfig({ llm_daily_budget_cents: initialBudgetCents, runtime_mode: "auto" });
  const after = await runtimeStatus();
  const afterSpend = Number(after.llm_gateway?.budget?.daily_spend_cents || 0);
  const afterFailures = Number(after.llm_gateway?.circuit?.consecutive_failures || 0);
  const ok = afterSpend === beforeSpend && afterFailures === beforeFailures;
  recordPhase("previous_fix_runtime_state_preserved", ok, {
    before_budget: before.llm_gateway?.budget,
    after_budget: after.llm_gateway?.budget,
    before_circuit: before.llm_gateway?.circuit,
    after_circuit: after.llm_gateway?.circuit,
  });
}

async function initialBudgetPhase() {
  const before = await runtimeStatus();
  const result = await submitScenario("initial_1_1_yuan_budget", "baseline_login", async () => submitLogin("budget-1-1", "ok-password"));
  const after = await runtimeStatus();
  const reason = result.llm_reason;
  const ok = result.route === "sync_agent" && ["provider_json_decision", "llm_budget_exhausted"].includes(reason) && Number(after.llm_gateway?.budget?.daily_budget_cents) === initialBudgetCents;
  recordPhase("initial_1_1_yuan_budget", ok, {
    before_budget: before.llm_gateway?.budget,
    after_budget: after.llm_gateway?.budget,
    sample: result,
  });
}

async function budgetOverrunPhase() {
  const attempts = [];
  const started = Date.now();
  let runtime = await runtimeStatus();
  let remaining = Number(runtime.llm_gateway?.budget?.daily_remaining_cents ?? initialBudgetCents);
  let exhausted = false;
  const maxAttempts = Math.max(8, initialBudgetCents + 12);
  for (let index = 1; index <= maxAttempts; index += 1) {
    const result = await submitScenario("budget_overrun", `budget_login_${index}`, async () => submitLogin(`overrun-${index}`, "ok-password"));
    attempts.push(result);
    if (result.llm_reason === "llm_budget_exhausted") {
      exhausted = true;
      break;
    }
    runtime = await runtimeStatus();
    remaining = Number(runtime.llm_gateway?.budget?.daily_remaining_cents ?? 0);
    if (remaining <= 0) {
      const exhaustedCheck = await submitScenario("budget_overrun", "budget_exhausted_probe", async () => submitLogin("overrun-probe", "ok-password"));
      attempts.push(exhaustedCheck);
      exhausted = exhaustedCheck.llm_reason === "llm_budget_exhausted";
      break;
    }
    if (Date.now() - started > Math.min(3600, Math.max(600, durationSeconds / 4)) * 1000) {
      break;
    }
  }
  runtime = await runtimeStatus();
  const reasons = countBy(attempts.map((item) => item.llm_reason));
  const ok = exhausted && Number(runtime.llm_gateway?.budget?.daily_remaining_cents ?? 0) === 0;
  recordPhase("budget_overrun_to_exhaustion", ok, {
    attempts: attempts.length,
    reason_counts: reasons,
    budget: runtime.llm_gateway?.budget,
    circuit: runtime.llm_gateway?.circuit,
  });
}

async function degradedRunPhase() {
  await updateConfig({ runtime_mode: "degraded", llm_daily_budget_cents: initialBudgetCents });
  const runtimeBefore = await runtimeStatus();
  const results = [];
  results.push(await submitScenario("degraded_running", "degraded_login_budget_exhausted", async () => submitLogin("degraded-login", "ok-password")));
  results.push(await submitScenario("degraded_running", "degraded_comment_async", async () => submitComment("degraded mode async review payload")));
  results.push(await submitScenario("degraded_running", "degraded_sqli_block", async () => submitLogin("' OR 1=1 --", "attack")));
  const runtimeAfter = await runtimeStatus();
  const ok = runtimeAfter.runtime_mode === "degraded" && results.some((item) => item.llm_reason === "llm_budget_exhausted") && results.some((item) => item.route === "fast_path_block");
  recordPhase("degraded_running_after_budget_overrun", ok, {
    runtime_before: pickRuntime(runtimeBefore),
    runtime_after: pickRuntime(runtimeAfter),
    samples: results,
  });
}

async function degradedLongRunPhase() {
  const deadlineMs = Date.parse(summary.started_at) + durationSeconds * 1000;
  const startedCycle = summary.cycles_completed;
  while (Date.now() < deadlineMs) {
    const cycle = summary.cycles_completed + 1;
    const cycleStarted = Date.now();
    await submitScenario("degraded_long_run", "degraded_login_budget_exhausted", async () => submitLogin(`degraded-long-${cycle}`, "ok-password"));
    await submitScenario("degraded_long_run", "degraded_comment_async", async () => submitComment(`degraded mode comment ${cycle}`));
    await submitScenario("degraded_long_run", "degraded_upload_async", async () => submitUpload(`degraded-${cycle}.txt`, "normal degraded upload"));
    if (cycle % 3 === 0) {
      await submitScenario("degraded_long_run", "degraded_sqli_block", async () => submitLogin("' OR 1=1 --", "attack"));
    }
    summary.cycles_completed = cycle;
    const runtime = await runtimeStatus();
    updateRuntimeSummary(runtime);
    await writeStatus("running");
    const sleepMs = Math.max(0, intervalSeconds * 1000 - (Date.now() - cycleStarted));
    await delay(Math.min(sleepMs, Math.max(0, deadlineMs - Date.now())));
  }
  const runtime = await runtimeStatus();
  const queue = runtime.async_review || {};
  const ok = runtime.runtime_mode === "degraded"
    && Number(runtime.llm_gateway?.budget?.daily_remaining_cents ?? 0) === 0
    && Number(queue.dead_letter || 0) === 0
    && Number(summary.llm_reason_counts.llm_budget_exhausted || 0) > 0
    && summary.frontend_failures === 0;
  recordPhase("degraded_long_run_after_budget_overrun", ok, {
    cycles_completed: summary.cycles_completed - startedCycle,
    queue_high_water: summary.queue_high_water,
    final_queue: queue,
    final_budget: runtime.llm_gateway?.budget,
    final_circuit: runtime.llm_gateway?.circuit,
    frontend_failures: summary.frontend_failures,
  });
}

async function recoveryBudgetPhase() {
  const before = await runtimeStatus();
  const spent = Number(before.llm_gateway?.budget?.daily_spend_cents || 0);
  const recoveryBudget = spent + recoveryExtraBudgetCents;
  await waitForCircuitToClose(90_000);
  await updateConfig({ runtime_mode: "auto", llm_daily_budget_cents: recoveryBudget });
  const afterConfig = await runtimeStatus();
  const recovery = await submitScenario("recovery_plus_1_yuan_budget", "recovery_login", async () => submitLogin("recovery-plus-one", "ok-password"));
  const afterLogin = await runtimeStatus();
  const ok = recovery.route === "sync_agent" && recovery.llm_reason === "provider_json_decision" && Number(afterConfig.llm_gateway?.budget?.daily_remaining_cents || 0) >= recoveryExtraBudgetCents;
  recordPhase("recovery_core_plus_1_yuan_budget", ok, {
    spent_before_recovery: spent,
    recovery_budget_cents: recoveryBudget,
    after_config_budget: afterConfig.llm_gateway?.budget,
    recovery_sample: recovery,
    after_login_budget: afterLogin.llm_gateway?.budget,
  });
}

async function intrusionOverloadPhase() {
  const deadlineMs = Date.parse(summary.started_at) + durationSeconds * 1000;
  const startedCycle = summary.cycles_completed;
  while (Date.now() < deadlineMs) {
    const cycle = summary.cycles_completed + 1;
    const cycleStarted = Date.now();
    const batch = await submitIntrusionBatch(cycle, burstSize, burstConcurrency);
    recordBatch("post_recovery_intrusion_overload", `intrusion_batch_${cycle}`, batch);
    summary.cycles_completed = cycle;
    const runtime = await runtimeStatus();
    updateRuntimeSummary(runtime);
    await writeStatus("running");
    const sleepMs = Math.max(0, intervalSeconds * 1000 - (Date.now() - cycleStarted));
    await delay(Math.min(sleepMs, Math.max(0, deadlineMs - Date.now())));
  }
  const runtime = await runtimeStatus();
  const queue = runtime.async_review || {};
  const overloadObserved = Number(summary.queue_high_water.queued || 0) > Number(runtime.async_review_worker?.batch_size || 5) * 3
    || Number(summary.queue_high_water.dead_letter || 0) > 0
    || Number(queue.queued || 0) > 0;
  const budgetExhaustedObserved = Number(summary.llm_reason_counts.llm_budget_exhausted || 0) > 0 || Number(queue.dead_letter || 0) > 0;
  const ok = summary.cycles_completed > startedCycle && overloadObserved && budgetExhaustedObserved;
  recordPhase("post_recovery_intrusion_overload", ok, {
    cycles_completed: summary.cycles_completed - startedCycle,
    burst_size: burstSize,
    burst_concurrency: burstConcurrency,
    queue_high_water: summary.queue_high_water,
    final_queue: queue,
    final_budget: runtime.llm_gateway?.budget,
    final_circuit: runtime.llm_gateway?.circuit,
    frontend_failures: summary.frontend_failures,
    batch_failures: summary.batch_failures,
  });
}

async function submitLogin(username, password) {
  await page.locator('#loginForm input[name="username"]').fill(String(username));
  await page.locator('#loginForm input[name="password"]').fill(String(password));
  return submitAndRead("/api/login", "#loginForm button");
}

async function submitComment(text) {
  await page.locator('#commentForm textarea[name="text"]').fill(String(text));
  return submitAndRead("/api/comment", "#commentForm button");
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
  if (payload._response_status !== 200 || !payload.ok) {
    const expectedBlock = sample.route === "fast_path_block" && sample.action === "challenge";
    if (!expectedBlock) {
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
    { timeout: 60000 },
  );
  await page.locator(buttonSelector).click();
  const response = await responsePromise;
  const payload = await response.json();
  payload._response_status = response.status();
  await page.waitForFunction((count) => document.querySelectorAll("#resultList article").length > count, before, { timeout: 10000 });
  return payload;
}

async function submitIntrusionBatch(cycle, size, concurrency) {
  return page.evaluate(
    async ({ cycle, size, concurrency }) => {
      const scenarios = Array.from({ length: size }, (_, index) => {
        const id = `${cycle}-${index}`;
        if (index % 10 === 0) {
          return { name: "attack_upload_php", path: "/api/upload", body: { filename: `shell-${id}.php`, text: "GIF89a<?php system($_GET['cmd']); ?>" } };
        }
        if (index % 4 === 0) {
          return { name: "attack_sqli_login", path: "/api/login", body: { username: "' OR 1=1 --", password: "attack" } };
        }
        if (index % 3 === 0) {
          return { name: "async_upload_noise", path: "/api/upload", body: { filename: `invoice-${id}.txt`, text: `large post recovery upload ${id}` } };
        }
        return { name: "async_comment_noise", path: "/api/comment", body: { text: `post recovery high volume comment ${id}` } };
      });
      const started = performance.now();
      const results = [];
      let cursor = 0;
      async function worker() {
        while (cursor < scenarios.length) {
          const current = scenarios[cursor++];
          const itemStarted = performance.now();
          try {
            const response = await fetch(current.path, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(current.body),
            });
            const payload = await response.json();
            results.push({
              scenario: current.name,
              status: response.status,
              ok: Boolean(payload.ok),
              latency_ms: Math.round(performance.now() - itemStarted),
              payload,
            });
          } catch (error) {
            results.push({
              scenario: current.name,
              status: 0,
              ok: false,
              latency_ms: Math.round(performance.now() - itemStarted),
              error: String(error?.message || error),
            });
          }
        }
      }
      await Promise.all(Array.from({ length: Math.max(1, concurrency) }, () => worker()));
      return { cycle, elapsed_ms: Math.round(performance.now() - started), results };
    },
    { cycle, size, concurrency },
  );
}

function recordBatch(phase, name, batch) {
  summary.phase_counts[phase] = (summary.phase_counts[phase] || 0) + 1;
  summary.scenario_counts[name] = (summary.scenario_counts[name] || 0) + 1;
  summary.batch_latency_ms.values.push(Number(batch.elapsed_ms || 0));
  updateLatencyFor(summary.batch_latency_ms);
  for (const item of batch.results || []) {
    summary.frontend_submissions += 1;
    summary.scenario_counts[item.scenario] = (summary.scenario_counts[item.scenario] || 0) + 1;
    const payload = item.payload || {};
    payload._response_status = item.status;
    const sample = recordPayload(phase, item.scenario, payload, Number(item.latency_ms || 0));
    const expectedBlock = sample.route === "fast_path_block" && sample.action === "challenge";
    if (item.status !== 200 || (!item.ok && !expectedBlock)) {
      summary.frontend_failures += 1;
      summary.batch_failures += 1;
      if (summary.issues.length < 50) {
        summary.issues.push({ title: `${item.scenario}_batch_failed`, detail: `status=${item.status}; ok=${item.ok}; error=${item.error || payload.error || "-"}`, risk: "high" });
      }
    }
  }
}

function recordPayload(phase, name, payload, frontendLatencyMs = 0) {
  const core = payload.core_response || {};
  const route = core.route?.route || payload.security?.route || "unknown";
  const rule = core.fast_path?.rule_id || "-";
  const action = core.tool_gateway?.effective_action || payload.security?.effective_action || "-";
  const llmReason = core.llm_gateway?.reason || "-";
  const llmLatency = Number(core.llm_gateway?.latency_ms || core.llm_gateway?.provider_latency_ms || 0);
  const sample = { phase, scenario: name, status: payload._response_status, route, rule, action, llm_reason: llmReason, ok: Boolean(payload.ok) };
  summary.route_counts[route] = (summary.route_counts[route] || 0) + 1;
  summary.rule_counts[rule] = (summary.rule_counts[rule] || 0) + 1;
  summary.action_counts[action] = (summary.action_counts[action] || 0) + 1;
  summary.llm_reason_counts[llmReason] = (summary.llm_reason_counts[llmReason] || 0) + 1;
  summary.status_counts[String(payload._response_status || 0)] = (summary.status_counts[String(payload._response_status || 0)] || 0) + 1;
  const latency = llmLatency || frontendLatencyMs;
  if (latency > 0) {
    summary.latency_ms.values.push(latency);
    updateLatencyFor(summary.latency_ms);
  }
  if (summary.samples.length < 50) summary.samples.push(sample);
  return sample;
}

function recordPhase(name, ok, details) {
  summary.phase_results.push({ name, ok: Boolean(ok), details });
  if (!ok) summary.issues.push({ title: `${name}_failed`, detail: JSON.stringify(details).slice(0, 700), risk: "high" });
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
    llm_daily_budget_cents: Number(originalConfig.llm_daily_budget_cents ?? initialBudgetCents),
    async_review_worker_enabled: Boolean(originalConfig.async_review_worker_enabled),
    async_review_worker_interval_seconds: Number(originalConfig.async_review_worker_interval_seconds || 5),
    async_review_worker_batch_size: Number(originalConfig.async_review_worker_batch_size || 5),
  };
  if (Object.prototype.hasOwnProperty.call(originalConfig, "ledger_sqlite_path")) {
    payload.ledger_sqlite_path = originalConfig.ledger_sqlite_path;
  }
  if (originalProxyUrl !== "configured") payload.llm_proxy_url = originalProxyUrl;
  await updateConfig(payload).catch(() => {});
}

function inspectProblemCode() {
  const queue = summary.async_review || {};
  const worker = summary.async_review_worker || {};
  const queued = Number(summary.queue_high_water.queued || 0);
  const deadLetter = Number(summary.queue_high_water.dead_letter || 0);
  const maxDepth = Number(queue.max_depth || 0);
  if (queued > 0 && (!maxDepth || queue.backpressure === undefined)) {
    summary.code_findings.push({
      title: "async_review_queue_backpressure_not_reported",
      file: "services/core-service/atee_core/async_review.py",
      risk: "high",
      evidence: `high_water queued=${queued}; runtime queue status did not expose max_depth/backpressure.`,
    });
  }
  if (queued >= 10 && worker.adaptive !== true) {
    summary.code_findings.push({
      title: "async_worker_adaptive_scaling_not_enabled",
      file: "services/core-service/atee_core/async_review_worker.py",
      risk: "medium",
      evidence: `queued high-water ${queued}; worker status did not report adaptive=true.`,
    });
  }
  if (deadLetter > 0) {
    summary.code_findings.push({
      title: "budget_exhaustion_still_generates_dead_letters",
      file: "services/core-service/atee_core/core.py",
      risk: "high",
      evidence: `dead_letter high-water ${deadLetter}; budget exhaustion should pause async processing before claim.`,
    });
  }
}

function updateRuntimeSummary(runtime) {
  if (!runtime) return;
  summary.runtime_mode = runtime.runtime_mode;
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
  const queue = runtime.async_review || {};
  for (const key of Object.keys(summary.queue_high_water)) {
    summary.queue_high_water[key] = Math.max(Number(summary.queue_high_water[key] || 0), Number(queue[key] || 0));
  }
}

function updateLatencyFor(target) {
  const values = target.values.filter((item) => Number.isFinite(item));
  if (!values.length) return;
  target.min = Math.min(...values);
  target.max = Math.max(...values);
  target.avg = Math.round((values.reduce((total, value) => total + value, 0) / values.length) * 100) / 100;
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

async function waitForCircuitToClose(maxWaitMs) {
  const deadline = Date.now() + maxWaitMs;
  while (Date.now() < deadline) {
    const runtime = await runtimeStatus();
    updateRuntimeSummary(runtime);
    const remaining = Number(runtime.llm_gateway?.circuit?.remaining_ms || 0);
    if (!runtime.llm_gateway?.circuit?.open || remaining <= 0) return;
    await delay(Math.min(5000, remaining + 250));
  }
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

async function expectPageReady(targetPage) {
  await targetPage.locator("#loginForm").waitFor({ timeout: 15000 });
  await targetPage.locator("#commentForm").waitFor({ timeout: 15000 });
  await targetPage.locator("#uploadForm").waitFor({ timeout: 15000 });
}

function startProcess(command, commandArgs, extraEnv) {
  const child = spawn(command, commandArgs, { cwd: root, env: { ...process.env, ...extraEnv }, stdio: ["ignore", "ignore", "pipe"] });
  let stderr = "";
  child.stderr.on("data", (chunk) => { stderr = `${stderr}${String(chunk)}`.slice(-3000); });
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
  const { values: latencyValues, ...latency } = summary.latency_ms;
  const { values: batchLatencyValues, ...batchLatency } = summary.batch_latency_ms;
  return {
    ...summary,
    latency_ms: latency,
    batch_latency_ms: batchLatency,
    report_path: reportPath,
    status_path: statusPath,
    core_url: `http://127.0.0.1:${corePort}`,
    demo_url: `http://127.0.0.1:${demoPort}`,
  };
}

function markdownReport() {
  const data = publicSummary();
  const lines = [
    "# ATEE Frontend Budget Overrun Intrusion Rehearsal",
    "",
    `- Generated at UTC: ${new Date().toISOString()}`,
    `- Overall OK: ${data.ok}`,
    `- Elapsed seconds: ${data.elapsed_seconds}`,
    `- Stop reason: ${data.stop_reason}`,
    `- Frontend submissions: ${data.frontend_submissions}`,
    `- Frontend failures: ${data.frontend_failures}`,
    `- Batch failures: ${data.batch_failures}`,
    `- Initial budget cents: ${data.initial_budget_cents}`,
    `- Recovery extra budget cents: ${data.recovery_extra_budget_cents}`,
    `- Budget spend cents: ${data.llm_budget?.daily_spend_cents}`,
    `- Budget remaining cents: ${data.llm_budget?.daily_remaining_cents}`,
    `- Runtime mode: ${data.runtime_mode}`,
    `- LLM calls: ${data.llm_gateway?.calls}`,
    `- LLM failures: ${data.llm_gateway?.failures}`,
    `- LLM circuit open: ${data.llm_circuit?.open}`,
    `- Latency avg ms: ${data.latency_ms?.avg}`,
    `- Batch latency avg ms: ${data.batch_latency_ms?.avg}`,
    `- Queue high water: ${JSON.stringify(data.queue_high_water)}`,
    "",
    "## Phase Results",
    "",
    "| Phase | OK | Details |",
    "|---|---|---|",
    ...data.phase_results.map((item) => `| ${item.name} | ${item.ok} | ${JSON.stringify(item.details).replaceAll("|", "/").slice(0, 700)} |`),
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
    ...countLines("status", data.status_counts),
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
  lines.push("", "## Security Notes", "", "- API keys, key file paths, proxy URLs, API base URLs, Authorization headers, raw prompts, and raw request bodies are intentionally omitted.");
  return `${lines.join("\n")}\n`;
}

function countLines(prefix, counts) {
  return Object.entries(counts || {}).sort(([a], [b]) => a.localeCompare(b)).map(([key, value]) => `| ${prefix}:${key} | ${value} |`);
}

function countBy(values) {
  const counts = {};
  for (const value of values) counts[value || "-"] = (counts[value || "-"] || 0) + 1;
  return counts;
}

function pickRuntime(runtime) {
  return {
    runtime_mode: runtime.runtime_mode,
    budget: runtime.llm_gateway?.budget,
    circuit: runtime.llm_gateway?.circuit,
    async_review: runtime.async_review,
  };
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
