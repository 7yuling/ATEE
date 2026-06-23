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
const menuKeys = [
  "dashboard",
  "activity",
  "agent",
  "guide",
  "admins",
  "apiKeys",
  "appeals",
  "asyncReviews",
  "actions",
  "ledger",
  "config",
];

const port = await freePort();
const tempDir = await mkdtemp(path.join(tmpdir(), "atee-browser-e2e-"));
const checks = [];
const recentRequests = [];
let server;
let browser;
let serverStderr = "";

try {
  server = startCore(port, tempDir);
  server.stderr?.on("data", (chunk) => {
    serverStderr += chunk.toString();
  });
  await waitForHealth(port);

  browser = await chromium.launch({
    executablePath: chromePath,
    headless: true,
  });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const consoleErrors = [];
  const pageErrors = [];
  page.on("console", (message) => {
    if (message.type() === "error") {
      consoleErrors.push(message.text());
    }
  });
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.pathname.startsWith("/v1/")) {
      recentRequests.push(`${request.method()} ${url.pathname}${url.search}`);
      if (recentRequests.length > 30) {
        recentRequests.shift();
      }
    }
  });

  await page.goto(`http://127.0.0.1:${port}/`, { waitUntil: "domcontentloaded" });
  await expectNewConsoleConnected(page);
  mark("new_console_connected");

  await openMenu(page, "activity");
  await expectOne(page, "#testSafeBtn");
  await expectOne(page, "#testAttackBtn");
  await expectOne(page, "#testAppealBtn");
  await expectOne(page, "#testLlmBtn");
  await expectOne(page, "#refreshBtn");
  await expectOne(page, "#observeBtn");
  await expectOne(page, "#pauseBtn");
  await expectText(page, "/v1/check");
  mark("activity_module_connected");

  await openDetails(page, ".admin-auth-drawer");
  await expectOne(page, "#loadCaptchaBtn");
  await expectOne(page, "#adminLoginBtn");
  await clickAndWaitJson(
    page,
    "#loadCaptchaBtn",
    "/v1/auth/captcha",
    "GET",
    (data) => data.ok === true && Boolean(data.captcha_id) && Boolean(data.question),
    "admin captcha button should load a captcha",
  );
  mark("admin_captcha_button");

  await openDetails(page, ".legacy-token-panel");
  await page.locator("#adminIdInput").fill("browser-e2e-admin");
  await page.locator("#adminTokenInput").fill("browser-e2e-token");
  await click(page, "#saveAdminTokenBtn");
  await expectResult(
    page,
    (data) => data.ok === true && data.admin_token_saved === true && data.admin_actor_saved === true,
    "local admin token should be saved",
  );
  mark("admin_token_save_button");

  await click(page, "#clearAdminTokenBtn");
  await expectResult(
    page,
    (data) => data.ok === true && data.admin_token_saved === false && data.admin_actor_saved === false,
    "local admin token should be cleared",
  );
  mark("admin_token_clear_button");

  await clickAndWaitJson(
    page,
    "#refreshBtn",
    "/v1/runtime/status",
    "GET",
    (data) => data.config && data.llm_gateway,
    "runtime refresh should reload status",
  );
  mark("runtime_refresh_button");

  await clickAndWaitJson(
    page,
    "#observeBtn",
    "/v1/admin/mode",
    "POST",
    (data) => data.ok === true && data.mode === "observe",
    "observe mode button should switch to observe",
  );
  mark("observe_mode_button");

  await clickAndWaitJson(
    page,
    "#pauseBtn",
    "/v1/admin/pause-agent",
    "POST",
    (data) => data.ok === true && data.agent_paused === true,
    "pause button should pause the agent",
  );
  mark("pause_agent_button");

  await clickAndWaitJson(
    page,
    "#pauseBtn",
    "/v1/admin/pause-agent",
    "POST",
    (data) => data.ok === true && data.agent_paused === false,
    "resume button should resume the agent",
  );
  mark("resume_agent_button");

  await clickAndWaitJson(
    page,
    "#testSafeBtn",
    "/v1/check",
    "POST",
    (data) => data.route?.route === "skip",
    "safe request should skip",
  );
  mark("safe_request_button");

  await clickAndWaitJson(
    page,
    "#testAttackBtn",
    "/v1/check",
    "POST",
    (data) => data.route?.route === "fast_path_block",
    "attack should hit fast path",
  );
  mark("attack_button");

  await clickAndWaitJson(
    page,
    "#testAppealBtn",
    "/v1/appeal",
    "POST",
    (data) => data.status === 202,
    "appeal should be accepted",
  );
  mark("appeal_create_button");

  await clickAndWaitJson(
    page,
    "#testLlmBtn",
    "/v1/admin/llm/test",
    "GET",
    (data) => data.ok === true,
    "LLM gateway test should run from activity module",
  );
  mark("activity_llm_button");

  const asyncSource = await postJson(page, "/v1/check", {
    method: "POST",
    path: "/comment",
    event_type: "comment_create",
    feature_scope: "comments",
    user_id: "browser-async-run-user",
    body: { text: "browser e2e async review comment" },
    remote_addr: "198.51.100.10",
  });
  if (asyncSource.route?.route !== "async_agent" || asyncSource.llm_gateway?.reason !== "async_review_queued") {
    throw new Error(`async source request was not queued: ${JSON.stringify(asyncSource)}`);
  }
  mark("async_source_queued");

  const manualAsyncSource = await postJson(page, "/v1/check", {
    method: "POST",
    path: "/comment",
    event_type: "comment_create",
    feature_scope: "comments",
    user_id: "browser-manual-review-user",
    body: { text: "browser e2e manual review candidate" },
    remote_addr: "198.51.100.11",
  });
  if (manualAsyncSource.route?.route !== "async_agent" || manualAsyncSource.llm_gateway?.reason !== "async_review_queued") {
    throw new Error(`manual async source request was not queued: ${JSON.stringify(manualAsyncSource)}`);
  }
  mark("manual_async_source_queued");

  await openMenu(page, "asyncReviews");
  await expectOne(page, "#asyncReviewsBtn");
  await expectOne(page, "#runAsyncReviewsBtn");
  await expectOne(page, "#manualFeatureBanBtn");
  mark("async_reviews_module_connected");

  const pendingReviews = await clickAndWaitJson(
    page,
    "#asyncReviewsBtn",
    "/v1/admin/async-reviews",
    "GET",
    (data) => Array.isArray(data.jobs) && data.count >= 2,
    "async AI review queue should list pending jobs",
  );
  mark("async_reviews_list_button");

  const manualJob = pendingReviews.jobs.find((job) => job.id && job.user_hash && (job.feature_scope || job.event_type));
  if (!manualJob) {
    throw new Error(`manual async review job was not found: ${JSON.stringify(pendingReviews)}`);
  }
  await page.locator("#manualReviewJobIdInput").fill(String(manualJob.id));
  await page.locator("#manualReviewUserHashInput").fill(manualJob.user_hash);
  await page.locator("#manualReviewFeatureInput").fill(manualJob.feature_scope || manualJob.event_type);
  await page.locator("#manualReviewDurationInput").fill("3600");
  await page.locator("#manualReviewNoteInput").fill("browser e2e manual action");
  await confirmButtonAndWaitJson(
    page,
    "#manualFeatureBanBtn",
    "/v1/admin/async-reviews/manual-action",
    "POST",
    (data) => data.ok === true && data.job?.status === "completed" && data.action_result?.record?.action === "feature_ban",
    "manual async review action should complete a job and record a feature ban",
  );
  mark("manual_async_review_button");

  await clickAndWaitJson(
    page,
    "#runAsyncReviewsBtn",
    "/v1/admin/async-reviews/run",
    "POST",
    (data) => data.ok === true && data.claimed >= 1,
    "async review run should process due jobs",
  );
  mark("async_reviews_run_button");

  await openMenu(page, "agent");
  await expectOne(page, "#siteTypeSelect");
  await expectOne(page, "#adapterTypeSelect");
  await expectOne(page, "#agentChatInput");
  await expectOne(page, "#agentChatSendBtn");
  mark("agent_module_connected");

  await page.locator("#agentChatInput").fill("How should I launch in observe mode first?");
  await clickAndWaitJson(
    page,
    "#agentChatSendBtn",
    "/v1/admin/agent/chat",
    "POST",
    (data) => data.reason === "mock_chat" || Boolean(data.reply_zh),
    "agent chat should respond in mock mode",
  );
  mark("agent_chat_button");

  await openMenu(page, "guide");
  await expectOne(page, "#guideSiteTypeSelect");
  await expectOne(page, "#guideAdapterTypeSelect");
  await expectOne(page, "#preflightBtn");
  await expectOne(page, "#securityFlowBtn");
  mark("guide_module_connected");

  await clickAndWaitJson(
    page,
    "#preflightBtn",
    "/v1/admin/preflight",
    "GET",
    (data) => Array.isArray(data.checks),
    "preflight checks should run from guide",
  );
  mark("guide_preflight_button");

  await clickAndWaitJson(
    page,
    "#securityFlowBtn",
    "/v1/admin/security-flow/run",
    "POST",
    (data) => Array.isArray(data.flow_steps) && data.flow_steps.length >= 7,
    "security flow rehearsal should run from guide",
  );
  await expectOne(page, "#securityFlowResultList");
  mark("guide_security_flow_button");

  await expectOne(page, "#integrationSiteNameInput");
  await expectOne(page, "#integrationSiteUrlInput");
  await expectOne(page, "#integrationCoreUrlInput");
  await expectOne(page, "#integrationAppealPathInput");
  await expectOne(page, "#integrationProtectedFeaturesInput");
  await expectOne(page, "#integrationPlanBtn");
  await page.locator("#integrationSiteNameInput").fill("browser-target");
  await page.locator("#integrationSiteUrlInput").fill("https://browser-target.example");
  await page.locator("#integrationCoreUrlInput").fill(`http://127.0.0.1:${port}`);
  await page.locator("#integrationAppealPathInput").fill("/security/appeal");
  await page.locator("#integrationProtectedFeaturesInput").fill("comments\nuploads");
  await clickAndWaitJson(
    page,
    "#integrationPlanBtn",
    "/v1/admin/integration/plan",
    "POST",
    (data) => data.ok === true && data.endpoint_mappings?.length === 4,
    "HTTP API integration plan should be generated from guide",
  );
  await expectOne(page, "#integrationPlanResult");
  await expectText(page, "/v1/check");
  await expectText(page, "/v1/event");
  await expectText(page, "/v1/feature-access");
  await expectText(page, "/v1/appeal");
  mark("guide_integration_plan_button");

  await clickGuideAction(page, "site_type");
  await expectActiveMenu(page, "agent");
  await expectValue(
    page,
    "#agentChatInput",
    (value) => value.includes("ATEE") && value.length > 10,
    "guide site type action should prefill an Agent question",
  );
  mark("guide_action_prefill");

  await openMenu(page, "admins");
  await expectOne(page, "#adminAccountsBtn");
  await expectOne(page, "#createAdminAccountBtn");
  await expectOne(page, "#changeAdminPasswordBtn");
  mark("admin_accounts_module_connected");

  await clickAndWaitJson(
    page,
    "#adminAccountsBtn",
    "/v1/admin/accounts",
    "GET",
    (data) => data.ok === true && Array.isArray(data.admins),
    "admin accounts should be listed",
  );
  mark("admin_accounts_list_button");

  await page.locator("#newAdminUsernameInput").fill("browser_admin");
  await page.locator("#newAdminPasswordInput").fill("browser-admin-pass-1");
  await clickAndWaitJson(
    page,
    "#createAdminAccountBtn",
    "/v1/admin/accounts",
    "POST",
    (data) => data.ok === true && data.username === "browser_admin",
    "admin account should be created",
  );
  mark("admin_account_create_button");

  await page.locator("#passwordAdminUsernameInput").fill("browser_admin");
  await page.locator("#oldAdminPasswordInput").fill("browser-admin-pass-1");
  await page.locator("#changedAdminPasswordInput").fill("browser-admin-pass-2");
  await clickAndWaitJson(
    page,
    "#changeAdminPasswordBtn",
    "/v1/admin/accounts/password",
    "POST",
    (data) => data.ok === true && data.username === "browser_admin",
    "admin account password should be changed",
  );
  mark("admin_password_change_button");

  await openMenu(page, "apiKeys");
  await expectOne(page, "#apiKeysBtn");
  await expectOne(page, "#createApiKeyBtn");
  mark("api_keys_module_connected");

  await clickAndWaitJson(
    page,
    "#apiKeysBtn",
    "/v1/admin/api-keys",
    "GET",
    (data) => data.ok === true && Array.isArray(data.keys),
    "API keys should be listed",
  );
  mark("api_keys_list_button");

  await page.locator("#apiKeyNameInput").fill("browser-e2e-key");
  await page.locator("#apiKeyEnvInput").fill("ATEE_BROWSER_E2E_KEY");
  await page.locator("#apiKeyValueInput").fill("browser-e2e-key-value-123456");
  const createdApiKey = await clickAndWaitJson(
    page,
    "#createApiKeyBtn",
    "/v1/admin/api-keys",
    "POST",
    (data) => data.ok === true && data.record?.id && data.key,
    "API key should be created",
  );
  const apiKeyId = createdApiKey.record.id;
  mark("api_key_create_button");

  await expectOne(page, "#clearCreatedApiKeyBtn");
  await click(page, "#clearCreatedApiKeyBtn");
  await page.locator("#clearCreatedApiKeyBtn").waitFor({ state: "detached", timeout: 5000 });
  mark("api_key_clear_secret_button");

  await expectOne(page, `#deleteApiKey-${apiKeyId}`);
  await confirmButtonAndWaitJson(
    page,
    `#deleteApiKey-${apiKeyId}`,
    `/v1/admin/api-keys/${apiKeyId}`,
    "DELETE",
    (data) => data.ok === true && data.id === apiKeyId,
    "API key should be deleted",
  );
  mark("api_key_delete_button");

  await openMenu(page, "appeals");
  await expectOne(page, "#appealsBtn");
  await expectOne(page, "#approveAppealBtn");
  await expectOne(page, "#rejectAppealBtn");
  mark("appeals_module_connected");

  await clickAndWaitJson(
    page,
    "#appealsBtn",
    "/v1/admin/appeals",
    "GET",
    (data) => data.count === 1,
    "pending appeal should be listed",
  );
  mark("appeals_list_button");

  await page.locator("#appealIdInput").fill("demo-punishment");
  await page.locator("#appealNoteInput").fill("browser e2e approved");
  await confirmButtonAndWaitJson(
    page,
    "#approveAppealBtn",
    "/v1/admin/appeals/review",
    "POST",
    (data) => data.ok === true && data.appeal?.status === "approved",
    "appeal should be approved",
  );
  mark("appeal_approve_button");

  const rejectedAppeal = await postJson(page, "/v1/appeal", {
    punishment_id: "browser-reject-punishment",
    reason: "browser e2e reject rehearsal",
  });
  if (rejectedAppeal.status !== 202) {
    throw new Error(`reject rehearsal appeal was not accepted: ${JSON.stringify(rejectedAppeal)}`);
  }
  await clickAndWaitJson(
    page,
    "#appealsBtn",
    "/v1/admin/appeals",
    "GET",
    (data) => data.count === 1,
    "second pending appeal should be listed",
  );
  await page.locator("#appealIdInput").fill("browser-reject-punishment");
  await page.locator("#appealNoteInput").fill("browser e2e rejected");
  await confirmButtonAndWaitJson(
    page,
    "#rejectAppealBtn",
    "/v1/admin/appeals/review",
    "POST",
    (data) => data.ok === true && data.appeal?.status === "rejected",
    "appeal should be rejected",
  );
  mark("appeal_reject_button");

  await openMenu(page, "activity");
  await clickAndWaitJson(
    page,
    "#degradedBtn",
    "/v1/admin/mode",
    "POST",
    (data) => data.ok === true && data.mode === "degraded",
    "runtime mode should switch to degraded",
  );
  mark("degraded_mode_button");

  await clickAndWaitJson(
    page,
    "#readOnlyBtn",
    "/v1/admin/mode",
    "POST",
    (data) => data.ok === true && data.mode === "read_only",
    "runtime mode should switch to read only",
  );
  mark("read_only_mode_button");

  await openMenu(page, "appeals");
  await expectDisabled(page, "#approveAppealBtn", "read-only mode should disable appeal approval");
  await expectDisabled(page, "#rejectAppealBtn", "read-only mode should disable appeal rejection");
  mark("appeal_read_only_guard");

  await openMenu(page, "asyncReviews");
  await expectDisabled(page, "#runAsyncReviewsBtn", "read-only mode should disable async review processing");
  await expectDisabled(page, "#manualFeatureBanBtn", "read-only mode should disable manual async review action");
  mark("async_read_only_guard");

  await openMenu(page, "actions");
  await expectDisabled(page, "#cleanupActionsBtn", "read-only mode should disable action cleanup");
  await expectDisabled(page, "#revokeActionBtn", "read-only mode should disable action revoke");
  mark("actions_read_only_guard");

  await openMenu(page, "config");
  await expectDisabled(page, "#configSaveBtn", "read-only mode should disable config save");
  mark("config_read_only_guard");

  await openMenu(page, "guide");
  await expectDisabled(page, "#securityFlowBtn", "read-only mode should disable security flow rehearsal");
  mark("guide_read_only_guard");

  await openMenu(page, "admins");
  await expectDisabled(page, "#createAdminAccountBtn", "read-only mode should disable admin account creation");
  await expectDisabled(page, "#changeAdminPasswordBtn", "read-only mode should disable admin password change");
  mark("admin_accounts_read_only_guard");

  await openMenu(page, "apiKeys");
  await expectDisabled(page, "#createApiKeyBtn", "read-only mode should disable API key creation");
  mark("api_keys_read_only_guard");

  await openMenu(page, "activity");
  await confirmButtonAndWaitJson(
    page,
    "#autoBtn",
    "/v1/admin/mode",
    "POST",
    (data) => data.ok === true && data.mode === "auto",
    "runtime mode should switch to auto",
  );
  mark("auto_mode_button");

  await openMenu(page, "activity");
  await clickAndWaitJson(
    page,
    "#testAttackBtn",
    "/v1/check",
    "POST",
    (data) => data.action_result?.executed === true,
    "auto mode should execute action",
  );
  mark("auto_attack_executes");

  await openMenu(page, "actions");
  await expectOne(page, "#actionsBtn");
  await expectOne(page, "#cleanupActionsBtn");
  await expectOne(page, "#revokeActionBtn");
  mark("actions_module_connected");

  const actions = await clickAndWaitJson(
    page,
    "#actionsBtn",
    "/v1/admin/actions",
    "GET",
    (data) => Array.isArray(data.actions),
    "actions should be listed",
  );
  const actionId = actions.actions?.[0]?.id;
  if (!actionId) {
    throw new Error("active action id was not found");
  }
  mark("actions_list_button");

  await confirmButtonAndWaitJson(
    page,
    "#cleanupActionsBtn",
    "/v1/admin/actions/cleanup-expired",
    "POST",
    (data) => data.ok === true && typeof data.expired_marked === "number",
    "expired action cleanup should run",
  );
  mark("actions_cleanup_button");

  await page.locator("#actionIdInput").fill(String(actionId));
  await page.locator("#revokeReasonInput").fill("browser e2e revoke");
  await confirmButtonAndWaitJson(
    page,
    "#revokeActionBtn",
    "/v1/admin/actions/revoke",
    "POST",
    (data) => data.ok === true && data.action?.status === "revoked",
    "action should be revoked",
  );
  mark("action_revoke_button");

  await openMenu(page, "ledger");
  await expectOne(page, "#ledgerLimitInput");
  await expectOne(page, "#ledgerBtn");
  mark("ledger_module_connected");

  await page.locator("#ledgerLimitInput").fill("5");
  await clickAndWaitJson(
    page,
    "#ledgerBtn",
    "/v1/admin/ledger/recent",
    "GET",
    (data) => data.ok === true && Array.isArray(data.records),
    "ledger records should be listed as details for the console table",
  );
  await openMenu(page, "activity");
  await expectResult(
    page,
    (data) => typeof data.ledger_count === "number" && !Array.isArray(data.records),
    "activity result should keep ledger details summarized",
  );
  mark("ledger_summary_boundary");

  await openMenu(page, "config");
  await expectOne(page, "#configBtn");
  await expectOne(page, "#configSaveBtn");
  await expectOne(page, "#testLlmConfigBtn");
  await expectOne(page, "#breakGlassBtn");
  mark("config_module_connected");

  await clickAndWaitJson(
    page,
    "#configBtn",
    "/v1/admin/config",
    "GET",
    (data) => data.ok === true && data.config,
    "config should be loaded",
  );
  mark("config_load_button");

  await page.locator("#localPrecheckInput").fill("123");
  await confirmButtonAndWaitJson(
    page,
    "#configSaveBtn",
    "/v1/admin/config",
    "POST",
    (data) => data.ok === true && data.changed?.local_precheck_ms === 123,
    "config should be saved",
  );
  mark("config_save_button");

  await clickAndWaitJson(
    page,
    "#testLlmConfigBtn",
    "/v1/admin/llm/test",
    "GET",
    (data) => data.ok === true,
    "LLM gateway test should run from config module",
  );
  mark("config_llm_button");

  await clickAndWaitJson(
    page,
    "#breakGlassBtn",
    "/v1/admin/break-glass/status",
    "POST",
    (data) => data.valid_for_request === false,
    "break-glass status should be checked",
  );
  mark("break_glass_button");

  if (consoleErrors.length) {
    throw new Error(`browser console errors: ${consoleErrors.join("; ")}`);
  }
  if (pageErrors.length) {
    throw new Error(`browser page errors: ${pageErrors.join("; ")}`);
  }
  mark("browser_error_free");

  console.log(JSON.stringify({ ok: true, port, checks: checks.length, check_names: checks }, null, 2));
} finally {
  if (browser) {
    await browser.close();
  }
  if (server) {
    server.kill();
  }
  await rm(tempDir, { recursive: true, force: true });
}

