import { classifyControl } from "./page-action-classifier.mjs";

const DEFAULT_CONFIG = {
  featureAccessUrl: "/v1/feature-access",
  actionReportUrl: "",
  siteId: null,
  userId: "",
  protectedFeatures: [],
  protectedActionTypes: ["upload"],
  featureMap: {},
  reportActions: false,
  autoStart: true,
};

const state = {
  actions: [],
  blocked: [],
  running: false,
};

export async function startPageGuard(config = {}) {
  const options = normalizeConfig(config);
  if (!options.userId || state.running) {
    return { ok: false, reason: options.userId ? "already_running" : "user_id_required", actions: state.actions };
  }
  state.running = true;
  const actions = scanPageActions();
  state.actions = actions;
  if (options.reportActions && options.actionReportUrl) {
    await postJson(options.actionReportUrl, {
      site_id: options.siteId,
      page_url: globalThis.location?.href || "",
      actions,
    }).catch(() => null);
  }
  for (const action of actions) {
    const featureScope = resolveFeatureScope(action, options);
    if (!featureScope || !shouldGuardAction(action, featureScope, options)) {
      continue;
    }
    const access = await postJson(options.featureAccessUrl, {
      site_id: options.siteId,
      user_id: options.userId,
      feature_scope: featureScope,
    }).catch((error) => ({ ok: false, allowed: true, reason: error.message }));
    if (access.allowed === false) {
      const blocked = blockControl(action, featureScope, access);
      if (blocked) {
        state.blocked.push(blocked);
      }
    }
  }
  state.running = false;
  return { ok: true, actions: state.actions, blocked: state.blocked };
}

export function scanPageActions() {
  return collectControls().map((raw) => classifyControl(raw, globalThis.location?.href || "https://target.example/"));
}

export function pageGuardState() {
  return {
    actions: [...state.actions],
    blocked: [...state.blocked],
    running: state.running,
  };
}

function normalizeConfig(config) {
  const windowConfig = globalThis.ATEE_PAGE_GUARD_CONFIG || {};
  const merged = { ...DEFAULT_CONFIG, ...windowConfig, ...config };
  merged.protectedFeatures = toList(merged.protectedFeatures);
  merged.protectedActionTypes = toList(merged.protectedActionTypes);
  merged.featureMap = typeof merged.featureMap === "object" && merged.featureMap ? merged.featureMap : {};
  return merged;
}

function shouldGuardAction(action, featureScope, options) {
  if (options.protectedActionTypes.includes(action.action_type)) {
    return true;
  }
  if (!options.protectedFeatures.length) {
    return false;
  }
  return options.protectedFeatures.some((feature) => (
    feature === featureScope
    || feature === action.action_type
    || feature === action.suggested_event_type
    || action.suggested_feature_scope.includes(feature)
  ));
}

function resolveFeatureScope(action, options) {
  const mapped = options.featureMap[action.selector] || options.featureMap[action.action_type];
  if (mapped) {
    return String(mapped).trim();
  }
  if (action.action_type === "upload" && options.protectedFeatures.includes("uploads")) {
    return "uploads";
  }
  if (action.suggested_feature_scope.includes("comment") && options.protectedFeatures.includes("comments")) {
    return "comments";
  }
  if (action.suggested_feature_scope.includes("post") && options.protectedFeatures.includes("posts")) {
    return "posts";
  }
  return action.suggested_feature_scope;
}

function blockControl(action, featureScope, access) {
  const element = globalThis.document?.querySelector(action.selector);
  if (!element) {
    return null;
  }
  element.dataset.ateeBlocked = "true";
  element.dataset.ateeFeatureScope = featureScope;
  element.setAttribute("aria-disabled", "true");
  element.classList.add("atee-page-guard-blocked");
  const reason = access.reason || "active_feature_ban";
  element.title = element.title || `Blocked by ATEE: ${reason}`;
  if ("disabled" in element) {
    element.disabled = true;
  }
  const stop = (event) => {
    event.preventDefault();
    event.stopImmediatePropagation();
  };
  element.addEventListener("click", stop, true);
  if (action.submits_form) {
    const form = element.closest("form");
    form?.addEventListener("submit", stop, true);
  }
  return {
    selector: action.selector,
    feature_scope: featureScope,
    reason,
    punishment_id: access.punishment_id || null,
  };
}

function collectControls() {
  if (!globalThis.document) {
    return [];
  }
  function clean(value, limit = 240) {
    return String(value || "").replace(/\s+/g, " ").trim().slice(0, limit);
  }
  function cssEscape(value) {
    if (globalThis.CSS?.escape) {
      return globalThis.CSS.escape(value);
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
  return Array.from(document.querySelectorAll([
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
  ].join(",")))
    .filter((element) => {
      const style = globalThis.getComputedStyle(element);
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
}

function postJson(url, payload) {
  return fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }).then((response) => response.json());
}

function toList(value) {
  if (Array.isArray(value)) {
    return value.map((item) => String(item).trim()).filter(Boolean);
  }
  if (typeof value === "string") {
    return value.split(/[\n,]/).map((item) => item.trim()).filter(Boolean);
  }
  return [];
}

globalThis.ATEEPageGuard = {
  start: startPageGuard,
  scan: scanPageActions,
  state: pageGuardState,
};

if (normalizeConfig().autoStart && globalThis.document) {
  const start = () => startPageGuard().catch(() => null);
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
}
