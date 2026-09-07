<?php
// Read-only koala candidate status for the unattended display.
declare(strict_types=1);
require_once __DIR__ . '/display-settings.php';
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');

$tz = av_display_timezone();
$now = new DateTimeImmutable('now', $tz);
$today = $now->setTime(0, 0);
$evening = $today->setTime(18, 0);
$start = $now >= $evening ? $evening : $evening->modify('-1 day');
$end = $start->modify('+1 day')->setTime(10, 0);
$visible = $now >= $start && $now < $end;
$path = getenv('AV_KOALA_STATE_PATH') ?: '/var/lib/avian-koala/state.sqlite';
$candidate = null;
if ($visible && is_file($path) && class_exists('SQLite3')) {
    try {
        $db = new SQLite3($path, SQLITE3_OPEN_READONLY);
        $query = $db->prepare('SELECT detected_at, confidence, recording, status FROM detections WHERE detected_at >= :start AND detected_at < :end ORDER BY detected_at DESC LIMIT 1');
        $query->bindValue(':start', $start->format(DATE_ATOM), SQLITE3_TEXT);
        $query->bindValue(':end', $end->format(DATE_ATOM), SQLITE3_TEXT);
        $result = $query->execute();
        $candidate = $result ? ($result->fetchArray(SQLITE3_ASSOC) ?: null) : null;
        if ($result) $result->finalize();
        $query->close(); $db->close();
    } catch (Throwable $error) { $candidate = null; }
}
echo json_encode(['visible' => $visible && $candidate !== null, 'window_end' => $end->format(DATE_ATOM), 'candidate' => $candidate], JSON_UNESCAPED_SLASHES);
