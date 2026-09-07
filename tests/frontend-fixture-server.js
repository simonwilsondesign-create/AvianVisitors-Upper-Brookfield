/* Local-only browser fixture server for the passive display. */
const http = require('http');
const fs = require('fs');
const path = require('path');
const root = path.resolve(__dirname, '..');
const birds = Array.from({ length: 14 }, (_, i) => ({
  sci: `Fixture bird ${i + 1}`, com: `Fixture Bird ${i + 1}`, n: 14 - i,
}));
let mode = 'normal';
function json(res, body, status = 200) { res.writeHead(status, { 'content-type': 'application/json', 'cache-control': 'no-store' }); res.end(JSON.stringify(body)); }
http.createServer((req, res) => {
  const u = new URL(req.url, 'http://fixture');
  if (u.pathname === '/__mode') { mode = u.searchParams.get('value') || 'normal'; return json(res, { mode }); }
  if (u.pathname.startsWith('/avian/api/')) {
    if (mode === 'fail') return json(res, { error: 'fixture failure' }, 503);
    if (u.pathname.endsWith('display-config.php')) return json(res, { settings: { labels: true, overnight_enabled: true, page_seconds: 5, default_hours: 1, theme: 'light' } });
    if (u.pathname.endsWith('illustration-library.php')) {
      if (u.searchParams.get('asset')) return json(res, {});
      return json(res, { library: 'standard', revision: 'fixture', immutable: true });
    }
    if (u.pathname.endsWith('cutout.php')) return json(res, { error: 'missing fixture artwork' }, 404);
    if (u.pathname.endsWith('birdnet-api.php')) {
      const action = u.searchParams.get('action');
      if (action === 'recent') {
        const species = mode === 'empty' ? [] : mode === 'overnight-only' ? birds.slice(0, 13) : birds;
        return json(res, { species });
      }
      if (action === 'overnight') return json(res, { visible: true, timezone: 'Australia/Brisbane', species: [birds[0], { ...birds[13], last_seen_iso: '2026-09-07T02:14:00+10:00' }].map((b, i) => ({ ...b, last_seen_iso: b.last_seen_iso || '2026-09-07T04:00:00+10:00' })) });
      if (action === 'stats') return json(res, { last_hour: { detections: 14 }, today: { detections: 14 }, week: { detections: 14 }, totals: { detections: 14 } });
      if (action === 'lifelist' || action === 'firstseen') return json(res, { species: birds });
      if (action === 'timeseries') return json(res, { daily: [], by_hour: [] });
    }
    return json(res, {});
  }
  const requestPath = u.pathname === '/' ? 'index.html' : u.pathname.replace(/^\//, '');
  let file = path.join(root, 'avian/frontend', requestPath);
  if (!file.startsWith(root) || !fs.existsSync(file)) { res.writeHead(404); return res.end(); }
  res.writeHead(200, { 'content-type': file.endsWith('.css') ? 'text/css' : file.endsWith('.js') ? 'application/javascript' : file.endsWith('.html') ? 'text/html' : 'image/webp' });
  fs.createReadStream(file).pipe(res);
}).listen(4173, '127.0.0.1', () => console.log('fixture http://127.0.0.1:4173/'));
