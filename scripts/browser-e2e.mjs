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

  await page.goto(`http://127.0.0.1:${port}/`, { waitUntil: "domcontentloaded" });
  await expectText(page, "ATEE 管理控制台");
  await expectText(page, "模型网关");
  await expectText(page, "安全演练");

  await click(page, "#testSafeBtn");
  await expectResult(page, (data) => data.route?.route === "skip", "safe request should skip");

  await click(page, "#testAttackBtn");
  await expectResult(page, (data) => data.route?.route === "fast_path_block", "attack should hit fast path");

  await click(page, "#testAppealBtn");
  await expectResult(page, (data) => data.status === 202, "appeal should be accepted");

  await openTab(page, "申诉处理");
  await expectText(page, "申诉审核");
  await click(page, "#appealsBtn");
  await expectResult(page, (data) => data.count === 1, "pending appeal should be listed");

  await page.locator("#appealIdInput").fill("demo-punishment");
  await page.locator("#appealNoteInput").fill("browser e2e approved");
  await click(page, "#approveAppealBtn");
  await confirmPopconfirm(page);
  await expectResult(page, (data) => data.ok === true && data.appeal?.status === "approved", "appeal should be approved");

  await click(page, "#degradedBtn");
  await expectResult(page, (data) => data.ok === true && data.mode === "degraded", "runtime mode should switch to degraded");
  await click(page, "#readOnlyBtn");
  await expectResult(page, (data) => data.ok === true && data.mode === "read_only", "runtime mode should switch to read only");
  await expectText(page, "当前为只读模式");
  await click(page, "#autoBtn");
  await confirmPopconfirm(page);
  await expectResult(page, (data) => data.ok === true && data.mode === "auto", "runtime mode should switch to auto");
  await openTab(page, "操作台");
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
  await expectResult(page, (data) => Array.isArray(data.records), "ledger records should be listed");

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
  console.log(JSON.stringify({ ok: true, port, checks: 16 }, null, 2));
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
  await locator.click();
}

async function confirmPopconfirm(page) {
  const locator = page.locator(".ant-popconfirm-buttons .ant-btn-primary").last();
  await locator.click({ timeout: 5000 });
}

async function openTab(page, label) {
  const locator = page.locator(".ant-tabs-tab", { hasText: label });
  const count = await locator.count();
  if (count !== 1) {
    throw new Error(`${label} tab resolved to ${count} elements`);
  }
  await locator.click();
}

async function expectText(page, text) {
  const content = await page.locator("body").textContent({ timeout: 10000 });
  if (!String(content || "").includes(text)) {
    throw new Error(`page did not contain text: ${text}`);
  }
}

async function expectResult(page, predicate, message) {
  const deadline = Date.now() + 10000;
  let parsed;
  while (Date.now() < deadline) {
    parsed = await resultJson(page);
    if (predicate(parsed)) {
      return parsed;
    }
    await delay(200);
  }
  throw new Error(`${message}; last result: ${JSON.stringify(parsed)}`);
}

async function resultJson(page) {
  const text = (await page.locator("#result").textContent()) || "{}";
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
