import unittest
from pathlib import Path


class AdminConsoleTests(unittest.TestCase):
    def setUp(self):
        self.admin_dir = Path(__file__).resolve().parents[1] / "apps" / "admin-console"

    def test_html_uses_external_assets_for_csp(self):
        html = (self.admin_dir / "index.html").read_text(encoding="utf-8")
        self.assertIn('<link rel="stylesheet" href="/admin/styles.css">', html)
        self.assertIn('<script defer src="/admin/admin.js"></script>', html)
        self.assertNotIn("<style>", html.lower())
        self.assertNotIn("<script>\n", html.lower())

    def test_html_is_not_terminated_by_test_payload(self):
        html = (self.admin_dir / "index.html").read_text(encoding="utf-8")
        self.assertEqual(html.lower().count("</script>"), 1)
        self.assertNotIn("<script>alert(1)</script>", html)

    def test_external_assets_exist(self):
        css = (self.admin_dir / "styles.css").read_text(encoding="utf-8")
        js = (self.admin_dir / "admin.js").read_text(encoding="utf-8")
        self.assertIn("--panel", css)
        self.assertIn("async function refresh()", js)
        self.assertIn("async function showConfig()", js)
        self.assertIn("<script>alert(1)</script>", js)


if __name__ == "__main__":
    unittest.main()
