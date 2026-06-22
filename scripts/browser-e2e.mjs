import { chromium } from "playwright-core";
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import net from "node:net";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const chromePath = findChrome();
const pythonExe = process.env.PYTHON || "python";
const apiResponses = [];
let apiResponseCursor = 0;

const port = await freePort();
const tempDir = await mkdtemp(path.join(tmpdir(), "atee-browser-e2e-"));
let server;
let browser;

try {
  server = startCore(port, tempDir);
  await waitForHealth(port);

  browser = await chromium.launch({
    executablePath: chromePath,
    headless: true,
  });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const consoleErrors = [];
  page.on("console", (message) => {
    if (message.type() === "error") {
      consoleErrors.push(message.text());
    }
  });
  page.on("response", async (response) => {
    try {
      const pathName = new URL(response.url()).pathname;
      const contentType = response.headers()["content-type"] || "";
      if (!pathName.startsWith("/v1/") || !contentType.includes("application/json")) {
        return;
      }
      apiResponses.push({ path: pathName, data: await response.json() });
      if (apiResponses.length > 80) {
        apiResponses.splice(0, apiResponses.length - 80);
      }
    } catch {
      // Non-JSON or already-consumed responses are irrelevant to these checks.
    }
  });

  await page.goto(`http://127.0.0.1:${port}/`, { waitUntil: "domcontentloaded" });
  await expectText(page, "ATEE Control Plane");
  await expectText(page, "模型网关");
  await openTab(page, "活动页");
  await expectText(page, "安全演练");

  await click(page, "#testSafeBtn");
  await expectResult(page, (data) => data.route?.route === "skip", "safe request should skip");

  await click(page, "#testAttackBtn");
  await expectResult(page, (data) => data.route?.route === "fast_path_block", "attack should hit fast path");

  await click(page, "#testAppealBtn");
  await expectResult(page, (data) => data.status === 202, "appeal should be accepted");

  await click(page, "#testLlmBtn");
  await expectResult(page, (data) => data.ok === true, "LLM gateway test should run from dashboard");

  const asyncSource = await postJson(page, "/v1/check", {
    method: "POST",
    path: "/comment",
    event_type: "comment_create",
    body: { text: "browser e2e async review comment" },
    remote_addr: "198.51.100.10",
  });
  if (asyncSource.route?.route !== "async_agent" || asyncSource.llm_gateway?.reason !== "async_review_queued") {
    throw new Error(`async source request was not queued: ${JSON.stringify(asyncSource)}`);
  }

  await openTab(page, "异步 AI 审查");
  await expectText(page, "异步 AI 审查队列");
  await click(page, "#asyncReviewsBtn");
  await expectResult(page, (data) => Array.isArray(data.jobs) && data.count >= 1, "async AI review queue should list pending jobs");
  await click(page, "#runAsyncReviewsBtn");
  await expectResult(page, (data) => data.ok === true && data.claimed >= 1, "async review run should process due jobs");

  await openTab(page, "Agent 对话");
  await selectAntD(page, "#siteTypeSelect", "论坛/社区");
  await selectAntD(page, "#adapterTypeSelect", "HTTP API");
  await page.locator("#agentChatInput").fill("如何先用观察模式上线？");
  await click(page, "#agentChatSendBtn");
  await expectResult(page, (data) => data.reason === "mock_chat", "agent chat should respond in mock mode");

  await openTab(page, "新手引导");
  await selectAntD(page, "#guideSiteTypeSelect", "API 服务");
  await selectAntD(page, "#guideAdapterTypeSelect", "反向代理/Nginx");
  await click(page, "#preflightBtn");
  await expectResult(page, (data) => Array.isArray(data.checks), "preflight checks should run from guide");
  await click(page, "#securityFlowBtn");
  await expectResult(page, (data) => Array.isArray(data.flow_steps) && data.flow_steps.length >= 7, "security flow rehearsal should run from guide");
  await selectAntD(page, "#guideAdapterTypeSelect", "HTTP API");
  await page.locator("#integrationSiteNameInput").fill("browser-target");
  await page.locator("#integrationSiteUrlInput").fill("https://browser-target.example");
  await page.locator("#integrationCoreUrlInput").fill(`http://127.0.0.1:${port}`);
  await page.locator("#integrationAppealPathInput").fill("/security/appeal");
  await page.locator("#integrationProtectedFeaturesInput").fill("comments\nuploads");
  await click(page, "#integrationPlanBtn");
  await expectResult(
    page,
    (data) => data.ok === true && data.endpoint_mappings?.length === 4,
    "HTTP API integration plan should be generated from guide",
  );
  await expectText(page, "/v1/check");
  await expectText(page, "/v1/event");
  await expectText(page, "/v1/feature-access");
  await expectText(page, "/v1/appeal");
  await expectText(page, "安全情况处理总流程");
  await page.locator(".ant-collapse-header", { hasText: "网站类型选择" }).click();
  await click(page, "#guideAction-site_type");
  await expectText(page, "AI 安全助手");
  await expectValue(page, "#agentChatInput", (value) => value.includes("API 服务"), "guide site type action should prefill an Agent question");

  await openTab(page, "申诉处理");
  await expectText(page, "申诉审核");
  await click(page, "#appealsBtn");
  await expectResult(page, (data) => data.count === 1, "pending appeal should be listed");

  await page.locator("#appealIdInput").fill("demo-punishment");
  await page.locator("#appealNoteInput").fill("browser e2e approved");
  await click(page, "#approveAppealBtn");
  await confirmPopconfirm(page);
  await expectResult(page, (data) => data.ok === true && data.appeal?.status === "approved", "appeal should be approved");

  const rejectedAppeal = await postJson(page, "/v1/appeal", {
    punishment_id: "browser-reject-punishment",
    reason: "browser e2e reject rehearsal",
  });
  if (rejectedAppeal.status !== 202) {
    throw new Error(`reject rehearsal appeal was not accepted: ${JSON.stringify(rejectedAppeal)}`);
  }
  await click(page, "#appealsBtn");
  await expectResult(page, (data) => data.count === 1, "second pending appeal should be listed");
  await page.locator("#appealIdInput").fill("browser-reject-punishment");
  await page.locator("#appealNoteInput").fill("browser e2e rejected");
  await click(page, "#rejectAppealBtn");
  await confirmPopconfirm(page);
  await expectResult(page, (data) => data.ok === true && data.appeal?.status === "rejected", "appeal should be rejected");

  await click(page, "#degradedBtn");
  await expectResult(page, (data) => data.ok === true && data.mode === "degraded", "runtime mode should switch to degraded");
  await click(page, "#readOnlyBtn");
  await expectResult(page, (data) => data.ok === true && data.mode === "read_only", "runtime mode should switch to read only");
  await expectText(page, "当前为只读模式");
  await openTab(page, "申诉处理");
  await expectDisabled(page, "#approveAppealBtn", "read-only mode should disable appeal approval");
  await expectDisabled(page, "#rejectAppealBtn", "read-only mode should disable appeal rejection");
  await openTab(page, "异步 AI 审查");
  await expectDisabled(page, "#runAsyncReviewsBtn", "read-only mode should disable async review processing");
  await openTab(page, "动作管理");
  await expectDisabled(page, "#cleanupActionsBtn", "read-only mode should disable action cleanup");
  await expectDisabled(page, "#revokeActionBtn", "read-only mode should disable action revoke");
  await openTab(page, "网关配置");
  await expectDisabled(page, "#configSaveBtn", "read-only mode should disable config save");
  await openTab(page, "新手引导");
  await expectDisabled(page, "#securityFlowBtn", "read-only mode should disable security flow rehearsal");
  await click(page, "#autoBtn");
  await confirmPopconfirm(page);
  await expectResult(page, (data) => data.ok === true && data.mode === "auto", "runtime mode should switch to auto");
  await openTab(page, "活动页");
  await expectText(page, "安全演练");
  await click(page, "#testAttackBtn");
  await expectResult(page, (data) => data.action_result?.executed === true, "auto mode should execute action");

  await openTab(page, "动作管理");
  await expectText(page, "动作撤销");
  await click(page, "#actionsBtn");
  const actions = await expectResult(page, (data) => Array.isArray(data.actions), "actions should be listed");
  const actionId = actions.actions?.[0]?.id;
  if (!actionId) {
    throw new Error("active action id was not found");
  }

  await page.locator("#actionIdInput").fill(String(actionId));
  await page.locator("#revokeReasonInput").fill("browser e2e revoke");
  await click(page, "#revokeActionBtn");
  await confirmPopconfirm(page);
  await expectResult(page, (data) => data.ok === true && data.action?.status === "revoked", "action should be revoked");

  await openTab(page, "安全账本");
  await page.locator("#ledgerLimitInput").fill("5");
  await click(page, "#ledgerBtn");
  await expectResult(page, (data) => data.ok === true && Array.isArray(data.records), "ledger records should be listed");

  await openTab(page, "网关配置");
  await expectText(page, "运行配置");
  await click(page, "#configBtn");
  await expectResult(page, (data) => data.ok === true && data.config, "config should be loaded");
  await page.locator("#localPrecheckInput").fill("123");
  await click(page, "#configSaveBtn");
  await confirmPopconfirm(page);
  await expectResult(page, (data) => data.ok === true && data.changed?.local_precheck_ms === 123, "config should be saved");
  await click(page, "#testLlmConfigBtn");
  await expectResult(page, (data) => data.ok === true, "LLM gateway test should run from config tab");
  await click(page, "#breakGlassBtn");
  await expectResult(page, (data) => data.valid_for_request === false, "break-glass status should be checked");

  if (consoleErrors.length) {
    throw new Error(`browser console errors: ${consoleErrors.join("; ")}`);
  }
  console.log(JSON.stringify({ ok: true, port, checks: 33 }, null, 2));
} finally {
  if (browser) {
    await browser.close();
  }
  if (server) {
    server.kill();
  }
  await rm(tempDir, { recursive: true, force: true });
}

