<?php
declare(strict_types=1);

require_once __DIR__ . '/../../avian/api/detection-windows.php';

function check(bool $condition, string $message): void {
    if (!$condition) throw new RuntimeException($message);
}

$db = new SQLite3(':memory:');
$db->exec('CREATE TABLE detections (Date TEXT, Time TEXT, Sci_Name TEXT, Com_Name TEXT, Confidence REAL, File_Name TEXT)');
$db->exec("INSERT INTO detections VALUES
 ('2026-09-06','18:00:00','Ninox boobook','Southern Boobook',0.91,'night-start.wav'),
 ('2026-09-07','02:14:00','Ninox boobook','Southern Boobook',0.95,'owl.wav'),
 ('2026-09-07','05:59:59','Tyto alba','Barn Owl',0.87,'barn.wav'),
 ('2026-09-07','06:00:00','Tyto alba','Barn Owl',0.90,'morning.wav')");

$timezone = new DateTimeZone('Australia/Brisbane');
$start = new DateTimeImmutable('2026-09-06 18:00:00', $timezone);
$end = new DateTimeImmutable('2026-09-07 06:00:00', $timezone);
$birds = av_window_species($db, $start, $end, false);
check(count($birds) === 2, 'overnight species are grouped');
foreach ($birds as $bird) {
    if ($bird['sci'] === 'Tyto alba') check($bird['n'] === 1, '06:00 belongs to morning, not overnight');
}

$window = av_overnight_window(new DateTimeImmutable('2026-09-07 08:00:00', $timezone), av_display_defaults());
check($window['visible'] === true, 'morning strip is visible at 08:00');
check($window['start']->format('Y-m-d H:i:s') === '2026-09-06 18:00:00', 'overnight starts previous evening');
$window = av_overnight_window(new DateTimeImmutable('2026-09-07 12:00:00', $timezone), av_display_defaults());
check($window['visible'] === false, 'morning strip ends at noon');
echo "detection window tests passed\n";