function mark(name) {
  checks.push(name);
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
  const stderr = serverStderr.trim();
  throw new Error(`Core service did not become healthy: ${lastError}${stderr ? `; stderr=${stderr.slice(-2000)}` : ""}`);
}

async function expectNewConsoleConnected(page) {
  await expectOne(page, "main.gothic-console");
  await expectOne(page, ".gothic-backdrop");
  await expectOne(page, "#runtime");
  await expectOne(page, "#llmState");
  await expectOne(page, "#circuitState");

  for (const key of menuKeys) {
    await expectOne(page, `.gothic-nav [data-menu-id="${key}"]`);
  }

  const assetState = await page.evaluate(() => {
    const shell = document.querySelector("main.gothic-console");
    const shellStyle = shell ? window.getComputedStyle(shell) : null;
    return {
      adminScript: Boolean(document.querySelector('script[src="/admin/admin.js"]')),
      adminStyles: Boolean(document.querySelector('link[href="/admin/styles.css"]')),
      styledShell: Boolean(shellStyle && shellStyle.display !== "inline"),
      styleNonceInstalled: Boolean(window.__ateeStyleNonceInstalled),
      runtimeText: document.querySelector("#runtime")?.textContent?.trim() || "",
    };
  });
  if (!assetState.adminScript || !assetState.adminStyles || !assetState.styledShell || !assetState.styleNonceInstalled || !assetState.runtimeText) {
    throw new Error(`new console assets were not fully connected: ${JSON.stringify(assetState)}`);
  }

  const runtimeStatus = await fetchJson(page, "/v1/runtime/status");
  if (!runtimeStatus.config || !runtimeStatus.llm_gateway || runtimeStatus.llm_gateway.provider !== "mock") {
    throw new Error(`runtime status was not connected to the new console: ${JSON.stringify(runtimeStatus)}`);
  }
}