function startCore(port, tempDir) {
  const code = [
    "import os, sys",
    "from pathlib import Path",
    "root = Path(os.environ['ATEE_E2E_ROOT'])",
    "sys.path.insert(0, str(root / 'services' / 'core-service'))",
    "from atee_core.config import AdminConfig",
    "from atee_core.core import CoreService",
    "from atee_core import http_server",
    "http_server.CORE = CoreService(config=AdminConfig(llm_mode='mock', llm_provider='mock', llm_model='atee-local-mock-v1'), config_path=Path(os.environ['ATEE_E2E_CONFIG']))",
    "http_server.run(port=int(os.environ['ATEE_E2E_PORT']))",
  ].join("; ");
  return spawn(pythonExe, ["-c", code], {
    cwd: root,
    env: {
      ...process.env,
      ATEE_E2E_ROOT: root,
      ATEE_E2E_CONFIG: path.join(tempDir, "config", "config.json"),
      ATEE_E2E_PORT: String(port),
    },
    stdio: ["ignore", "ignore", "pipe"],
  });
}

async function waitForHealth(port) {
  const deadline = Date.now() + 15000;
  let lastError = "";
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`http://127.0.0.1:${port}/health`);
      if (response.ok) {
        return;
      }
      lastError = `HTTP ${response.status}`;
    } catch (error) {
      lastError = error.message;
    }
    await delay(250);
  }
  throw new Error(`Core service did not become healthy: ${lastError}`);
}

