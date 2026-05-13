export function createAteeAdapter({ coreUrl = "http://127.0.0.1:8787" } = {}) {
  async function post(path, payload) {
    const response = await fetch(`${coreUrl}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    return response.json();
  }

  return {
    async check(req) {
      return post("/v1/check", {
        method: req.method,
        path: req.path || req.url,
        headers: req.headers || {},
        query: req.query || {},
        body: req.body,
        remote_addr: req.ip || req.socket?.remoteAddress
      });
    },
    async event(req, eventType) {
      return post("/v1/event", {
        method: req.method,
        path: req.path || req.url,
        headers: req.headers || {},
        query: req.query || {},
        body: req.body,
        remote_addr: req.ip || req.socket?.remoteAddress,
        event_type: eventType
      });
    }
  };
}

