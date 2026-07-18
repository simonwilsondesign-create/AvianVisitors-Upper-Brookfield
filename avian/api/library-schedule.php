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

function av_resolve_library(): array {
    $definitions = av_library_definitions();
    $timezone = av_schedule_timezone();
    $now = new DateTimeImmutable('now', $timezone);
    $override = strtolower(trim((string)($_GET['library'] ?? '')));
    $hasOverride = array_key_exists($override, $definitions);
    $requested = $hasOverride ? $override : av_scheduled_library($now);
    $selected = av_library_is_ready($definitions[$requested]) ? $requested : 'standard';
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
    ];
}