async function click(page, selector) {
  const locator = page.locator(selector);
  const count = await locator.count();
  if (count !== 1) {
    throw new Error(`${selector} resolved to ${count} elements`);
  }
  apiResponseCursor = apiResponses.length;
  try {
    await locator.click({ timeout: 5000 });
  } catch {
    await locator.evaluate((element) => {
      if (element.disabled) {
        throw new Error("element is disabled");
      }
      element.click();
    });
  }
}

async function confirmPopconfirm(page) {
  const locator = page.locator(".ant-popconfirm-buttons .ant-btn-primary").last();
  apiResponseCursor = apiResponses.length;
  try {
    await locator.click({ timeout: 5000 });
  } catch {
    await locator.evaluate((element) => element.click());
  }
}

async function selectAntD(page, selector, label) {
  await page.locator(selector).click();
  const option = page.locator(".ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item-option", {
    hasText: label,
  }).last();
  await option.click({ timeout: 5000 });
}

async function postJson(page, path, payload) {
  return page.evaluate(
    async ({ path, payload }) => {
      const response = await fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      return response.json();
    },
    { path, payload },
  );
}

async function openTab(page, label) {
  const menuLocator = page.locator(".ant-menu-item", { hasText: label });
  const menuCount = await menuLocator.count();
  if (menuCount === 1) {
    try {
      await menuLocator.click({ timeout: 5000 });
    } catch {
      await menuLocator.evaluate((element) => element.click());
    }
    return;
  }

  const locator = page.locator(".ant-tabs-tab", { hasText: label });
  const count = await locator.count();
  if (count !== 1) {
    throw new Error(`${label} tab resolved to ${count} elements`);
  }
  const key = await locator.getAttribute("data-node-key");
  if (key) {
    const clickedMenuItem = await page.evaluate((tabKey) => {
      const menuItems = Array.from(document.querySelectorAll(".ant-menu-item"));
      const target = menuItems.find((element) => {
        const menuId = element.getAttribute("data-menu-id") || "";
        return menuId === tabKey || menuId.endsWith(`-${tabKey}`);
      });
      if (!target) {
        return false;
      }
      target.click();
      return true;
    }, key);
    if (clickedMenuItem) {
      return;
    }
  }
  try {
    await locator.click({ timeout: 5000 });
  } catch {
    await locator.evaluate((element) => element.click());
  }
}

