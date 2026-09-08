<?php
// Read-only koala candidate windows for the unattended display.
declare(strict_types=1);
require_once __DIR__ . '/detection-windows.php';
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');

function av_koala_enrich_candidate(array $candidate): array {
    // The published TPR is filter context, never event-level certainty.
    $candidate['confidence_kind'] = 'filter_tpr';
    $root = getenv('AV_KOALA_RECORDINGS_PATH') ?: '/var/lib/avian-koala/recordings';
    if (is_file($root . '/' . $candidate['recording'])) {
        $candidate['recording_url'] = '/avian/api/koala-recording.php?recording=' . rawurlencode((string)$candidate['recording']);
    }
    return $candidate;
}

function av_koala_candidate(SQLite3 $db, DateTimeImmutable $start, DateTimeImmutable $end): ?array {
    $query = $db->prepare("SELECT detected_at, confidence, recording, status FROM detections WHERE detected_at >= :start AND detected_at < :end AND status != 'rejected' ORDER BY detected_at DESC LIMIT 1");
    if (!$query) return null;
    $query->bindValue(':start', $start->format(DATE_ATOM), SQLITE3_TEXT);
    $query->bindValue(':end', $end->format(DATE_ATOM), SQLITE3_TEXT);
    $result = $query->execute();
    $candidate = $result ? ($result->fetchArray(SQLITE3_ASSOC) ?: null) : null;
    if ($result) $result->finalize();
    $query->close();
    return $candidate !== null ? av_koala_enrich_candidate($candidate) : null;
}

$now = av_detection_now();
$settings = av_display_settings();
$overnightWindow = av_overnight_window($now, $settings);
$recentStart = $now->modify('-1 hour');
$overnightQueryEnd = $overnightWindow['end'] > $now ? $now : $overnightWindow['end'];
$path = getenv('AV_KOALA_STATE_PATH') ?: '/var/lib/avian-koala/state.sqlite';
$recent = null;
$overnight = null;
$history = [];
if (is_file($path) && class_exists('SQLite3')) {
    try {
        $db = new SQLite3($path, SQLITE3_OPEN_READONLY);
        $recent = av_koala_candidate($db, $recentStart, $now);
        $overnight = av_koala_candidate($db, $overnightWindow['start'], $overnightQueryEnd);
        if (($_GET['action'] ?? '') === 'history') {
            $limit = max(1, min(100, (int)($_GET['limit'] ?? 25)));
            $query = $db->prepare("SELECT detected_at, confidence, recording, status FROM detections WHERE status != 'rejected' ORDER BY detected_at DESC LIMIT :limit");
            $query->bindValue(':limit', $limit, SQLITE3_INTEGER);
            $result = $query->execute();
            while ($result && ($row = $result->fetchArray(SQLITE3_ASSOC))) $history[] = av_koala_enrich_candidate($row);
            if ($result) $result->finalize();
            $query->close();
        }
        $db->close();
    } catch (Throwable $error) { $recent = null; $overnight = null; }
}

$carryVisible = $overnightWindow['visible'];
// A rolling-hour candidate is always current. During the active night and
// dawn carry period, retain the latest overnight candidate if none is newer.
$candidate = $recent ?? ($carryVisible ? $overnight : null);
$phase = $recent !== null ? 'recent' : ($carryVisible && $overnight !== null ? $overnightWindow['phase'] : 'inactive');
echo json_encode([
    'visible' => $candidate !== null,
    'display_phase' => $phase,
    'candidate' => $candidate,
    'recent' => $recent,
    'overnight' => $overnight,
    'recent_start_iso' => $recentStart->format(DATE_ATOM),
    'recent_end_iso' => $now->format(DATE_ATOM),
    'interval_start_iso' => $overnightWindow['start']->format(DATE_ATOM),
    'interval_end_iso' => $overnightWindow['end']->format(DATE_ATOM),
    'display_start_iso' => $overnightWindow['display_start']->format(DATE_ATOM),
    'display_end_iso' => $overnightWindow['display_end']->format(DATE_ATOM),
    'window_end' => $overnightWindow['display_end']->format(DATE_ATOM),
    'timezone' => av_display_timezone()->getName(),
    'as_of' => $now->format(DATE_ATOM),
    'history' => $history,
], JSON_UNESCAPED_SLASHES);
