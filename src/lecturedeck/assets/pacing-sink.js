// lecturedeck pacing sink. `lecturedeck serve` injects this only into pages
// opened by a browser on the serving computer; it is never copied into a
// release. The viewer looks it up on every flush and owns all policy; this
// file only carries one segment to <deck>/../__lecturedeck/pacing.
(() => {
  "use strict";
  const unit = document.currentScript?.dataset.unit || null;
  // Playwright and Selenium report navigator.webdriver; automated walks write nothing.
  const inert = navigator.webdriver === true ? "automation" : null;
  const deckPath = /^(\/decks\/[^/]+)?\/webdeck\/$/;
  const endpoint = path => (typeof path === "string" && deckPath.test(path)
    ? new URL("../__lecturedeck/pacing", location.origin + path) : null);
  // Every answer has one shape; status 0 means no request reached the server.
  const answer = fields => ({ok: false, status: 0, error: null, detail: null,
    rev: null, file: null, savedAt: null, ready: false, ...fields});
  const text = value => (typeof value === "string" ? value : null);
  // The server's own limit (pacing.MAX_BODY). It refuses a longer body
  // before reading it and closes the connection, which a browser often
  // reports as a network error for a large upload, so the viewer would
  // retry forever. Answering here gives it the server's final 413.
  const MAX_BODY = 262144;

  async function send(path, kind, body, keepalive) {
    if (inert) return answer({error: inert});
    const url = endpoint(path);
    if (!url) return answer({error: "path"});
    let response;
    try {
      response = await fetch(url, {
        method: "POST", credentials: "same-origin", cache: "no-store",
        keepalive: Boolean(keepalive), body,
        headers: {"Content-Type": "application/json", "X-Lecturedeck-Pacing": kind},
      });
    } catch (_) {
      return answer({error: "network"});
    }
    let data = null;
    try { data = await response.json(); } catch (_) { /* a reply without JSON */ }
    return answer({
      ok: response.ok && data?.ok === true,
      status: response.status,
      error: response.ok ? null : text(data?.error) || `http-${response.status}`,
      detail: text(data?.detail),
      rev: Number.isInteger(data?.rev) ? data.rev : null,
      file: text(data?.file),
      savedAt: text(data?.savedAt),
      ready: data?.ready === true,
    });
  }

  const probe = path => send(path, "probe", "", false);
  const save = (record, {keepalive = false} = {}) => {
    let body;
    try { body = JSON.stringify(record); } catch (_) {
      return Promise.resolve(answer({error: "serialize"}));
    }
    if (!inert && new TextEncoder().encode(body).length > MAX_BODY) {
      return Promise.resolve(answer({status: 413, error: "too-large"}));
    }
    return send(record?.path, "2", body, keepalive);
  };

  window.lecturedeckPacingSink = Object.freeze({version: 1, unit, inert, probe, save});
})();
