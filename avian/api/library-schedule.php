<?php
// Shared illustration-library schedule for images and silhouette metadata.

declare(strict_types=1);

function av_library_definitions(): array {
    $avian = dirname(__DIR__);
    return [
        'standard' => [
            'label' => 'Standard Brisbane birds',
            'illustrations' => $avian . '/assets/illustrations',
            'metadata' => $avian . '/frontend',
        ],
        'fun' => [
            'label' => 'Friday fun birds',
            'illustrations' => $avian . '/assets/illustration-libraries/brisbane-weekend/cutouts',
            'metadata' => $avian . '/assets/illustration-libraries/brisbane-weekend/metadata',
        ],
        'wes' => [
            'label' => 'Weekend storybook birds',
            'illustrations' => $avian . '/assets/illustration-libraries/brisbane-wes-anderson/cutouts',
            'metadata' => $avian . '/assets/illustration-libraries/brisbane-wes-anderson/metadata',
        ],
    ];
}
function av_release_root(string $key): string {
    return dirname(__DIR__) . '/assets/illustration-releases/' . $key;
}
function av_release(string $key): ?array {
    $root = av_release_root($key);
    $current = $root . '/CURRENT';
    if (!is_file($current)) return null;
    $revision = trim((string)file_get_contents($current));
    if (!preg_match('/^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$/', $revision)) return null;
    $directory = $root . '/' . $revision;
    $manifest = $directory . '/manifest.json';
    if (!is_file($manifest)) return null;
    $data = json_decode((string)file_get_contents($manifest), true);
    if (!is_array($data) || ($data['library'] ?? null) !== $key || ($data['revision'] ?? null) !== $revision
        || !is_file($directory . '/dims.json') || !is_file($directory . '/masks.json') || !is_dir($directory . '/illustrations')) return null;
    return ['revision' => $revision, 'directory' => $directory, 'manifest' => $data];
}
function av_named_release(string $key, string $revision): ?array {
    if (!preg_match('/^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$/', $revision)) return null;
    $directory = av_release_root($key) . '/' . $revision;
    $manifest = $directory . '/manifest.json';
    if (!is_file($manifest)) return null;
    $data = json_decode((string)file_get_contents($manifest), true);
    if (!is_array($data) || ($data['library'] ?? null) !== $key || ($data['revision'] ?? null) !== $revision
        || !is_file($directory . '/dims.json') || !is_file($directory . '/masks.json') || !is_dir($directory . '/illustrations')) return null;
    return ['revision' => $revision, 'directory' => $directory, 'manifest' => $data];
}
function av_schedule_timezone(): DateTimeZone {
    $name = getenv('AV_TIMEZONE') ?: 'Australia/Brisbane';
    try {
        return new DateTimeZone($name);
    } catch (Exception $error) {
        return new DateTimeZone('Australia/Brisbane');
    }
}

function av_scheduled_library(DateTimeImmutable $now): string {
    $day = (int)$now->format('N'); // 1=Monday ... 7=Sunday
    if ($day <= 4) return 'standard';
    if ($day === 5) return 'fun';
    return 'wes';
}

function av_library_is_ready(array $definition): bool {
    return is_dir($definition['illustrations'])
        && is_file($definition['metadata'] . '/dims.json')
        && is_file($definition['metadata'] . '/masks.json');
}
function av_legacy_metadata(array $selection, string $asset): ?array {
    $path = $selection['definition']['metadata'] . '/' . $asset . '.json';
    $standard = $selection['standard']['metadata'] . '/' . $asset . '.json';
    $chosen = json_decode((string)@file_get_contents($path), true);
    if (!is_array($chosen)) return null;
    if ($selection['key'] === 'standard') return $chosen;
    // Image resolution tries alternate then standard per pose. Mirror that
    // exact order in metadata so a missing alternate pose uses standard dims
    // and mask, while approved alternate art retains its own silhouette.
    $base = json_decode((string)@file_get_contents($standard), true);
    if (!is_array($base)) return null;
    $art = $selection['definition']['illustrations'];
    foreach ($chosen as $key => $value) {
        if (is_file($art . '/' . $key . '.png')) {
            $base[$key] = $value;
        } elseif (str_ends_with($key, '-2')) {
            $primary = substr($key, 0, -2);
            // This mirrors cutout.php's alternate pose-1 fallback.
            if (is_file($art . '/' . $primary . '.png') && array_key_exists($primary, $chosen)) {
                $base[$key] = $chosen[$primary];
            }
        }
    }
    return $base;
}

function av_resolve_library(): array {
    $definitions = av_library_definitions();
    $timezone = av_schedule_timezone();
    $now = new DateTimeImmutable('now', $timezone);
    $override = strtolower(trim((string)($_GET['library'] ?? '')));
    $hasOverride = array_key_exists($override, $definitions);
    $requested = $hasOverride ? $override : av_scheduled_library($now);
    $requestedRelease = av_release($requested);
    $selected = ($requestedRelease || av_library_is_ready($definitions[$requested])) ? $requested : 'standard';
    $release = $selected === $requested ? $requestedRelease : av_release('standard');
    $nextMidnight = $now->modify('tomorrow')->setTime(0, 1);

    return [
        'key' => $selected,
        'requested' => $requested,
        'fallback' => $selected !== $requested,
        'override' => $hasOverride,
        'timezone' => $timezone->getName(),
        'next_reload_ms' => ((int)$nextMidnight->format('U')) * 1000,
        'definition' => $definitions[$selected],
        'standard' => $definitions['standard'],
        'release' => $release,
    ];
}