async function openMenu(page, key) {
  const clicked = await page.evaluate((menuKey) => {
    const item = document.querySelector(`.gothic-nav [data-menu-id="${menuKey}"]`);
    if (!item) {
      return false;
    }
    item.click();
    return true;
  }, key);
  if (!clicked) {
    throw new Error(`menu item was not found: ${key}`);
  }
  await expectActiveMenu(page, key);
}

async function expectActiveMenu(page, key) {
  await page.waitForFunction(
    (menuKey) => document.querySelector("main.gothic-console")?.classList.contains(`active-${menuKey}`),
    key,
    { timeout: 10000 },
  );
  await expectOne(page, `.gothic-workspace-${key}`);
}

async function clickGuideAction(page, actionId) {
  const selector = `#guideAction-${actionId}`;
  if (await isVisible(page, selector)) {
    await click(page, selector);
    return;
  }

  const headers = page.locator(".ant-collapse-header");
  const count = await headers.count();
  for (let index = 0; index < count; index += 1) {
    await headers.nth(index).click();
    try {
      await page.locator(selector).waitFor({ state: "visible", timeout: 1000 });
      await click(page, selector);
      return;
    } catch {
      // Keep walking the accordion until the requested guide action is mounted.
    }
  }
  const diagnostics = await page.evaluate(() => ({
    guideListExists: Boolean(document.querySelector("#guideList")),
    headerCount: document.querySelectorAll(".ant-collapse-header").length,
    mountedGuideActions: Array.from(document.querySelectorAll('[id^="guideAction-"]')).map((element) => element.id),
    guideListText: (document.querySelector(".ant-collapse")?.textContent || "").slice(0, 240),
  }));
  throw new Error(`guide action was not found or visible: ${actionId}; diagnostics=${JSON.stringify(diagnostics)}`);
}

