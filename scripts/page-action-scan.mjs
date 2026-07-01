import { access } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";
import { classifyControl as classifyPageControl } from "../apps/page-guard/page-action-classifier.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const args = parseArgs(process.argv.slice(2));

if (args.help || !args.url) {
  console.log(`Usage: node scripts/page-action-scan.mjs --url <url> [--allowed-domain example.com] [--storage-state state.json] [--allow-high-risk-actions]`);
  process.exit(args.help ? 0 : 2);
}

const startUrl = normalizeUrl(args.url);
const startHost = new URL(startUrl).hostname;
const allowedDomains = new Set((args.allowedDomain.length ? args.allowedDomain : [startHost]).map(normalizeDomain));
const maxPages = boundedInt(args.maxPages, 1, 100, 10);
const maxActions = boundedInt(args.maxActions, 1, 1000, 100);
const timeoutMs = boundedInt(args.timeoutMs, 1000, 120000, 30000);
const allowHighRiskActions = Boolean(args.allowHighRiskActions);
const chromePath = await findChrome();

let browser;
try {
  browser = await chromium.launch({
    executablePath: chromePath,
    headless: true,
  });
  const contextOptions = {};
  if (args.storageState) {
    contextOptions.storageState = path.resolve(root, args.storageState);
  }
  const context = await browser.newContext(contextOptions);
  const page = await context.newPage();
  page.setDefaultTimeout(Math.min(timeoutMs, 15000));
  const result = await crawl(page);
  console.log(JSON.stringify(result, null, 2));
} catch (error) {
  console.error(error?.message || String(error));
  process.exitCode = 1;
} finally {
  if (browser) {
    await browser.close();
  }
}

async function crawl(page) {
  const queue = [startUrl];
  const visited = new Set();
  const actions = [];
  const errors = [];

  while (queue.length && visited.size < maxPages && actions.length < maxActions) {
    const url = queue.shift();
    if (!url || visited.has(url) || !isAllowedUrl(url)) {
      continue;
    }
    visited.add(url);
    try {
      await page.goto(url, { waitUntil: "domcontentloaded", timeout: timeoutMs });
      await page.waitForLoadState("networkidle", { timeout: Math.min(timeoutMs, 5000) }).catch(() => {});
      const rawControls = await collectControls(page);
      for (const raw of rawControls) {
        const action = classifyPageControl(raw, page.url());
        actions.push(action);
        if (actions.length >= maxActions) {
          break;
        }
      }
      for (const link of rawControls.filter((item) => item.href).map((item) => normalizeUrl(item.href))) {
        if (!visited.has(link) && isAllowedUrl(link) && queue.length + visited.size < maxPages) {
          queue.push(link);
        }
      }
      if (allowHighRiskActions) {
        await exploreHighRiskControls(page, actions);
      }
    } catch (error) {
      errors.push({ url, error: String(error?.message || error).slice(0, 300) });
    }
  }

  const uniqueActions = dedupeActions(actions).slice(0, maxActions);
  return {
    ok: true,
    status: errors.length && !uniqueActions.length ? "failed" : "completed",
    start_url: startUrl,
    pages_scanned: visited.size,
    actions: uniqueActions,
    errors,
    scanner: {
      allow_high_risk_actions: allowHighRiskActions,
      max_pages: maxPages,
      max_actions: maxActions,
    },
  };
}

async function collectControls(page) {
  return page.evaluate(() => {
    function clean(value, limit = 240) {
      return String(value || "").replace(/\s+/g, " ").trim().slice(0, limit);
    }
    function cssEscape(value) {
      if (window.CSS?.escape) {
        return window.CSS.escape(value);
      }
      return String(value).replace(/[^A-Za-z0-9_-]/g, "\\$&");
    }
    function selectorFor(element) {
      if (element.id) {
        return `#${cssEscape(element.id)}`;
      }
      const parts = [];
      let current = element;
      while (current && current.nodeType === Node.ELEMENT_NODE && parts.length < 5) {
        let part = current.tagName.toLowerCase();
        if (current.id) {
          parts.unshift(`#${cssEscape(current.id)}`);
          break;
        }
        const name = current.getAttribute("name");
        const type = current.getAttribute("type");
        const siblings = Array.from(current.parentElement?.children || []).filter((item) => item.tagName === current.tagName);
        if (name) {
          part += `[name="${cssEscape(name)}"]`;
        } else if (type) {
          part += `[type="${cssEscape(type)}"]`;
        }
        if (siblings.length > 1 && !current.id) {
          part += `:nth-of-type(${siblings.indexOf(current) + 1})`;
        }
        parts.unshift(part);
        current = current.parentElement;
      }
      return parts.join(" > ");
    }
    const nodes = Array.from(document.querySelectorAll([
      "button",
      "a[href]",
      "input",
      "textarea",
      "select",
      "[role='button']",
      "[role='menuitem']",
      "[role='link']",
      "[role='tab']",
      "[onclick]",
    ].join(",")));
    return nodes
      .filter((element) => {
        const style = window.getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        return style.visibility !== "hidden" && style.display !== "none" && rect.width > 0 && rect.height > 0;
      })
      .map((element) => {
        const form = element.closest("form");
        const tagName = element.tagName.toLowerCase();
        const inputType = clean(element.getAttribute("type") || (tagName === "input" ? "text" : ""), 40).toLowerCase();
        const text = clean(element.innerText || element.textContent || element.getAttribute("value") || element.getAttribute("placeholder"));
        return {
          selector: selectorFor(element),
          tag_name: tagName,
          role: clean(element.getAttribute("role"), 80),
          input_type: inputType,
          text,
          aria_label: clean(element.getAttribute("aria-label")),
          title: clean(element.getAttribute("title")),
          id: clean(element.id, 120),
          name: clean(element.getAttribute("name"), 120),
          class_name: clean(element.className, 180),
          href: element.href || "",
          form_method: clean(form?.method, 20).toUpperCase(),
          form_action: form?.action || "",
          aria_haspopup: clean(element.getAttribute("aria-haspopup"), 40),
        };
      });
  });
}

