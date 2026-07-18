<?php
// Returns the active scheduled library or its matching mask metadata.

declare(strict_types=1);
require_once __DIR__ . '/library-schedule.php';

$selection = av_resolve_library();
$asset = strtolower(trim((string)($_GET['asset'] ?? '')));
header('Cache-Control: no-store');

if ($asset === 'dims' || $asset === 'masks') {
    $path = $selection['definition']['metadata'] . '/' . $asset . '.json';
    if (!is_file($path)) {
        http_response_code(404);
        header('Content-Type: application/json; charset=utf-8');
        echo json_encode(['error' => 'library metadata unavailable']);
        exit;
    }
    header('Content-Type: application/json; charset=utf-8');
    header('Content-Length: ' . (string)filesize($path));
    readfile($path);
    exit;
}

header('Content-Type: application/json; charset=utf-8');
echo json_encode([
    'library' => $selection['key'],
    'label' => $selection['definition']['label'],
    'requested' => $selection['requested'],
    'fallback' => $selection['fallback'],
    'override' => $selection['override'],
    'timezone' => $selection['timezone'],
    'next_reload_ms' => $selection['next_reload_ms'],
], JSON_UNESCAPED_SLASHES);
