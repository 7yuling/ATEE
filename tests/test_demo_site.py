import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "core-service"))

from atee_core.core import CoreService


def load_demo_module():
    module_path = ROOT / "apps" / "demo-site" / "server.py"
    spec = importlib.util.spec_from_file_location("atee_demo_site_server", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class LocalCoreAdapter:
    def __init__(self, core: CoreService):
        self.core = core

    def check(self, payload):
        return self.core.check(payload, remote_addr=payload.get("remote_addr", "127.0.0.1"))

    def event(self, payload):
        return self.core.event(payload, remote_addr=payload.get("remote_addr", "127.0.0.1"))

    def appeal(self, payload):
        return self.core.appeal(payload, remote_addr="127.0.0.1")


class DemoSiteTests(unittest.TestCase):
    def setUp(self):
        self.demo_dir = ROOT / "apps" / "demo-site"
        self.demo_module = load_demo_module()

    def test_demo_assets_are_external_and_plain_text_safe(self):
        html = (self.demo_dir / "index.html").read_text(encoding="utf-8")
        js = (self.demo_dir / "demo.js").read_text(encoding="utf-8")
        self.assertIn('<link rel="stylesheet" href="/demo/styles.css">', html)
        self.assertIn('<script defer src="/demo/demo.js"></script>', html)
        self.assertIn('<img class="brand-mark" src="/assets/flow.svg"', html)
        self.assertNotIn("<style>", html.lower())
        self.assertEqual(html.lower().count("</script>"), 1)
        self.assertIn("textContent", js)
        self.assertNotIn("innerHTML", js)

    def test_demo_login_comment_upload_and_appeal_hit_core(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            core = CoreService(config_path=Path(temp_dir) / "config" / "config.json")
            demo = self.demo_module.DemoBusinessApp(LocalCoreAdapter(core))

            login = demo.login({"username": "alice", "password": "secret"})
            comment = demo.comment({"text": "<script>alert(1)</script>"})
            upload = demo.upload({"filename": "demo.txt", "text": "normal file"})
            appeal = demo.appeal({"punishment_id": "demo-p1", "reason": "please review"})

            self.assertEqual(login["security"]["event_type"], "login")
            self.assertEqual(comment["security"]["route"], "fast_path_block")
            self.assertEqual(upload["security"]["event_type"], "file_upload")
            self.assertEqual(appeal["appeal"]["status"], 202)
            self.assertEqual(core.runtime_status()["pending_appeals"], 1)

    def test_python_adapter_has_appeal_entrypoint(self):
        adapter_path = ROOT / "adapters" / "python-fastapi" / "atee_adapter.py"
        text = adapter_path.read_text(encoding="utf-8")
        self.assertIn("def appeal", text)
        self.assertIn('"/v1/appeal"', text)

    def test_demo_server_has_deployment_overrides_and_core_error_response(self):
        source = (self.demo_dir / "server.py").read_text(encoding="utf-8")

        self.assertIn("ATEE_CORE_URL", source)
        self.assertIn("ATEE_DEMO_PORT", source)
        self.assertIn("core_request_failed", source)
        self.assertIn("could not bind", source)


if __name__ == "__main__":
    unittest.main()
