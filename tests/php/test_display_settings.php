<?php
declare(strict_types=1);

require_once __DIR__ . '/../../avian/api/display-settings.php';

function assert_true(bool $condition, string $message): void {
    if (!$condition) throw new RuntimeException($message);
}

$directory = sys_get_temp_dir() . '/avian-display-settings-' . bin2hex(random_bytes(4));
mkdir($directory, 0700, true);
$path = $directory . '/settings.json';

$defaults = av_display_load_settings($path);
assert_true($defaults['profile'] === 'kiosk', 'default profile');
assert_true($defaults['timezone'] === 'Australia/Brisbane', 'default timezone');
assert_true($defaults['revision'] === 0, 'default revision');

$invalid = av_display_update_settings(['labels' => 'true'], $path);
assert_true(!$invalid['ok'] && $invalid['error'] === 'validation', 'booleans must be JSON booleans');
$invalid = av_display_update_settings(['timezone' => 'UTC'], $path);
assert_true(!$invalid['ok'] && $invalid['fields']['timezone'] === 'server managed', 'timezone is server managed');
$invalid = av_display_update_settings(['night_start_hour' => 5], $path);
assert_true(!$invalid['ok'] && isset($invalid['fields']['night_start_hour']), 'night crosses midnight');

$saved = av_display_update_settings([
    'labels' => false, 'overnight_enabled' => true, 'night_start_hour' => 19,
    'night_end_hour' => 5, 'morning_end_hour' => 11, 'page_seconds' => 20,
    'theme' => 'dark', 'default_hours' => 1, 'kiosk_idle_seconds' => 180,
    'expected_revision' => 0,
], $path);
assert_true($saved['ok'], 'valid settings save');
assert_true($saved['settings']['revision'] === 1 && $saved['settings']['theme'] === 'dark', 'saved settings revision');
assert_true(is_file($path), 'settings persisted');
assert_true(json_decode((string)file_get_contents($path), true)['labels'] === false, 'persisted JSON value');

$conflict = av_display_update_settings(['theme' => 'light', 'expected_revision' => 0], $path);
assert_true(!$conflict['ok'] && $conflict['error'] === 'revision conflict', 'stale writes conflict');
assert_true(av_display_storage_health($path)['status'] === 'ok', 'storage health');
assert_true(!av_display_path_is_outside_webroot(dirname(__DIR__, 2) . '/avian/settings.json'), 'webroot storage rejected');

unlink($path);
unlink($path . '.lock');
rmdir($directory);
echo "display settings tests passed\n";
