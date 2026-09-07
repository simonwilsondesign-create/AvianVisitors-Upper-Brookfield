<?php
// Public read-only display settings and deliberately protected kiosk writes.

declare(strict_types=1);
require_once __DIR__ . '/display-settings.php';

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
header('X-Content-Type-Options: nosniff');

function av_display_json(array $body, int $status = 200): never {
    http_response_code($status);
    echo json_encode($body, JSON_UNESCAPED_SLASHES);
    exit;
}

function av_display_same_origin(): bool {
    $origin = $_SERVER['HTTP_ORIGIN'] ?? '';
    if ($origin === '') return true; // non-browser clients authenticate with the explicit token.
    $scheme = (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off') ? 'https' : 'http';
    $host = $_SERVER['HTTP_HOST'] ?? '';
    return $host !== '' && hash_equals($scheme . '://' . $host, $origin);
}

function av_display_token_is_valid(): bool {
    $token = (string)getenv('AV_DISPLAY_SETTINGS_TOKEN');
    $provided = $_SERVER['HTTP_X_AVIAN_DISPLAY_TOKEN'] ?? '';
    return $token !== '' && is_string($provided) && hash_equals($token, $provided);
}

function av_display_proxy_identity_is_valid(): bool {
    // This opt-in is only safe when the reverse proxy verifies credentials and
    // passes REMOTE_USER to PHP. A client supplied Authorization header alone
    // is never accepted.
    return getenv('AV_DISPLAY_TRUST_PROXY_AUTH') === '1'
        && !empty($_SERVER['REMOTE_USER']);
}

function av_display_issue_csrf_cookie(): string {
    $cookie = $_COOKIE['av_display_csrf'] ?? '';
    if (!is_string($cookie) || !preg_match('/^[a-f0-9]{64}$/', $cookie)) {
        $cookie = bin2hex(random_bytes(32));
        setcookie('av_display_csrf', $cookie, [
            'expires' => 0, 'path' => '/avian/api/', 'secure' => !empty($_SERVER['HTTPS']),
            'httponly' => false, 'samesite' => 'Strict',
        ]);
    }
    return $cookie;
}

function av_display_csrf_is_valid(): bool {
    $cookie = $_COOKIE['av_display_csrf'] ?? '';
    $provided = $_SERVER['HTTP_X_AVIAN_CSRF'] ?? '';
    return is_string($cookie) && is_string($provided) && $cookie !== '' && hash_equals($cookie, $provided);
}

$method = $_SERVER['REQUEST_METHOD'] ?? 'GET';
$health = av_display_storage_health();
$settings = av_display_load_settings();

if ($method === 'GET') {
    $body = [
        'settings' => $settings,
        'health' => $health,
        'server_time' => (new DateTimeImmutable('now', av_display_timezone()))->format(DATE_ATOM),
    ];
    if (av_display_proxy_identity_is_valid()) {
        $body['csrf_token'] = av_display_issue_csrf_cookie();
    }
    av_display_json($body);
}

if ($method !== 'POST') av_display_json(['error' => 'method not allowed'], 405);
if (!av_display_same_origin()) av_display_json(['error' => 'cross-origin write rejected'], 403);

$tokenAuth = av_display_token_is_valid();
$proxyAuth = av_display_proxy_identity_is_valid();
if (!$tokenAuth && !$proxyAuth) av_display_json(['error' => 'write authentication is not configured or failed'], 403);
if ($proxyAuth && !$tokenAuth && !av_display_csrf_is_valid()) {
    av_display_json(['error' => 'csrf validation failed'], 403);
}
if (stripos($_SERVER['CONTENT_TYPE'] ?? '', 'application/json') !== 0) {
    av_display_json(['error' => 'content type must be application/json'], 415);
}
$body = json_decode((string)file_get_contents('php://input'), true);
if (!is_array($body)) av_display_json(['error' => 'bad json'], 400);
$result = av_display_update_settings($body);
if (!$result['ok']) {
    $status = $result['error'] === 'revision conflict' ? 409 : ($result['error'] === 'validation' ? 400 : 503);
    av_display_json($result, $status);
}
av_display_json(['ok' => true, 'settings' => $result['settings'], 'health' => av_display_storage_health()]);
