export function classifyControl(raw, pageUrl) {
  const haystack = [
    raw.text,
    raw.aria_label,
    raw.title,
    raw.id,
    raw.name,
    raw.class_name,
    raw.href,
    raw.input_type,
  ].join(" ").toLowerCase();
  const isPlainFormField = ["input", "textarea", "select"].includes(raw.tag_name)
    && !["submit", "button", "reset", "file", "search", "checkbox", "radio"].includes(raw.input_type);
  const submitsForm = (raw.tag_name === "button" && (!raw.input_type || raw.input_type === "submit"))
    || raw.input_type === "submit";
  let actionType = "unknown";
  if (matchesDeleteIntent(haystack)) {
    actionType = "delete";
  } else if (matches(haystack, ["login", "sign in", "signin", "\u767b\u5f55", "\u767b\u9678"])) {
    actionType = "login";
  } else if (matches(haystack, ["register", "sign up", "signup", "\u6ce8\u518c"])) {
    actionType = "register";
  } else if (matches(haystack, ["search", "find", "query", "\u641c\u7d22", "\u67e5\u8be2"]) || raw.input_type === "search") {
    actionType = "search";
  } else if (matches(haystack, ["save", "update", "\u4fdd\u5b58", "\u66f4\u65b0"])) {
    actionType = "save";
  } else if (matches(haystack, ["upload", "\u4e0a\u4f20"]) || raw.input_type === "file") {
    actionType = "upload";
  } else if (isPlainFormField) {
    actionType = "form_field";
  } else if (matches(haystack, ["next", "prev", "previous", "page=", "\u4e0a\u4e00\u9875", "\u4e0b\u4e00\u9875", "\u5206\u9875"])) {
    actionType = "pagination";
  } else if (raw.aria_haspopup || matches(haystack, ["menu", "dropdown", "\u66f4\u591a", "\u83dc\u5355"])) {
    actionType = "menu";
  } else if (matches(haystack, ["modal", "dialog", "confirm", "\u786e\u8ba4", "\u5f39\u7a97"])) {
    actionType = "dialog_trigger";
  } else if (submitsForm) {
    actionType = "submit";
  } else if (raw.href) {
    actionType = "navigation";
  }
  const riskLevel = riskFor(actionType, haystack);
  return {
    page_url: pageUrl,
    action_type: actionType,
    risk_level: riskLevel,
    label: raw.text || raw.aria_label || raw.title || raw.name || raw.id || raw.href || "unlabeled control",
    selector: raw.selector,
    role: raw.role,
    tag_name: raw.tag_name,
    aria_label: raw.aria_label,
    href: raw.href,
    form_method: raw.form_method,
    form_action: raw.form_action,
    is_dialog_trigger: actionType === "dialog_trigger",
    causes_navigation: actionType === "navigation",
    submits_form: submitsForm,
    suggested_event_type: eventTypeFor(actionType),
    suggested_feature_scope: featureScopeFor(actionType, raw, pageUrl),
    recommended_test_type: ["high", "critical"].includes(riskLevel) ? "approval_regression" : "smoke",
    requires_admin_review: ["high", "critical"].includes(riskLevel),
    metadata: {
      input_type: raw.input_type,
      class_name: raw.class_name,
    },
  };
}

export function eventTypeFor(actionType) {
  if (actionType === "submit") {
    return "form_submit";
  }
  if (actionType === "dialog_confirm") {
    return "confirm_action";
  }
  return actionType;
}

export function riskFor(actionType, text) {
  if (actionType === "delete" || matches(text, ["payment", "pay", "refund", "role", "permission", "\u652f\u4ed8", "\u9000\u6b3e", "\u6743\u9650", "\u7ba1\u7406\u5458"])) {
    return "critical";
  }
  if (["login", "register", "submit", "save", "upload", "dialog_confirm"].includes(actionType)) {
    return "high";
  }
  if (["menu", "pagination", "navigation", "dialog_trigger"].includes(actionType)) {
    return "medium";
  }
  return "low";
}

export function featureScopeFor(actionType, raw, pageUrl) {
  const fallbackUrl = globalThis.window?.location?.href || "https://target.example/";
  const url = new URL(pageUrl, fallbackUrl);
  const basis = `${url.pathname}_${actionType}_${raw.name || raw.id || raw.text || raw.aria_label || "control"}`;
  return basis
    .toLowerCase()
    .replace(/[^a-z0-9\u4e00-\u9fa5]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 120) || actionType;
}

export function matches(text, needles) {
  return needles.some((needle) => text.includes(needle));
}

function matchesDeleteIntent(text) {
  return matches(text, ["delete", "remove", "destroy", "\u5220\u9664", "\u79fb\u9664"]) || /\bdrop\b/.test(text);
}
