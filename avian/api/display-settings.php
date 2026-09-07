<?php
// Shared, server-side settings for the unattended Avian display.
//
// The settings file deliberately lives outside the web root.  Set
// AV_DISPLAY_SETTINGS_PATH to a directory owned by the PHP-FPM user, for
// example /var/lib/avian/display-settings.json.

declare(strict_types=1);

const AV_DISPLAY_FALLBACK_TIMEZONE = 'Australia/Brisbane';

function av_display_timezone(): DateTimeZone {
    $name = getenv('AV_TIMEZONE') ?: AV_DISPLAY_FALLBACK_TIMEZONE;
    try {
        return new DateTimeZone($name);
    } catch (Exception $error) {
        return new DateTimeZone(AV_DISPLAY_FALLBACK_TIMEZONE);
    }
}

function av_display_defaults(): array {
    return [
        'profile' => 'kiosk',
        'labels' => true,
        'overnight_enabled' => true,
        'night_start_hour' => 18,
        'night_end_hour' => 6,
        'morning_end_hour' => 9,
        'page_seconds' => 15,
        'theme' => 'light',
        'default_hours' => 1,
        'kiosk_idle_seconds' => 120,
        'timezone' => av_display_timezone()->getName(),
        'revision' => 0,
    ];
}

function av_display_settings_path(): string {
    $configured = trim((string)getenv('AV_DISPLAY_SETTINGS_PATH'));
    return $configured !== '' ? $configured : '/var/lib/avian/display-settings.json';
}

function av_display_path_is_outside_webroot(string $path): bool {
    if ($path === '' || $path[0] !== '/') return false;
    $webroot = realpath(dirname(__DIR__)); // .../avian
    $directory = realpath(dirname($path));
    if ($webroot === false || $directory === false) return true;
    return $directory !== $webroot && strpos($directory . '/', $webroot . '/') !== 0;
}

function av_display_validation_error(array $updates): array {
    $allowed = [
        'labels', 'overnight_enabled', 'night_start_hour', 'night_end_hour',
        'morning_end_hour', 'page_seconds', 'theme', 'default_hours',
        'kiosk_idle_seconds', 'expected_revision',
    ];
    $errors = [];
    foreach ($updates as $key => $value) {
        if (!in_array($key, $allowed, true)) {
            $errors[$key] = $key === 'timezone' ? 'server managed' : 'unknown setting';
            continue;
        }
        if (in_array($key, ['labels', 'overnight_enabled'], true) && !is_bool($value)) {
            $errors[$key] = 'must be boolean';
        }
        if (in_array($key, ['night_start_hour', 'night_end_hour', 'morning_end_hour'], true)
            && (!is_int($value) || $value < 0 || $value > 23)) {
            $errors[$key] = 'must be an integer from 0 to 23';
        }
        if ($key === 'page_seconds' && (!is_int($value) || $value < 5 || $value > 120)) {
            $errors[$key] = 'must be an integer from 5 to 120';
        }
        if ($key === 'default_hours' && (!is_int($value) || $value < 1 || $value > 168)) {
            $errors[$key] = 'must be an integer from 1 to 168';
        }
        if ($key === 'kiosk_idle_seconds' && (!is_int($value) || $value < 30 || $value > 3600)) {
            $errors[$key] = 'must be an integer from 30 to 3600';
        }
        if ($key === 'theme' && !in_array($value, ['light', 'dark'], true)) {
            $errors[$key] = 'must be light or dark';
        }
        if ($key === 'expected_revision' && (!is_int($value) || $value < 0)) {
            $errors[$key] = 'must be a non-negative integer';
        }
    }
    return $errors;
}

function av_display_window_error(array $settings): array {
    $errors = [];
    // This is one overnight period crossing midnight, followed by a morning
    // display period. Reject ambiguous values before saving them remotely.
    if ($settings['night_start_hour'] <= $settings['night_end_hour']) {
        $errors['night_start_hour'] = 'must be later than night end for an overnight window';
    }
    if ($settings['morning_end_hour'] <= $settings['night_end_hour']) {
        $errors['morning_end_hour'] = 'must be later than night end';
    }
    return $errors;
}

function av_display_normalize_settings(array $stored): array {
    $defaults = av_display_defaults();
    $storedFields = [
        'labels', 'overnight_enabled', 'night_start_hour', 'night_end_hour',
        'morning_end_hour', 'page_seconds', 'theme', 'default_hours',
        'kiosk_idle_seconds',
    ];
    $candidate = array_intersect_key($stored, array_flip($storedFields));
    $errors = av_display_validation_error($candidate);
    if ($errors) return $defaults;
    $settings = array_merge($defaults, $candidate);
    // The site timezone is configured on the server, never by a browser.
    $settings['timezone'] = av_display_timezone()->getName();
    $settings['profile'] = 'kiosk';
    $settings['revision'] = is_int($stored['revision'] ?? null) && $stored['revision'] >= 0
        ? $stored['revision'] : 0;
    return av_display_window_error($settings) ? $defaults : $settings;
}

