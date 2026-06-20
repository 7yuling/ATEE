import unittest
from pathlib import Path


class AdminConsoleTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        self.admin_dir = root / "apps" / "admin-console"
        self.source_dir = root / "apps" / "admin-console-src"

    def test_html_uses_vite_external_assets_for_csp(self):
        html = (self.admin_dir / "index.html").read_text(encoding="utf-8")

        self.assertIn('<meta name="csp-nonce" content="__ATEE_CSP_NONCE__">', html)
        self.assertIn('src="/admin/admin.js"', html)
        self.assertIn('href="/admin/styles.css"', html)
        self.assertIn("ATEE 管理控制台", html)
        self.assertNotIn("<style", html.lower())
        self.assertEqual(html.lower().count("<script "), 1)
        self.assertEqual(html.lower().count("</script>"), 1)

    def test_html_is_not_terminated_by_test_payload(self):
        html = (self.admin_dir / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("<script>alert(1)</script>", html)

    def test_external_assets_exist_and_wire_admin_endpoints(self):
        css = (self.admin_dir / "styles.css").read_text(encoding="utf-8")
        js_files = sorted(self.admin_dir.glob("admin*.js"))
        js = "\n".join(path.read_text(encoding="utf-8") for path in js_files)

        self.assertIn(".atee-shell", css)
        self.assertIn("ant-", css)
        self.assertGreaterEqual(len(js_files), 4)
        self.assertLess(max(path.stat().st_size for path in js_files), 500_000)
        self.assertTrue((self.admin_dir / "admin.js").is_file())
        self.assertTrue(any(path.name.startswith("admin-antd-") for path in js_files))
        self.assertIn("/v1/admin/llm/test", js)
        self.assertIn("/v1/admin/ledger/recent", js)
        self.assertIn("/v1/admin/appeals?status=", js)
        self.assertIn("/v1/admin/actions?status=", js)
        self.assertIn("/v1/admin/actions/revoke", js)
        self.assertIn("/v1/admin/async-reviews?status=", js)
        self.assertIn("/v1/admin/async-reviews/run", js)
        self.assertIn("/v1/admin/config", js)
        self.assertIn("/v1/admin/preflight", js)
        self.assertIn("/v1/admin/security-flow/run", js)
        self.assertIn("/v1/admin/agent/chat", js)
        self.assertIn("/v1/auth/captcha", js)
        self.assertIn("/v1/auth/login", js)
        self.assertIn("/v1/admin/accounts", js)
        self.assertIn("/v1/admin/api-keys", js)
        self.assertIn("<script>alert(1)<\\/script>", js)
        self.assertIn("ATEE 管理控制台", js)

    def test_react_source_keeps_e2e_ids_and_plain_text_rendering(self):
        main_source = (self.source_dir / "src" / "main.jsx").read_text(encoding="utf-8")
        agent_guide_source = (self.source_dir / "src" / "adminAgentGuide.jsx").read_text(encoding="utf-8")
        dashboard_source = (self.source_dir / "src" / "adminDashboard.jsx").read_text(encoding="utf-8")
        gothic_shell_source = (self.source_dir / "src" / "adminGothicShell.jsx").read_text(encoding="utf-8")
        ledger_config_source = (self.source_dir / "src" / "adminLedgerConfig.jsx").read_text(encoding="utf-8")
        review_source = (self.source_dir / "src" / "adminReviewQueues.jsx").read_text(encoding="utf-8")
        access_source = (self.source_dir / "src" / "adminAccess.jsx").read_text(encoding="utf-8")
        support_source = (self.source_dir / "src" / "adminSupport.jsx").read_text(encoding="utf-8")
        source = (
            main_source
            + "\n"
            + agent_guide_source
            + "\n"
            + dashboard_source
            + "\n"
            + gothic_shell_source
            + "\n"
            + ledger_config_source
            + "\n"
            + review_source
            + "\n"
            + access_source
            + "\n"
            + support_source
        )

        for element_id in [
            "appealIdInput",
            "appealNoteInput",
            "appealStatusSelect",
            "approveAppealBtn",
            "rejectAppealBtn",
            "actionIdInput",
            "actionStatusSelect",
            "cleanupActionsBtn",
            "revokeActionBtn",
            "llmState",
            "circuitState",
            "testSafeBtn",
            "testAttackBtn",
            "degradedBtn",
            "readOnlyBtn",
            "operationGuardAlert",
            "adminIdInput",
            "adminTokenInput",
            "adminLoginUsernameInput",
            "adminLoginPasswordInput",
            "adminCaptchaAnswerInput",
            "loadCaptchaBtn",
            "adminLoginBtn",
            "adminRegisterBtn",
            "adminAccountsBtn",
            "newAdminUsernameInput",
            "newAdminPasswordInput",
            "createAdminAccountBtn",
            "changeAdminPasswordBtn",
            "apiKeysBtn",
            "apiKeyNameInput",
            "apiKeyScopeSelect",
            "apiKeyEnvInput",
            "apiKeyValueInput",
            "createApiKeyBtn",
            "saveAdminTokenBtn",
            "clearAdminTokenBtn",
            "adminAuthState",
            "adminAuthAlert",
            "adminAuthSwitch",
            "adminTokenEnvInput",
            "adminTokenFileInput",
            "outputSummary",
            "resultSummary",
            "ledgerLimitInput",
            "configSaveBtn",
            "localeSelect",
            "configModeSelect",
            "agentPausedSwitch",
            "asyncReviewWorkerSwitch",
            "asyncReviewWorkerIntervalInput",
            "asyncReviewWorkerBatchInput",
            "trustedProxyInput",
            "appealPathsInput",
            "llmApiBaseInput",
            "llmApiKeyValueInput",
            "llmProxyUrlInput",
            "bypassKeyFileInput",
            "breakGlassHeaderInput",
            "guideList",
            "agentChatWindow",
            "agentChatInput",
            "agentChatSendBtn",
            "siteTypeSelect",
            "adapterTypeSelect",
            "guideSiteTypeSelect",
            "guideAdapterTypeSelect",
            "preflightBtn",
            "preflightChecks",
            "securityFlowBtn",
            "guideAction-${item.id}",
            "securityFlowList",
            "securityFlowResultList",
            "asyncReviewQueue",
            "asyncReviewStatusSelect",
            "asyncReviewsBtn",
            "runAsyncReviewsBtn",
        ]:
            self.assertIn(element_id, source)
        self.assertIn('from "./adminSupport.jsx"', main_source)
        self.assertLess(len(main_source.splitlines()), 1500)
        self.assertIn("SECRET_JSON_KEYS", source)
        self.assertIn("REDACTED_VALUE", source)
        self.assertIn("new_llm_api_base", source)
        self.assertIn("llm_api_key_value", source)
        self.assertIn("llm_gateway_test", source)
        self.assertIn("llm_api_base_configured", source)
        self.assertIn("llm_api_key_env_configured", source)
        self.assertIn("visibilityToggle={false}", source)
        self.assertNotIn('name="llm_api_base"', source)
        self.assertIn("async function saveConfig()", source)
        self.assertIn("async_review_worker_enabled", source)
        self.assertIn("Popconfirm", source)
        self.assertIn("writeLocked", source)
        self.assertIn("MetricCard", source)
        self.assertIn("InteractiveGothicBackdrop", source)
        self.assertIn("GothicFallbackBackdrop", source)
        self.assertIn("GothicPageFrame", source)
        self.assertIn("gothic-console", source)
        self.assertIn("navCollapseBtn", source)
        self.assertIn("RuntimeSummary", source)
        self.assertIn("OperationSummary", source)
        self.assertIn("PreflightSummary", source)
        self.assertIn("LabelWithHelp", source)
        self.assertIn("SECURITY_FLOW_STEPS", source)
        self.assertIn('response.headers.get("Content-Type")', source)
        self.assertIn("response.statusText", source)
        self.assertIn("配置已接入", source)
        self.assertIn("原始 JSON", source)
        self.assertIn("Authorization = `Bearer ${adminToken}`", source)
        self.assertIn('headers["X-ATEE-Admin-Id"] = adminId', source)
        self.assertIn("atee.adminId", source)
        self.assertIn("atee-admin-auth-required", source)
        self.assertIn("POST\",", source)
        self.assertIn("/v1/admin/config", source)
        self.assertIn("/v1/auth/captcha", source)
        self.assertIn("/v1/auth/login", source)
        self.assertIn("/v1/auth/register", source)
        self.assertIn("/v1/admin/accounts", source)
        self.assertIn("/v1/admin/api-keys", source)
        self.assertIn("details=1", source)
        self.assertIn("installStyleNonce(runtimeCspNonce)", source)
        self.assertIn("csp={{ nonce: runtimeCspNonce }}", source)
        self.assertIn("wave={{ disabled: true }}", source)
        self.assertNotIn("dangerouslySetInnerHTML", source)


if __name__ == "__main__":
    unittest.main()
