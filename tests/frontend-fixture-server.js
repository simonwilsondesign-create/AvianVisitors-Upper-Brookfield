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
function relativeIso(minutes) { return new Date(Date.now() + minutes * 60_000).toISOString(); }
function displayPhase() {
  if (mode === 'night') return 'night';
  if (mode === 'day') return 'day';
  return 'dawn';
}
function koalaFixture() {
  if (mode === 'koala-off') return { visible: false, display_phase: 'inactive', candidate: null };
  if (mode === 'koala-recent') return {
    visible: true, display_phase: 'recent',
    candidate: { detected_at: relativeIso(-10), status: 'candidate', recording_url: '/fixture-koala.wav' },
  };
  if (mode === 'koala-dawn') return {
    visible: true, display_phase: 'dawn',
    display_end_iso: relativeIso(60),
    candidate: { detected_at: relativeIso(-240), status: 'candidate', recording_url: '/fixture-koala.wav' },
  };
  return { visible: false, display_phase: 'inactive', candidate: null };
}
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
    if (u.pathname.endsWith('koala.php')) return json(res, koalaFixture());
    if (u.pathname.endsWith('birdnet-api.php')) {
      const action = u.searchParams.get('action');
      if (action === 'recent') {
        const species = mode === 'empty' ? [] : mode === 'overnight-only' ? birds.slice(0, 13) : birds;
        return json(res, { species: species.map((bird) => ({ ...bird, last_seen_iso: relativeIso(-10) })) });
      }
      if (action === 'overnight') {
        const phase = displayPhase();
        const intervalEnd = phase === 'night' ? relativeIso(240) : relativeIso(-90);
        const displayEnd = phase === 'day' ? relativeIso(-1) : phase === 'night' ? relativeIso(420) : relativeIso(60);
        return json(res, {
          visible: phase !== 'day', phase, timezone: 'Australia/Brisbane',
          interval_end_iso: intervalEnd, display_end_iso: displayEnd,
          species: [birds[0], { ...birds[13], last_seen_iso: relativeIso(-240) }].map((b, i) => ({ ...b, last_seen_iso: b.last_seen_iso || relativeIso(-240) })),
        });
      }
      if (action === 'stats') return json(res, { last_hour: { detections: 14 }, today: { detections: 14 }, week: { detections: 14 }, totals: { detections: 14 } });
      if (action === 'lifelist' || action === 'firstseen') return json(res, { species: birds });
      if (action === 'timeseries') return json(res, { daily: [], by_hour: [] });
    }
    return json(res, {});
  }
  const requestPath = u.pathname === '/' ? 'index.html' : u.pathname.replace(/^\//, '');
  // The real kiosk serves the frontend from its root and assets from /avian.
  // Mirror that arrangement so visual fixtures can load the transparent koala.
  let file = requestPath.startsWith('avian/assets/')
    ? path.join(root, requestPath)
    : path.join(root, 'avian/frontend', requestPath);
  if (!file.startsWith(root) || !fs.existsSync(file)) { res.writeHead(404); return res.end(); }
  const type = file.endsWith('.css') ? 'text/css' : file.endsWith('.js') ? 'application/javascript' : file.endsWith('.html') ? 'text/html' : file.endsWith('.png') ? 'image/png' : 'image/webp';
  res.writeHead(200, { 'content-type': type });
  fs.createReadStream(file).pipe(res);
}).listen(4173, '127.0.0.1', () => console.log('fixture http://127.0.0.1:4173/'));