async function expectText(page, text) {
  await page.waitForFunction(
    (expected) => String(document.body?.textContent || "").includes(expected),
    text,
    { timeout: 10000 },
  );
}

async function expectResult(page, predicate, message) {
  const deadline = Date.now() + 10000;
  let parsed;
  while (Date.now() < deadline) {
    parsed = await resultJson(page);
    if (predicate(parsed)) {
      return parsed;
    }
    for (const item of apiResponses.slice(apiResponseCursor)) {
      parsed = item.data;
      if (predicate(parsed)) {
        return parsed;
      }
    }
    await delay(200);
  }
  throw new Error(`${message}; last result: ${JSON.stringify(parsed)}`);
}

async function expectValue(page, selector, predicate, message) {
  const deadline = Date.now() + 10000;
  let value = "";
  while (Date.now() < deadline) {
    value = await page.locator(selector).inputValue();
    if (predicate(value)) {
      return value;
    }
    await delay(200);
  }
  throw new Error(`${message}; last value: ${JSON.stringify(value)}`);
}

async function expectDisabled(page, selector, message) {
  const deadline = Date.now() + 10000;
  let disabled = false;
  while (Date.now() < deadline) {
    disabled = await page.locator(selector).isDisabled();
    if (disabled) {
      return true;
    }
    await delay(200);
  }
  throw new Error(`${message}; disabled=${disabled}`);
}

async function resultJson(page) {
  const locator = page.locator("#result");
  if ((await locator.count()) < 1) {
    return {};
  }
  const text = (await locator.first().textContent({ timeout: 500 })) || "{}";
  try {
    return JSON.parse(text);
  } catch {
    return {};
  }
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
  throw new Error("Chrome or Edge executable was not found. Set CHROME_PATH to run browser E2E.");
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
