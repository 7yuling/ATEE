import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


class DeploymentAssetTests(unittest.TestCase):
    def test_dockerfile_runs_preflight_and_exposes_healthcheck(self):
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

        self.assertIn("ATEE_HOST=0.0.0.0", dockerfile)
        self.assertIn("EXPOSE 8787", dockerfile)
        self.assertIn("HEALTHCHECK", dockerfile)
        self.assertIn("/health", dockerfile)
        self.assertIn("check_config.py", dockerfile)
        self.assertNotIn("config/secrets", dockerfile)

    def test_dockerignore_excludes_local_state_and_secret_sources(self):
        dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")

        for expected in ("config/config.json", "config/secrets/", "data/", "node_modules/", "reports/"):
            self.assertIn(expected, dockerignore)

    def test_compose_uses_named_volumes_for_config_and_data(self):
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

        self.assertIn("atee-config:/app/config", compose)
        self.assertIn("atee-data:/app/data", compose)
        self.assertIn("ATEE_HOST: \"0.0.0.0\"", compose)
        self.assertIn("8787:8787", compose)
        self.assertNotIn("./config:/app/config", compose)

    def test_run_server_reads_bind_address_from_environment(self):
        module_path = ROOT / "services" / "core-service" / "run_server.py"
        sys.path.insert(0, str(ROOT / "services" / "core-service"))
        spec = importlib.util.spec_from_file_location("atee_run_server_for_test", module_path)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)

        with patch.dict(os.environ, {"ATEE_HOST": "0.0.0.0", "ATEE_PORT": "9999"}, clear=False):
            self.assertEqual(module.bind_from_env(), ("0.0.0.0", 9999))
        with patch.dict(os.environ, {"ATEE_PORT": "invalid"}, clear=False):
            self.assertEqual(module.bind_from_env()[1], 8787)

    def test_windows_start_script_runs_preflight_before_server(self):
        script = (ROOT / "scripts" / "windows" / "start-atee-core.ps1").read_text(encoding="utf-8")

        self.assertIn("check_config.py", script)
        self.assertIn("run_server.py", script)
        self.assertLess(script.index("check_config.py"), script.index("run_server.py"))
        self.assertIn("ATEE_HOST", script)
        self.assertIn("ATEE_PORT", script)
        self.assertIn("PYTHONUNBUFFERED", script)
        self.assertIn("atee-server.out.log", script)
        self.assertIn("atee-server.err.log", script)

    def test_windows_scripts_resolve_default_project_root_after_param_binding(self):
        for script_path in (ROOT / "scripts" / "windows").glob("*.ps1"):
            script = script_path.read_text(encoding="utf-8")
            if "ProjectRoot" not in script:
                continue
            self.assertNotIn(
                '[string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\\..")).Path',
                script,
                msg=str(script_path),
            )
            self.assertIn("if (-not $ProjectRoot)", script, msg=str(script_path))

    def test_windows_background_launcher_uses_current_user_preflight_and_pid_file(self):
        script = (ROOT / "scripts" / "windows" / "start-atee-core-background.ps1").read_text(encoding="utf-8")
        stop_script = (ROOT / "scripts" / "windows" / "stop-atee-core-background.ps1").read_text(encoding="utf-8")

        self.assertIn("check_config.py", script)
        self.assertIn("Start-Process", script)
        self.assertIn("Remove-Item Env:PATH", script)
        self.assertIn("atee-server.pid", script)
        self.assertIn("/health", script)
        self.assertIn("ConvertTo-Json", script)
        self.assertIn("Stop-Process", stop_script)
        self.assertIn("atee-server.pid", stop_script)

    def test_frontend_live_rehearsal_applies_adjustable_budget_to_core(self):
        script = (ROOT / "scripts" / "frontend-live-production-rehearsal.mjs").read_text(encoding="utf-8")

        self.assertIn('const budgetCents = nonNegativeIntArg(args, "budget-cents", 1000);', script)
        self.assertIn("await applyRuntimeBudget(corePort);", script)
        self.assertIn("/v1/admin/config", script)
        self.assertIn("llm_daily_budget_cents: budgetCents", script)
        self.assertIn("ATEE_ADMIN_TOKEN", script)
        self.assertIn("remaining !== null && remaining !== undefined", script)
        self.assertNotRegex(script, r"sk-[A-Za-z0-9]")

    def test_windows_install_task_uses_scheduled_task_wrapper(self):
        script = (ROOT / "scripts" / "windows" / "install-atee-task.ps1").read_text(encoding="utf-8")

        self.assertIn("New-ScheduledTaskAction", script)
        self.assertIn("Register-ScheduledTask", script)
        self.assertIn("Start-ScheduledTask", script)
        self.assertIn("start-atee-core.ps1", script)
        self.assertIn("-ExecutionPolicy", script)
        self.assertIn("AtLogOn", script)
        self.assertIn("AtStartup", script)
        self.assertNotIn("config/secrets", script)

    def test_windows_uninstall_task_stops_and_unregisters_task(self):
        script = (ROOT / "scripts" / "windows" / "uninstall-atee-task.ps1").read_text(encoding="utf-8")

        self.assertIn("Get-ScheduledTask", script)
        self.assertIn("Stop-ScheduledTask", script)
        self.assertIn("Unregister-ScheduledTask", script)
        self.assertIn("Confirm:$false", script)

    def test_winsw_install_script_wraps_existing_start_script_without_downloading_binary(self):
        script = (ROOT / "scripts" / "windows" / "install-atee-winsw.ps1").read_text(encoding="utf-8")

        self.assertIn("WinswExePath", script)
        self.assertIn("Copy-Item", script)
        self.assertIn("start-atee-core.ps1", script)
        self.assertIn("roll-by-size", script)
        self.assertIn("10 sec", script)
        self.assertIn("& $WrapperExe install", script)
        self.assertIn("& $WrapperExe start", script)
        self.assertNotIn("Invoke-WebRequest", script)
        self.assertNotIn("config/secrets", script)

    def test_winsw_uninstall_script_uses_wrapper_stop_and_uninstall(self):
        script = (ROOT / "scripts" / "windows" / "uninstall-atee-winsw.ps1").read_text(encoding="utf-8")

        self.assertIn("& $WrapperExe stop", script)
        self.assertIn("& $WrapperExe uninstall", script)
        self.assertIn("RemoveFiles", script)
        self.assertIn("Remove-Item", script)

    def test_gitignore_excludes_generated_windows_service_runtime(self):
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

        self.assertIn("runtime/", gitignore)
        self.assertIn("logs/", gitignore)
        self.assertIn("backups/", gitignore)

    def test_backup_script_excludes_secrets_and_includes_config_and_sqlite(self):
        script = (ROOT / "scripts" / "windows" / "backup-atee-state.ps1").read_text(encoding="utf-8")

        self.assertIn("Compress-Archive", script)
        self.assertIn("manifest.json", script)
        self.assertIn("config\\config.json", script)
        self.assertIn("atee_ledger.sqlite3", script)
        self.assertIn("atee_ledger.sqlite3-wal", script)
        self.assertIn("config/secrets", script)
        self.assertIn("Secrets are intentionally excluded", script)
        self.assertNotIn("config\\secrets", script)

    def test_restore_script_requires_force_and_refuses_secret_archives(self):
        script = (ROOT / "scripts" / "windows" / "restore-atee-state.ps1").read_text(encoding="utf-8")

        self.assertIn("Expand-Archive", script)
        self.assertIn("Re-run with -Force", script)
        self.assertIn("existing ATEE installation directory", script)
        self.assertIn("config\\secrets", script)
        self.assertIn("refusing to restore", script)
        self.assertIn("config\\config.json", script)
        self.assertIn("data", script)

    def test_log_rotation_script_rolls_large_logs_and_keeps_recent_archives(self):
        script = (ROOT / "scripts" / "windows" / "rotate-atee-logs.ps1").read_text(encoding="utf-8")

        self.assertIn("MaxBytes", script)
        self.assertIn("KeepFiles", script)
        self.assertIn("Move-Item", script)
        self.assertIn("Select-Object -Skip $KeepFiles", script)
        self.assertIn("Remove-Item -Force", script)

    def test_dockerignore_excludes_backups(self):
        dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")

        self.assertIn("backups/", dockerignore)

    def test_linux_start_script_runs_preflight_before_server(self):
        script = (ROOT / "scripts" / "linux" / "start-atee-core.sh").read_text(encoding="utf-8")

        self.assertIn("check_config.py", script)
        self.assertIn("run_server.py", script)
        self.assertLess(script.index("check_config.py"), script.index("run_server.py"))
        self.assertIn("ATEE_HOST", script)
        self.assertIn("ATEE_PORT", script)
        self.assertIn("PYTHONUNBUFFERED", script)
        self.assertIn("atee-preflight.log", script)
        self.assertIn("exec \"$PYTHON_BIN\"", script)

    def test_linux_systemd_installer_defaults_to_user_service_and_preflight_wrapper(self):
        script = (ROOT / "scripts" / "linux" / "install-atee-systemd.sh").read_text(encoding="utf-8")

        self.assertIn('MODE="user"', script)
        self.assertIn("systemctl --user", script)
        self.assertIn("multi-user.target", script)
        self.assertIn("start-atee-core.sh", script)
        self.assertIn("EnvironmentFile=-", script)
        self.assertIn("ExecStart=", script)
        self.assertIn("ExecStart=/usr/bin/env sh", script)
        self.assertIn("Environment=ATEE_ENV_FILE=", script)
        self.assertIn("systemd_unit_value", script)
        self.assertIn('value=${value//%/%%}', script)
        self.assertIn('CONFIG_FILE="$PROJECT_ROOT/config/config.json"', script)
        self.assertIn("cp config/config.example.json config/config.json", script)
        self.assertLess(script.index('CONFIG_FILE="$PROJECT_ROOT/config/config.json"'), script.index("systemctl --user"))
        self.assertNotIn('ExecStart=$(systemd_escape "$START_SCRIPT")', script)
        self.assertNotIn('EnvironmentFile=-$(systemd_escape "$ENV_FILE")', script)
        self.assertIn("NoNewPrivileges=true", script)
        self.assertIn("--system mode requires --run-user", script)
        self.assertNotIn("config/secrets", script)
        self.assertNotRegex(script, r"sk-[A-Za-z0-9]")

    def test_linux_systemd_uninstaller_preserves_env_by_default(self):
        script = (ROOT / "scripts" / "linux" / "uninstall-atee-systemd.sh").read_text(encoding="utf-8")

        self.assertIn("systemctl --user", script)
        self.assertIn("disable --now", script)
        self.assertIn("REMOVE_ENV=0", script)
        self.assertIn("--remove-env", script)
        self.assertIn("daemon-reload", script)

    def test_linux_start_script_preflights_port_before_config(self):
        script = (ROOT / "scripts" / "linux" / "start-atee-core.sh").read_text(encoding="utf-8")

        self.assertIn("ATEE port preflight failed", script)
        self.assertIn("atee-port-preflight.log", script)
        self.assertLess(script.index("atee-port-preflight.log"), script.index("check_config.py"))

    def test_linux_env_example_uses_placeholders_only(self):
        env_example = (ROOT / "scripts" / "linux" / "atee-core.env.example").read_text(encoding="utf-8")
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

        self.assertIn("ATEE_LLM_API_KEY", env_example)
        self.assertIn("ATEE_ADMIN_TOKEN", env_example)
        self.assertIn("Do not commit real secrets", env_example)
        self.assertNotRegex(env_example, r"sk-[A-Za-z0-9]")
        self.assertIn("*.env", gitignore)
        self.assertIn("!*.env.example", gitignore)

    def test_config_preflight_secret_errors_are_cross_platform(self):
        script = (ROOT / "services" / "core-service" / "check_config.py").read_text(encoding="utf-8")

        self.assertIn("OS/user context", script)
        self.assertIn("llm_api_key_env from the service environment or secret manager", script)
        self.assertIn("admin_token_env from the service environment or secret manager", script)
        self.assertNotIn("cannot be decrypted in this Windows user context", script)

    def test_wsl_systemd_nginx_smoke_installs_tests_and_cleans_up(self):
        script = (ROOT / "scripts" / "linux" / "wsl-systemd-nginx-smoke.sh").read_text(encoding="utf-8")

        self.assertIn("install-atee-systemd.sh", script)
        self.assertIn("systemctl --user start", script)
        self.assertIn("production-smoke-check.py", script)
        self.assertIn("nginx -t", script)
        self.assertIn("proxy_pass http://127.0.0.1:${CORE_PORT}", script)
        self.assertIn("trap cleanup EXIT", script)
        self.assertIn("systemctl --user stop", script)
        self.assertIn("rm -f \"$NGINX_CONF\"", script)
        self.assertIn("rm -f \"${XDG_CONFIG_HOME:-$HOME/.config}/atee/${SERVICE_NAME}.env\"", script)
        self.assertNotRegex(script, r"sk-[A-Za-z0-9]")

    def test_ci_and_git_hook_quality_gates_exist(self):
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        hook = (ROOT / ".githooks" / "pre-push").read_text(encoding="utf-8")

        for text in (workflow, hook):
            self.assertIn("unittest", text)
            self.assertIn("build:admin", text)
            self.assertNotRegex(text, r"sk-[A-Za-z0-9]")
            self.assertNotIn(("api" + ".deepseek" + ".com"), text)
        self.assertIn("local-release-gate.py --quick", workflow)
        self.assertIn("python scripts/ci-whitespace-check.py", workflow)
        self.assertIn("git diff --check", hook)
        self.assertIn("node-version: \"22.12.0\"", workflow)
        self.assertIn("python-version: \"3.12\"", workflow)
        self.assertIn("Browser E2E", workflow)

        checker = (ROOT / "scripts" / "ci-whitespace-check.py").read_text(encoding="utf-8")
        self.assertIn("\"ls-tree\"", checker)
        self.assertIn("HEAD:", checker)
        self.assertNotRegex(checker, r"sk-[A-Za-z0-9]")

    def test_reverse_proxy_examples_use_local_upstream_and_security_headers(self):
        nginx = (ROOT / "deploy" / "reverse-proxy" / "nginx" / "atee.conf.example").read_text(encoding="utf-8")
        demo_nginx = (ROOT / "deploy" / "reverse-proxy" / "nginx" / "atee-demo.conf.example").read_text(encoding="utf-8")
        caddy = (ROOT / "deploy" / "reverse-proxy" / "caddy" / "Caddyfile.example").read_text(encoding="utf-8")

        for config in (nginx, caddy):
            self.assertIn("127.0.0.1:8787", config)
            self.assertIn("Strict-Transport-Security", config)
            self.assertIn("X-Content-Type-Options", config)
            self.assertIn("Referrer-Policy", config)
            self.assertIn("X-Forwarded-Proto", config)
            self.assertIn("X-Real-IP", config)
            self.assertNotIn("Access-Control-Allow-Origin *", config)
            self.assertNotIn(("api" + ".deepseek" + ".com"), config)
            self.assertNotRegex(config, r"sk-[A-Za-z0-9]")
        self.assertIn("large_client_header_buffers 4 16k", nginx)
        self.assertIn('proxy_set_header Cookie ""', nginx)
        self.assertIn("proxy_pass http://127.0.0.1:8787", nginx)
        self.assertIn("reverse_proxy 127.0.0.1:8787", caddy)
        self.assertIn("listen 8790", demo_nginx)
        self.assertIn("proxy_pass http://127.0.0.1:8791", demo_nginx)
        self.assertIn("large_client_header_buffers 4 16k", demo_nginx)
        self.assertIn('proxy_set_header Cookie ""', demo_nginx)
        self.assertNotRegex(demo_nginx, r"sk-[A-Za-z0-9]")

    def test_sso_reverse_proxy_examples_inject_admin_identity_from_auth_layer(self):
        nginx = (ROOT / "deploy" / "reverse-proxy" / "nginx" / "atee-sso.conf.example").read_text(encoding="utf-8")
        caddy = (ROOT / "deploy" / "reverse-proxy" / "caddy" / "Caddyfile.sso.example").read_text(encoding="utf-8")

        for config in (nginx, caddy):
            self.assertIn("127.0.0.1:8787", config)
            self.assertIn("127.0.0.1:4180", config)
            self.assertIn("X-ATEE-Admin-Id", config)
            self.assertIn("X-Real-IP", config)
            self.assertIn("Strict-Transport-Security", config)
            self.assertNotIn("$http_x_atee_admin_id", config)
            self.assertNotIn(("api" + ".deepseek" + ".com"), config)
            self.assertNotRegex(config, r"sk-[A-Za-z0-9]")
        self.assertIn("auth_request /oauth2/auth", nginx)
        self.assertIn("auth_request_set $atee_admin_id $upstream_http_x_auth_request_email", nginx)
        self.assertIn("proxy_set_header X-ATEE-Admin-Id $atee_admin_id", nginx)
        self.assertIn("request_header -X-ATEE-Admin-Id", caddy)
        self.assertIn("forward_auth 127.0.0.1:4180", caddy)
        self.assertIn("copy_headers X-Auth-Request-Email>X-ATEE-Admin-Id", caddy)

    def test_rotate_admin_token_updates_env_file_without_printing_token_by_default(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_file = Path(temp_dir) / "atee-core.env"
            env_file.write_text(
                "ATEE_LLM_API_KEY=placeholder\n#ATEE_ADMIN_TOKEN=old-token\n",
                encoding="utf-8",
            )
            script = ROOT / "scripts" / "rotate-admin-token.py"

            completed = subprocess.run(
                [sys.executable, str(script), "--env-file", str(env_file), "--json"],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            payload = json.loads(completed.stdout)
            env_text = env_file.read_text(encoding="utf-8")
            token_line = next(line for line in env_text.splitlines() if line.startswith("ATEE_ADMIN_TOKEN="))
            token = token_line.split("=", 1)[1]

            self.assertTrue(payload["ok"])
            self.assertEqual(payload["env_name"], "ATEE_ADMIN_TOKEN")
            self.assertIn("token_fingerprint", payload)
            self.assertNotIn("token", payload)
            self.assertNotIn(token, completed.stdout)
            self.assertGreaterEqual(len(token), 32)
            self.assertIn("ATEE_LLM_API_KEY=placeholder", env_text)
            self.assertEqual(env_text.count("ATEE_ADMIN_TOKEN="), 1)


if __name__ == "__main__":
    unittest.main()
