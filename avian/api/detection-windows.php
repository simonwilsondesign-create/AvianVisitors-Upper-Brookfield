<?php
// Shared, site-local detection windows. BirdNET stores Date and Time as local text.
declare(strict_types=1);
require_once __DIR__ . '/taxonomy.php';
require_once __DIR__ . '/display-settings.php';

function av_detection_now(): DateTimeImmutable {
    return new DateTimeImmutable('now', av_display_timezone());
}

/**
 * Brisbane's civil timezone is the authority for display boundaries.  The
 * PHP's bundled solar calculation keeps the sunrise boundary local without a
 * network call or an additional Pi dependency.
 */
function av_brisbane_coordinates(): array {
    $path = getenv('AV_BIRDNET_CONFIG_PATH') ?: '/etc/birdnet/birdnet.conf';
    if (!is_readable($path)) $path = dirname(__DIR__, 2) . '/birdnet.conf';
    $values = [];
    if (is_readable($path)) {
        foreach (file($path, FILE_IGNORE_NEW_LINES) ?: [] as $line) {
            if (preg_match('/^\s*(LATITUDE|LONGITUDE)\s*=\s*([^#\s]+)/', $line, $match)) {
                $values[$match[1]] = (float)trim($match[2], "\"'");
            }
        }
    }
    $latitude = $values['LATITUDE'] ?? -27.4705;
    $longitude = $values['LONGITUDE'] ?? 153.0260;
    return [$latitude, $longitude];
}

function av_brisbane_sunrise(DateTimeImmutable $day): DateTimeImmutable {
    $tz = av_display_timezone();
    $day = $day->setTimezone($tz);
    [$latitude, $longitude] = av_brisbane_coordinates();
    // Local noon ensures date_sun_info is asked for the requested local day.
    $sun = date_sun_info($day->setTime(12, 0)->getTimestamp(), $latitude, $longitude);
    if (!is_int($sun['sunrise'] ?? null)) throw new RuntimeException('Sunrise unavailable for site');
    return (new DateTimeImmutable('@' . $sun['sunrise']))->setTimezone($tz);
}

function av_overnight_window(DateTimeImmutable $now, array $settings): array {
    $now = $now->setTimezone(av_display_timezone());
    $today = $now->setTime(0, 0);
    $nightStart = $today->setTime($settings['night_start_hour'], 0);
    $sunrise = av_brisbane_sunrise($today);
    if ($now >= $nightStart) {
        $start = $nightStart;
        $end = av_brisbane_sunrise($today->modify('+1 day'));
        $displayEnd = $today->modify('+1 day')->setTime($settings['morning_end_hour'], 0);
        $phase = 'night';
    } else {
        $start = $today->modify('-1 day')->setTime($settings['night_start_hour'], 0);
        $end = $sunrise;
        $displayEnd = $today->setTime($settings['morning_end_hour'], 0);
        $phase = $now < $sunrise ? 'night' : ($now < $displayEnd ? 'dawn' : 'day');
    }
    return [
        'start' => $start, 'end' => $end,
        'display_start' => $end, 'display_end' => $displayEnd,
        'phase' => $phase,
        'visible' => $settings['overnight_enabled'] && in_array($phase, ['night', 'dawn'], true),
    ];
}

function av_window_bind(DateTimeImmutable $start, DateTimeImmutable $end): array {
    return [':start_date' => $start->format('Y-m-d'), ':start_time' => $start->format('H:i:s'),
        ':end_date' => $end->format('Y-m-d'), ':end_time' => $end->format('H:i:s')];
}

function av_window_sql(bool $includeEnd = true): string {
    // Tuple comparison uses the existing Date/Time index and crosses midnight.
    return '(Date, Time) >= (:start_date, :start_time) AND (Date, Time) '
        . ($includeEnd ? '<=' : '<') . ' (:end_date, :end_time)';
}

function av_detection_rows(SQLite3 $db, string $sql, array $bind = []): array {
    $statement = $db->prepare($sql);
    if (!$statement) throw new RuntimeException('Could not prepare detection query');
    foreach ($bind as $key => $value) {
        $statement->bindValue($key, $value, is_int($value) ? SQLITE3_INTEGER : SQLITE3_TEXT);
    }
    $result = $statement->execute();
    if (!$result) throw new RuntimeException('Could not execute detection query');
    $out = [];
    while ($row = $result->fetchArray(SQLITE3_ASSOC)) $out[] = $row;
    $result->finalize();
    $statement->close();
    return $out;
}

function av_window_species(SQLite3 $db, DateTimeImmutable $start, DateTimeImmutable $end, bool $includeEnd = true): array {
    $canonical = avian_canonical_sci_sql();
    // One bounded scan; avoid a separate best-recording query for every species.
    $sql = "WITH windowed AS (SELECT $canonical AS sci, Com_Name AS com, Confidence AS conf, "
        . "Date || ' ' || Time AS detected_at, File_Name AS file FROM detections WHERE " . av_window_sql($includeEnd) . "), "
        . "ranked AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY sci ORDER BY conf DESC, detected_at DESC, file ASC) AS rank FROM windowed), "
        . "summary AS (SELECT sci, MAX(com) AS com, COUNT(*) AS n, MAX(conf) AS best_conf, MAX(detected_at) AS last_seen FROM windowed GROUP BY sci) "
        . "SELECT summary.*, ranked.file AS top_file, ranked.detected_at AS top_at FROM summary "
        . "JOIN ranked ON ranked.sci = summary.sci AND ranked.rank = 1 ORDER BY last_seen DESC, summary.sci ASC";
    $rows = av_detection_rows($db, $sql, av_window_bind($start, $end));
    foreach ($rows as &$row) {
        $row['last_seen_iso'] = (new DateTimeImmutable($row['last_seen'], av_display_timezone()))->format(DATE_ATOM);
        $row['top_at_iso'] = (new DateTimeImmutable($row['top_at'], av_display_timezone()))->format(DATE_ATOM);
    }
    unset($row);
    return $rows;
}

function av_window_count(SQLite3 $db, DateTimeImmutable $start, DateTimeImmutable $end): array {
    $canonical = avian_canonical_sci_sql();
    return av_detection_rows($db, "SELECT COUNT(*) AS n, COUNT(DISTINCT $canonical) AS species FROM detections WHERE "
        . av_window_sql(), av_window_bind($start, $end))[0];
}
