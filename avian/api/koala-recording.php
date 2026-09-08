<?php
// Serve a durable WAV saved when the koala recogniser found a candidate.
declare(strict_types=1);
$recording = trim((string)($_GET['recording'] ?? ''));
if ($recording === '' || strpos($recording, '..') !== false || !preg_match('/^[A-Za-z0-9_.: -]+\.wav$/', $recording)) {
    http_response_code(400); echo 'invalid recording'; exit;
}
$root = getenv('AV_KOALA_RECORDINGS_PATH') ?: '/var/lib/avian-koala/recordings';
$path = $root . '/' . $recording;
if (!is_file($path) || filesize($path) < 64) {
    http_response_code(404); echo 'recording not found'; exit;
}
header('Content-Type: audio/wav');
header('Content-Length: ' . filesize($path));
header('Cache-Control: private, max-age=86400');
readfile($path);