async function exploreHighRiskControls(page, actions) {
  const highRisk = actions.filter((action) => ["high", "critical"].includes(action.risk_level)).slice(0, 20);
  for (const action of highRisk) {
    const beforeUrl = page.url();
    let dialogSeen = false;
    const handler = async (dialog) => {
      dialogSeen = true;
      await dialog.dismiss().catch(() => {});
    };
    page.once("dialog", handler);
    try {
      await page.locator(action.selector).first().click({ timeout: 1500 });
      await page.waitForTimeout(300);
      action.is_dialog_trigger = action.is_dialog_trigger || dialogSeen;
      action.causes_navigation = action.causes_navigation || page.url() !== beforeUrl;
      if (page.url() !== beforeUrl && isAllowedUrl(page.url())) {
        await page.goBack({ waitUntil: "domcontentloaded", timeout: 2000 }).catch(() => {});
      }
    } catch {
      action.metadata = { ...(action.metadata || {}), exploration: "click_failed" };
    }
    page.removeListener("dialog", handler);
  }
}

function dedupeActions(actions) {
  const seen = new Set();
  const output = [];
  for (const action of actions) {
    const key = [
      action.page_url,
      action.action_type,
      action.risk_level,
      action.label,
      normalizeSelector(action.selector),
      action.form_method,
      action.form_action || action.href,
      action.suggested_feature_scope,
    ].map((item) => String(item || "").trim().toLowerCase()).join("|");
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    output.push(action);
  }
  return output;
}

function normalizeSelector(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/\s*>\s*/g, ">")
    .replace(/\s+/g, " ")
    .replace(/:nth-(?:child|of-type)\(\d+\)/g, ":nth(*)");
}

function isAllowedUrl(value) {
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) && allowedDomains.has(normalizeDomain(url.hostname));
  } catch {
    return false;
  }
}

function normalizeUrl(value) {
  const url = new URL(String(value));
  url.hash = "";
  return url.toString();
}

function normalizeDomain(value) {
  return String(value || "").trim().toLowerCase().replace(/^\.+|\.+$/g, "");
}

function boundedInt(value, minimum, maximum, fallback) {
  const parsed = Number.parseInt(String(value || ""), 10);
  if (!Number.isFinite(parsed)) {
    return fallback;
  }
  return Math.max(minimum, Math.min(maximum, parsed));
}

function parseArgs(argv) {
  const parsed = {
    allowedDomain: [],
  };
  for (let index = 0; index < argv.length; index += 1) {
    const item = argv[index];
    if (item === "--help" || item === "-h") {
      parsed.help = true;
    } else if (item === "--allow-high-risk-actions") {
      parsed.allowHighRiskActions = true;
    } else if (item === "--allowed-domain") {
      parsed.allowedDomain.push(argv[++index]);
    } else if (item.startsWith("--")) {
      const key = item.slice(2).replace(/-([a-z])/g, (_, char) => char.toUpperCase());
      parsed[key] = argv[++index];
    }
  }
  return parsed;
}

async function findChrome() {
  const candidates = [
    process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE,
    process.env.CHROME_PATH,
    "C:/Program Files/Google/Chrome/Application/chrome.exe",
    "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
    "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
    "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
  ].filter(Boolean);
  for (const candidate of candidates) {
    try {
      await access(candidate);
      return candidate;
    } catch {
      // Try the next system browser candidate.
    }
  }
  throw new Error("Chrome or Edge executable not found. Set PLAYWRIGHT_CHROMIUM_EXECUTABLE or CHROME_PATH.");
}
