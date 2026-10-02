// Shared across all pages: formatting helpers, the buy/sell calculation, and the sidebar nav.
const $ = s => document.querySelector(s);
const getPf = () => new URLSearchParams(location.search).get('pf') || 'default';
const pfQS = () => '?pf=' + encodeURIComponent(getPf());
const apiURL = path => path + (path.includes('?') ? '&' : '?') + 'pf=' + encodeURIComponent(getPf());
const n2 = v => isFinite(v) ? v.toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2}) : '–';
const cls = v => v < 0 ? 'neg' : v > 0 ? 'pos' : '';
const esc = v => String(v ?? '').replace(/"/g, '&quot;').replace(/</g, '&lt;');
const pct = v => isFinite(v) ? (v * 100).toFixed(2) + '%' : '–';
const rnd = v => Math.round(v * 1000) / 1000;
const today = () => new Date().toISOString().slice(0, 10);
const dt = d => d ? new Date(d + 'T00:00:00').toLocaleDateString('en-GB', {day: 'numeric', month: 'short', year: 'numeric'}) : '–';

// Weighted-average cost: a buy raises the average, a sell leaves it unchanged and books realized P&L.
// Returns sells[] (one entry per sell, oldest first) with the average held just before that sell.
function calc(s) {
  const ts = s.txns.map((t, k) => ({...t, k})).sort((a, b) => (a.date || '').localeCompare(b.date || '') || a.k - b.k);
  let q = 0, cost = 0, real = 0, bad = false;
  const sells = [];
  for (const t of ts) {
    const n = Number(t.qty), p = Number(t.price);
    if ((t.type || 'BUY') === 'SELL') {
      if (n > q + 1e-9) bad = true;
      const m = Math.min(n, q), avg = q ? cost / q : 0;
      const profit = (p - avg) * m;
      real += profit; cost -= avg * m; q -= m;
      if (q < 1e-9) { q = 0; cost = 0; }
      sells.push({date: t.date, qty: m, price: p, avg, share: p - avg, profit});
    } else { q += n; cost += n * p; }
  }
  const ltp = Number(s.ltp) || 0, cv = ltp * q, pl = cv - cost;
  const prevClose = s.prevClose != null ? Number(s.prevClose) : null;
  const day = prevClose != null ? { chg: ltp - prevClose, pct: prevClose ? (ltp - prevClose) / prevClose : NaN, value: (ltp - prevClose) * q } : null;
  return {q, inv: cost, avg: q ? cost / q : NaN, cv, pl, real, bad, sells, day, pct: cost ? rnd(pl / cost) : NaN};
}

const save = S => fetch(apiURL('/api/portfolio'), {method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(S)});

// Quantity of a stock held as of a given date, from its buy/sell transactions (no cost tracking).
function qtyOnDate(s, dateStr) {
  return s.txns.filter(t => (t.date || '') <= dateStr)
    .reduce((q, t) => q + ((t.type || 'BUY') === 'SELL' ? -Number(t.qty) : Number(t.qty)), 0);
}

async function doRefresh(statusEl, after) {
  statusEl.textContent = 'Fetching prices…';
  try {
    const d = await (await fetch(apiURL('/api/refresh'), {method: 'POST'})).json();
    statusEl.textContent = d.failed.length ? 'No price for ' + d.failed.join(', ') + '; kept previous values' : 'Prices updated';
    after(d.portfolio);
  } catch { statusEl.textContent = 'Refresh failed. Check the server is running and you are online.'; }
}

// Sidebar: same nav on every page (scoped to the open portfolio via ?pf=), with a
// collapse toggle remembered per browser, and a link back to the portfolio switcher.
const NAV_ITEMS = [
  {href: '/dashboard', label: 'Dashboard', short: 'Dsh'},
  {href: '/pnl', label: 'P&L% view', short: 'P&L'},
  {href: '/booked', label: 'Profit booked', short: 'Bkd'},
  {href: '/returns', label: '1-day returns', short: '1D'},
  {href: '/download', label: 'Download portfolio', short: 'D/L'},
  {href: '/dividend', label: 'Dividend paid', short: 'Div'},
];

function renderNav(active) {
  const nav = document.createElement('nav');
  nav.className = 'side';
  const qs = pfQS();
  nav.innerHTML = '<div class="hd"><b id="navTitle">Portfolio</b><button class="tgl" id="navTgl" title="Minimize" aria-label="Minimize sidebar">≡</button></div>'
    + `<a href="/" data-full="⇆ All portfolios" data-short="⇆">⇆ All portfolios</a>`
    + NAV_ITEMS.map(it => `<a href="${it.href}${qs}"${it.href === active ? ' class="on"' : ''} data-full="${it.label}" data-short="${it.short}">${it.label}</a>`).join('');
  document.body.prepend(nav);
  const collapsed = localStorage.getItem('sidebarCollapsed') === '1';
  const apply = c => {
    nav.classList.toggle('collapsed', c);
    nav.querySelectorAll('a').forEach(a => a.textContent = c ? a.dataset.short : a.dataset.full);
  };
  apply(collapsed);
  $('#navTgl').onclick = () => { const c = !nav.classList.contains('collapsed'); localStorage.setItem('sidebarCollapsed', c ? '1' : '0'); apply(c); };
  fetch('/api/portfolios').then(r => r.json()).then(d => {
    const p = (d.portfolios || []).find(x => x.id === getPf());
    if (p) $('#navTitle').textContent = p.name;
  }).catch(() => {});
}

// Per-section minimize/expand, remembered per browser. Used for the Holdings,
// Transactions and Profit booking cards. A page must expose window.render (and,
// for a card whose body is toggled without a full rebuild, apply isCollapsed()
// itself) so a click anywhere updates the right view.
const isCollapsed = id => localStorage.getItem('cx:' + id) === '1';
const setCollapsed = (id, v) => localStorage.setItem('cx:' + id, v ? '1' : '0');
const collapseBtn = id => `<button class="cbtn" data-collapse="${id}" title="Minimize or expand this section" aria-expanded="${!isCollapsed(id)}">${isCollapsed(id) ? '▸ Expand' : '▾ Minimize'}</button>`;
document.addEventListener('click', e => {
  const b = e.target.closest('[data-collapse]');
  if (!b) return;
  setCollapsed(b.dataset.collapse, !isCollapsed(b.dataset.collapse));
  if (typeof window.render === 'function') window.render();
});

// "Show last N, then N more" pattern used for Transactions and Profit booking.
// state is a plain object the caller owns, e.g. {n: 7}; step defaults to 7.
function pager(state, total, step = 7) {
  if (state.n == null) state.n = step;
  return {
    shown: Math.min(state.n, total),
    hasMore: state.n < total,
    button(id) {
      const left = total - state.n;
      return left > 0 ? `<div class="more"><button id="${id}">Show next ${Math.min(step, left)} (${left} more)</button></div>` : '';
    },
  };
}