function av_display_load_settings(?string $path = null): array {
    $path = $path ?? av_display_settings_path();
    if (!is_file($path)) return av_display_defaults();
    $raw = @file_get_contents($path);
    $stored = is_string($raw) ? json_decode($raw, true) : null;
    return is_array($stored) ? av_display_normalize_settings($stored) : av_display_defaults();
}

function av_display_stored_settings_are_valid(array $stored): bool {
    $allowed = [
        'profile', 'labels', 'overnight_enabled', 'night_start_hour', 'night_end_hour',
        'morning_end_hour', 'page_seconds', 'theme', 'default_hours',
        'kiosk_idle_seconds', 'timezone', 'revision',
    ];
    foreach (array_keys($stored) as $key) {
        if (!in_array($key, $allowed, true)) return false;
    }
    $userFields = [
        'labels', 'overnight_enabled', 'night_start_hour', 'night_end_hour',
        'morning_end_hour', 'page_seconds', 'theme', 'default_hours', 'kiosk_idle_seconds',
    ];
    foreach ($userFields as $field) {
        if (!array_key_exists($field, $stored)) return false;
    }
    $candidate = array_intersect_key($stored, array_flip($userFields));
    return ($stored['profile'] ?? null) === 'kiosk'
        && is_string($stored['timezone'] ?? null)
        && is_int($stored['revision'] ?? null) && $stored['revision'] >= 0
        && av_display_validation_error($candidate) === []
        && av_display_window_error(array_merge(av_display_defaults(), $candidate)) === [];
}

// Public name for consumers such as birdnet-api.php.  It intentionally has
// no file-path argument: production callers use the configured safe path.
function av_display_settings(): array {
    return av_display_load_settings();
}

function av_display_storage_health(?string $path = null): array {
    $path = $path ?? av_display_settings_path();
    if (!av_display_path_is_outside_webroot($path)) return ['status' => 'error', 'storage' => 'unsafe path'];
    if (!is_dir(dirname($path)) || !is_writable(dirname($path))) {
        return ['status' => 'error', 'storage' => 'unavailable'];
    }
    if (is_file($path) && !is_readable($path)) return ['status' => 'error', 'storage' => 'unreadable'];
    if (is_file($path)) {
        $raw = @file_get_contents($path);
        $stored = is_string($raw) ? json_decode($raw, true) : null;
        if (!is_array($stored) || !av_display_stored_settings_are_valid($stored)) {
            return ['status' => 'error', 'storage' => 'invalid'];
        }
    }
    return ['status' => 'ok', 'storage' => is_file($path) ? 'persisted' : 'defaults'];
}

/** @return array{ok: bool, settings?: array, error?: string, fields?: array} */
function av_display_update_settings(array $updates, ?string $path = null): array {
    $path = $path ?? av_display_settings_path();
    $errors = av_display_validation_error($updates);
    if ($errors) return ['ok' => false, 'error' => 'validation', 'fields' => $errors];
    if (!av_display_path_is_outside_webroot($path)) return ['ok' => false, 'error' => 'unsafe storage path'];
    $directory = dirname($path);
    if (!is_dir($directory) || !is_writable($directory)) {
        return ['ok' => false, 'error' => 'settings storage unavailable'];
    }
    $lock = @fopen($path . '.lock', 'c');
    if ($lock === false || !flock($lock, LOCK_EX)) return ['ok' => false, 'error' => 'settings storage unavailable'];
    try {
        $current = av_display_load_settings($path);
        $expected = $updates['expected_revision'] ?? null;
        unset($updates['expected_revision']);
        if ($expected !== null && $expected !== $current['revision']) {
            return ['ok' => false, 'error' => 'revision conflict', 'settings' => $current];
        }
        $next = array_merge($current, $updates);
        $windowErrors = av_display_window_error($next);
        if ($windowErrors) return ['ok' => false, 'error' => 'validation', 'fields' => $windowErrors];
        $next['profile'] = 'kiosk';
        $next['timezone'] = av_display_timezone()->getName();
        $next['revision'] = $current['revision'] + 1;
        $json = json_encode($next, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES);
        $temporary = @tempnam($directory, '.display-settings-');
        if ($json === false || $temporary === false || @file_put_contents($temporary, $json . "\n", LOCK_EX) === false) {
            if (is_string($temporary)) @unlink($temporary);
            return ['ok' => false, 'error' => 'settings storage unavailable'];
        }
        @chmod($temporary, 0640);
        if (!@rename($temporary, $path)) {
            @unlink($temporary);
            return ['ok' => false, 'error' => 'settings storage unavailable'];
        }
        return ['ok' => true, 'settings' => $next];
    } finally {
        flock($lock, LOCK_UN);
        fclose($lock);
    }
}