async function openDetails(page, selector) {
  await expectOne(page, selector);
  const details = page.locator(selector);
  if (!await details.evaluate((element) => Boolean(element.open))) {
    await details.locator("summary").first().click({ timeout: 5000 });
  }
  await page.waitForFunction(
    (detailsSelector) => Boolean(document.querySelector(detailsSelector)?.open),
    selector,
    { timeout: 5000 },
  );
}

async function clickAndWaitJson(page, selector, expectedPath, method, predicate, message) {
  await waitForUiIdle(page);
  const responsePromise = waitForJsonResponse(page, expectedPath, method);
  try {
    await click(page, selector);
  } catch (error) {
    await responsePromise.catch(() => {});
    throw error;
  }
  const data = await responsePromise;
  assertPredicate(data, predicate, message);
  await waitForUiIdle(page);
  return data;
}

async function confirmButtonAndWaitJson(page, selector, expectedPath, method, predicate, message) {
  await waitForUiIdle(page);
  await click(page, selector);
  const responsePromise = waitForJsonResponse(page, expectedPath, method);
  await confirmPopconfirm(page);
  const data = await responsePromise;
  assertPredicate(data, predicate, message);
  await waitForUiIdle(page);
  return data;
}

async function waitForJsonResponse(page, expectedPath, method) {
  let response;
  try {
    response = await page.waitForResponse((candidate) => {
      if (method && candidate.request().method() !== method) {
        return false;
      }
      const url = new URL(candidate.url());
      const pathWithQuery = `${url.pathname}${url.search}`;
      return url.pathname === expectedPath || pathWithQuery === expectedPath || pathWithQuery.startsWith(`${expectedPath}?`);
    }, { timeout: 10000 });
  } catch (error) {
    const requestSummary = recentRequests.length ? recentRequests.join(", ") : "none";
    throw new Error(`${method || "*"} ${expectedPath} response was not observed; recent requests: ${requestSummary}; ${error.message}`);
  }
  return response.json();
}

