<?php
// Returns the active scheduled library or its matching mask metadata.

declare(strict_types=1);
require_once __DIR__ . '/library-schedule.php';

$selection = av_resolve_library();
$asset = strtolower(trim((string)($_GET['asset'] ?? '')));
$pinnedRevision = trim((string)($_GET['revision'] ?? ''));
if ($pinnedRevision !== '') {
    $pinned = av_named_release($selection['key'], $pinnedRevision);
    if (!$pinned) {
        http_response_code(409);
        header('Content-Type: application/json; charset=utf-8');
        echo json_encode(['error' => 'requested artwork revision is unavailable']);
        exit;
    }
    $selection['release'] = $pinned;
}
header('Cache-Control: no-store');

if ($asset === 'dims' || $asset === 'masks') {
    if ($selection['release']) {
        $path = $selection['release']['directory'] . '/' . $asset . '.json';
        $contents = is_file($path) ? file_get_contents($path) : false;
    } else {
        $metadata = av_legacy_metadata($selection, $asset);
        $contents = $metadata === null ? false : json_encode($metadata, JSON_UNESCAPED_SLASHES);
    }
    if ($contents === false) {
        http_response_code(404);
        header('Content-Type: application/json; charset=utf-8');
        echo json_encode(['error' => 'library metadata unavailable']);
        exit;
    }
    header('Content-Type: application/json; charset=utf-8');
    header('Content-Length: ' . (string)strlen($contents));
    echo $contents;
    exit;
}

if ($asset === 'manifest') {
    if (!$selection['release']) {
        http_response_code(404);
        header('Content-Type: application/json; charset=utf-8');
        echo json_encode(['error' => 'no immutable release is active']);
        exit;
    }
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode($selection['release']['manifest'], JSON_UNESCAPED_SLASHES);
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
    'revision' => $selection['release']['revision'] ?? null,
    'immutable' => $selection['release'] !== null,
], JSON_UNESCAPED_SLASHES);
