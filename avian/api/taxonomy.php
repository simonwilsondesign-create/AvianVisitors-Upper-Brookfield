<?php
// Taxonomy aliases between the installed BirdNET 2.4 model and the
// current scientific names used by the Brisbane illustration library.

declare(strict_types=1);

function avian_taxonomy_aliases(): array {
    return [
        'Streptopelia chinensis' => 'Spilopelia chinensis',
        'Calyptorhynchus funereus' => 'Zanda funerea',
    ];
}

function avian_canonical_sci(string $sci): string {
    return avian_taxonomy_aliases()[$sci] ?? $sci;
}

function avian_model_sci(string $sci): string {
    $modelName = array_search($sci, avian_taxonomy_aliases(), true);
    return $modelName === false ? $sci : $modelName;
}

function avian_canonical_sci_sql(string $column = 'Sci_Name'): string {
    if (!preg_match('/^[A-Za-z_][A-Za-z0-9_.]*$/', $column)) {
        throw new InvalidArgumentException('unsafe SQLite column name');
    }
    $parts = ["CASE $column"];
    foreach (avian_taxonomy_aliases() as $old => $current) {
        $old = str_replace("'", "''", $old);
        $current = str_replace("'", "''", $current);
        $parts[] = "WHEN '$old' THEN '$current'";
    }
    $parts[] = "ELSE $column END";
    return implode(' ', $parts);
}
