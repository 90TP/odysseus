// Send browser-side JavaScript errors to Aerith (companion/maintenance), so
// she can see and fix front-end bugs as well as server ones.
// Quiet by design: batched, deduplicated, capped per page load, and switched
// off for the rest of the page if Aerith maintenance isn't enabled.

const ENDPOINT = '/api/companion/aerith/maintenance/logs';
const MAX_PER_PAGE = 20;
const FLUSH_DELAY_MS = 2000;

const seen = new Set();
let queue = [];
let sent = 0;
let disabled = false;
let timer = null;

function platform() {
  return /Android/i.test(navigator.userAgent || '') ? 'android' : 'desktop';
}

function enqueue(message, detail, source) {
  if (disabled || !message) return;
  // Cross-origin scripts and browser extensions aren't ours to fix.
  if (message === 'Script error.' || /^(chrome|moz|safari)-extension:/.test(source || '')) return;
  const key = `${source}|${message}`.slice(0, 400);
  if (seen.has(key) || sent >= MAX_PER_PAGE) return;
  seen.add(key);
  sent += 1;
  queue.push({
    level: 'ERROR',
    message: String(message).slice(0, 4000),
    detail: String(detail || '').slice(0, 20000),
    source: String(source || 'odysseus-web').slice(0, 200),
    timestamp: new Date().toISOString(),
  });
  if (!timer) timer = setTimeout(flush, FLUSH_DELAY_MS);
}

async function flush() {
  timer = null;
  if (disabled || !queue.length) return;
  const events = queue;
  queue = [];
  try {
    const res = await fetch(ENDPOINT, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        platform: platform(),
        app_id: 'odysseus-web',
        app_version: document.documentElement.dataset.version || '',
        events,
      }),
    });
    // 503: maintenance is off; 401/403: not signed in. Stop trying.
    if ([401, 403, 503].includes(res.status)) disabled = true;
  } catch (_) {
    // Offline or server down; drop these rather than retry forever.
  }
}

window.addEventListener('error', (ev) => {
  if (!ev || !ev.message) return; // resource load errors have no message
  const where = ev.filename ? `${ev.filename.split('?')[0]}:${ev.lineno}:${ev.colno}` : '';
  const stack = (ev.error && ev.error.stack) || '';
  enqueue(ev.message, `${stack}\nat ${where}\npage ${location.pathname}`.trim(), where || 'window');
});

window.addEventListener('unhandledrejection', (ev) => {
  const reason = ev && ev.reason;
  const message = (reason && (reason.message || String(reason))) || 'Unhandled promise rejection';
  enqueue(`Unhandled rejection: ${message}`, `${(reason && reason.stack) || ''}\npage ${location.pathname}`.trim(),
    'unhandledrejection');
});