async function waitForUiIdle(page) {
  await page.waitForFunction(
    () => document.querySelectorAll(".ant-btn-loading").length === 0,
    { timeout: 10000 },
  );
}

function assertPredicate(data, predicate, message) {
  if (!predicate(data)) {
    throw new Error(`${message}; response: ${JSON.stringify(data)}`);
  }
}

async function click(page, selector) {
  const locator = page.locator(selector);
  const count = await locator.count();
  if (count !== 1) {
    throw new Error(`${selector} resolved to ${count} elements`);
  }
  try {
    await locator.click({ timeout: 5000 });
  } catch (error) {
    const diagnostics = await clickDiagnostics(page, selector);
    throw new Error(`${selector} click failed: ${error.message}; diagnostics=${JSON.stringify(diagnostics)}`);
  }
}

async function clickDiagnostics(page, selector) {
  return page.evaluate((targetSelector) => {
    function describe(element) {
      if (!element) {
        return null;
      }
      const id = element.id ? `#${element.id}` : "";
      const className = typeof element.className === "string"
        ? `.${element.className.trim().replace(/\s+/g, ".")}`
        : "";
      return `${element.tagName.toLowerCase()}${id}${className}`;
    }

    const element = document.querySelector(targetSelector);
    if (!element) {
      return { found: false };
    }
    const rect = element.getBoundingClientRect();
    const center = {
      x: rect.left + rect.width / 2,
      y: rect.top + rect.height / 2,
    };
    const hit = document.elementFromPoint(center.x, center.y);
    const path = [];
    let current = hit;
    while (current && path.length < 8) {
      path.push(describe(current));
      current = current.parentElement;
    }
    const ancestors = [];
    current = element;
    while (current && ancestors.length < 8) {
      const currentRect = current.getBoundingClientRect();
      const currentStyle = window.getComputedStyle(current);
      ancestors.push({
        element: describe(current),
        pointerEvents: currentStyle.pointerEvents,
        overflow: `${currentStyle.overflowX}/${currentStyle.overflowY}`,
        rect: {
          x: currentRect.x,
          y: currentRect.y,
          width: currentRect.width,
          height: currentRect.height,
        },
        scrollTop: current.scrollTop,
        scrollLeft: current.scrollLeft,
      });
      current = current.parentElement;
    }
    const style = window.getComputedStyle(element);
    return {
      found: true,
      disabled: Boolean(element.disabled),
      pointerEvents: style.pointerEvents,
      visibility: style.visibility,
      display: style.display,
      rect: {
        x: rect.x,
        y: rect.y,
        width: rect.width,
        height: rect.height,
      },
      center,
      viewport: {
        width: window.innerWidth,
        height: window.innerHeight,
        scrollX: window.scrollX,
        scrollY: window.scrollY,
      },
      hit: describe(hit),
      hitPath: path,
      ancestors,
    };
  }, selector);
}

async function confirmPopconfirm(page) {
  const locator = page.locator(".ant-popconfirm-buttons .ant-btn-primary").last();
  await locator.click({ timeout: 5000 });
}

async function postJson(page, requestPath, payload) {
  return page.evaluate(
    async ({ requestPath, payload }) => {
      const response = await fetch(requestPath, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      return response.json();
    },
    { requestPath, payload },
  );
}

async function fetchJson(page, requestPath) {
  return page.evaluate(async (pathToFetch) => {
    const response = await fetch(pathToFetch);
    return response.json();
  }, requestPath);
}

async function expectOne(page, selector) {
  const locator = page.locator(selector);
  await locator.first().waitFor({ state: "attached", timeout: 10000 });
  const count = await locator.count();
  if (count !== 1) {
    throw new Error(`${selector} resolved to ${count} elements`);
  }
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

async function isVisible(page, selector) {
  const locator = page.locator(selector);
  return (await locator.count()) === 1 && await locator.isVisible();
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
