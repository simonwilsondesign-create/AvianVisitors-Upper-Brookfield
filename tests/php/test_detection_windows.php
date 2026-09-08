<?php
declare(strict_types=1);

require_once __DIR__ . '/../../avian/api/detection-windows.php';

function check(bool $condition, string $message): void {
    if (!$condition) throw new RuntimeException($message);
}

$timezone = new DateTimeZone('Australia/Brisbane');
$dawn = new DateTimeImmutable('2026-09-07 08:00:00', $timezone);
$window = av_overnight_window($dawn, av_display_defaults());
$sunrise = $window['end'];

check($sunrise->format('Y-m-d') === '2026-09-07', 'sunrise stays on the requested Brisbane date');
check((int)$sunrise->format('G') >= 4 && (int)$sunrise->format('G') <= 7, 'sunrise is a local morning boundary');
check($window['visible'] === true, 'overnight birds remain visible during the dawn display');
check($window['phase'] === 'dawn', 'sunrise to 09:00 is the dawn split-scene phase');
check($window['start']->format('Y-m-d H:i:s') === '2026-09-06 18:00:00', 'overnight starts on the previous evening');

$night = av_overnight_window(new DateTimeImmutable('2026-09-07 20:00:00', $timezone), av_display_defaults());
check($night['phase'] === 'night' && $night['visible'] === true, 'evening begins a visible overnight scene');
check($night['start']->format('Y-m-d H:i:s') === '2026-09-07 18:00:00', 'evening scene accumulates from tonight at 18:00');

$db = new SQLite3(':memory:');
$db->exec('CREATE TABLE detections (Date TEXT, Time TEXT, Sci_Name TEXT, Com_Name TEXT, Confidence REAL, File_Name TEXT)');
$insert = $db->prepare('INSERT INTO detections VALUES (:date, :time, :sci, :com, :confidence, :file)');
$add = static function (DateTimeImmutable $at, string $sci, string $com, string $file) use ($insert): void {
    $insert->bindValue(':date', $at->format('Y-m-d'), SQLITE3_TEXT);
    $insert->bindValue(':time', $at->format('H:i:s'), SQLITE3_TEXT);
    $insert->bindValue(':sci', $sci, SQLITE3_TEXT);
    $insert->bindValue(':com', $com, SQLITE3_TEXT);
    $insert->bindValue(':confidence', 0.91, SQLITE3_FLOAT);
    $insert->bindValue(':file', $file, SQLITE3_TEXT);
    $insert->execute();
};

// A real overnight bird, a first-light bird exactly at sunrise, and a bird
// from the rolling one-hour dawn chorus are deliberately distinct.
$add($window['start'], 'Ninox boobook', 'Southern Boobook', 'night-start.wav');
$add($sunrise->modify('-1 second'), 'Tyto alba', 'Barn Owl', 'last-night.wav');
$add($sunrise, 'Pachycephala pectoralis', 'Golden Whistler', 'sunrise.wav');
$add($dawn->modify('-30 minutes'), 'Acanthiza pusilla', 'Brown Thornbill', 'dawn.wav');

$overnight = av_window_species($db, $window['start'], $sunrise, false);
check(count($overnight) === 2, 'overnight query retains birds through the final second before sunrise');
check(!in_array('Pachycephala pectoralis', array_column($overnight, 'sci'), true), 'a sunrise detection is not duplicated in the overnight group');

$morning = av_window_species($db, $dawn->modify('-1 hour'), $dawn);
check(count($morning) === 1 && $morning[0]['sci'] === 'Acanthiza pusilla', 'dawn chorus uses only its rolling one-hour window');

$cutoff = av_overnight_window(new DateTimeImmutable('2026-09-07 09:00:00', $timezone), av_display_defaults());
check($cutoff['visible'] === false, 'overnight display ends exactly at 09:00');
check($cutoff['phase'] === 'day', '09:00 returns to the normal daytime scene');

// A fresh morning request reconstructs the same bounded slices from the
// database, rather than depending on state held by an earlier render.
$restartOvernight = av_window_species($db, $window['start'], $sunrise, false);
$restartMorning = av_window_species($db, $dawn->modify('-1 hour'), $dawn);
check(array_column($restartOvernight, 'sci') === array_column($overnight, 'sci'), 'morning restart restores overnight detections');
check(array_column($restartMorning, 'sci') === array_column($morning, 'sci'), 'morning restart restores rolling-hour detections');
echo "detection window tests passed\n";
