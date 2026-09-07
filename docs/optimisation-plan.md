# AvianVisitors optimisation plan

Date: 7 September 2026. Status: implementation complete locally; pending deployment and artwork import.

## Scope and review limits

This began as a passive review of the local application source, illustration pipeline, installation scripts, CI configuration, deployment documentation, and the historical screenshot in `docs/thumb.png`. The implementation now covers the display, artwork inventory/import/release workflow, and test coverage described below. No production service restart, Pi configuration change, image generation, artwork import, or scheduled job installation has been performed. The screenshot illustrates the original layout; it is not evidence of the current deployed screen.

Assumption: the Pi drives a browser display with no routinely available keyboard, mouse, or touch input; administration happens remotely. This plan targets `avian/frontend`, not the optional e-ink implementation in `frame/`. Confirm the actual screen resolution, orientation, browser startup method, deployed revision, and timezone during implementation discovery.

The intended result is a readable, self-recovering bird display that retains the one-hour view, identifies every displayed bird, remembers overnight visitors in the morning, and inventories artwork gaps each week. Artwork generation remains a separately configured external step, at the user's request.

## Implementation record

Implemented locally:

- Species with missing, broken, or unavailable artwork remain visible as named placeholders; common-name captions, stable paging, stale-data feedback, and metadata retry handling are in the kiosk frontend.
- A bounded server-side overnight endpoint supplies the morning strip without altering the one-hour view; rolling queries now cross midnight correctly.
- Server-backed kiosk settings have validation, revisions, protected writes, and a site-managed timezone.
- The weekly systemd worker records a durable all-history artwork queue. It selects well-supported detections automatically and retains uncertain detections for review. It does not call an image provider.
- Reviewed external artwork can be merged into a complete staging library, validated, and atomically published as an immutable release; the browser refreshes on the release revision.
- PHP/JavaScript CI coverage and focused PHP fixtures were added. Local PHP is unavailable, so the PHP checks run in GitHub Actions after the change is pushed.

Still required on the Pi: deploy this revision, create `/var/lib/avian-artwork` with the `avian` service account, install and enable the timer, set the protected settings path/token if remote writes are needed, and import the artwork you generate using the supplied brief and release commands.

## Findings and priorities

Priorities: P1 = correctness/reliability or core requested behaviour; P2 = usability/performance; P3 = cleanup. These are source findings, not claims that every issue has occurred in production.

| Priority | Finding and source | Planned change |
|---|---|---|
| P1 | `renderCollage()` in `avian/frontend/apt.js` returns `null` for a species without a mask, then filters it out. A detection can disappear before its image resolver is called. | Always represent each eligible species with artwork or a named placeholder. |
| P1 | Metadata fetch failure leaves `tablesReady` false; rendering retries every 80 ms without refetching the failed metadata. | Bounded metadata retries, safe fallback layout, and explicit recovery state. |
| P1 | `refreshRecent()` only logs failure. `refreshAll()` retains old recent data but replaces other failed datasets with null. There is no fetch timeout or same-window request ordering protection. | Keep last successful data per endpoint, show freshness, cancel/ignore obsolete requests, and retry without overlapping polls. |
| P1 | Collage content comes exclusively from `recent&hours=...`; the default is correctly one hour. | Add a separate overnight summary without changing that query's meaning. |
| P1 | `stats` in `avian/api/birdnet-api.php` restricts last-hour counts to today's date. Around midnight it can omit yesterday's detections and include inappropriate times from today. | Use one bounded timestamp interval for both recent birds and last-hour totals; exclude future timestamps. |
| P1 | `report_missing_illustrations.py` already checks both poses in three source libraries, but defaults to 24 hours and checks file existence only. No artwork scheduler was found in the reviewed scripts. | Durable missing-artwork inventory plus a weekly generation/validation/release job. |
| P1 | `config.php` and `birdnet-status.php` rely on deployment authentication; their optional PHP check only checks for an Authorization header. | Verify actual reverse-proxy protection before adding remote controls; use validated authentication and CSRF protection for writes. This review does not establish whether the deployed app is exposed. |
| P2 | Common names exist in API `com` values but collage names are primarily hover/title text. | Persistent common-name captions that need no interaction. |
| P2 | `cutout.php` can fall back to standard artwork while the browser still uses alternate-library masks. Library readiness checks only directory/metadata existence. | Resolve image, dimensions, and mask together per species/pose, with validated manifests. |
| P2 | Artwork versions are hard-coded in JS; metadata loads at startup. `deploy_library.py` replaces images and metadata in separate steps. | Versioned, complete releases with an atomic active-release switch and automatic browser revision refresh. |
| P2 | Five endpoints are fetched and all views rendered every 30 seconds. `recent` uses a timestamp expression and another best-recording query per species. | Profile on the Pi, reduce unnecessary work, and optimise range queries before changing schema. |
| P2 | Theme/time-window preferences are browser-local. Changing them on a laptop does not configure the Pi browser. | Add server-backed display settings and an independently identified kiosk profile. |
| P3 | Both Python workflows target `main` rather than the documented `upper-brookfield` branch; reviewed CI has no frontend/PHP-specific checks. Documentation retains historical artwork counts and generation comments. | Cover the deployed branch and relevant languages; reconcile operational documentation. |

## 1. Make every detected species visible

Separate detection eligibility from artwork availability. Missing artwork must never remove a species from the display or overnight summary.

- Give missing or corrupt images a neutral silhouette, common name, and discreet “Illustration pending” caption. Avoid substituting another identifiable species.
- Use a rectangular placeholder mask/dimensions so the fallback participates in layout. Catch actual image load failures as well as missing manifest entries.
- If metadata is unavailable, use a simple labelled grid until it recovers. Do not wait indefinitely or run accumulating render timers.
- Distinguish “No birds detected in the past hour,” initial loading, artwork unavailable, and detection service unavailable.
- Treat a quiet microphone differently from failed recording/analysis. A lack of new birds alone is not proof of a fault.

Acceptance: fixtures containing only unknown species, mixed known/unknown species, broken PNGs, and failed metadata requests all retain named, visible birds and recover automatically.

## 2. Weekly missing-artwork process

### Inventory

Extend `avian/scripts/report_missing_illustrations.py` rather than create a competing detector. Add structured JSON output and strict API response validation: an error object or missing `species` array must fail the scan, not report complete coverage.

Track work by canonical scientific name, library, and pose. Reuse the taxonomy mappings in `avian/api/taxonomy.php` consistently across detection, filenames, generation, and reports. Validate both source and actually served assets: readable PNG, meaningful nonempty alpha bounds, expected pose, matching dimensions/mask, and release membership. File existence alone is insufficient.

Build the initial inventory from the lifelist/all history. Thereafter scan a checkpointed interval with overlap and retain unresolved entries; a missed weekly run must not lose birds outside the last 24 hours. Periodically reconcile all history. Store first/last detection, detection count, best confidence, missing parts, attempts, next retry, and status in a small job-state store separate from the detection database.

Suggested states: pending, generating, validating, ready, published, retryable failure, needs review. Low-confidence or questionable identifications should enter a remote review queue under configurable rules. Do not require repeated detections for every species: a single credible owl detection may be the important visitor.

### Schedule and execution

Proposed default: Monday at 10:00 in `Australia/Brisbane`, with a persistent systemd timer to catch up after downtime. The exact time is configurable. This is a deployment job, not a Codex scheduled task, and is only a proposal here.

Keep the inventory and scheduling on the Pi. Prefer an always-available worker for resource-intensive generation/background removal; do not depend on a personal laptop being awake. If the Pi must perform post-processing, run one job at a time with resource limits and benchmark its impact on recording/analysis first.

1. Acquire a process lock, check available disk space, read the deployed release, and scan for gaps.
2. Revalidate that each job is still missing, then select work within configurable species/image and spending limits.
3. Generate only missing poses using the existing `pregen.py` pipeline, explicit output paths, and a versioned prompt for each library. Standard coverage comes first; complete fun/storybook gaps afterwards. Storybook pose semantics are portrait/profile, not automatically perched/flight.
4. Remove backgrounds, build masks, and validate in staging. Reuse `cutout.py`, `build_masks.py`, `verify.py`, and existing deployment validation where suitable. Automated identification is a quality aid, not proof of species accuracy; flagged outputs remain pending review.
5. Publish validated artwork as a complete release; keep existing approved images intact. New standard images may serve as fallbacks while alternate styles remain pending, using standard metadata too.
6. Re-scan the served release and record completed, deferred, failed, and remaining work. Expose last run, next run, queue, and failures in remote administration.

Use timeouts, bounded backoff, resumable checkpoints, and a single-run lock. A generation failure must not interrupt detections or make the screen wait. Keep provider keys outside the web root and browser. Confirm supported model/API configuration and cost at implementation time; do not rely on historical model references in the repository.

### Publishing and cache refresh

Adapt `deploy_library.py` to produce immutable release directories containing images, dimensions, masks, and a manifest with a content revision. Switch one active pointer after validation. The current multi-step image/metadata replacement is not a single atomic release from a browser's perspective.

Expose the release revision through the library API and include it in asset URLs. Pin one revision while fetching image metadata and artwork, then transition together. Poll for revision changes so the kiosk does not need manual cache clearing or a JS version edit. Retain a limited number of known-good releases and support remote rollback.

Acceptance: a species older than seven days is still discovered; one missing pose causes only that pose to be generated; repeat runs do no duplicate work; corrupt assets are detected; a powered-off scheduled run catches up; rate limiting/disk exhaustion leaves the current screen healthy; a successful release appears without human input; rollback restores matching artwork and metadata.

## 3. Common names that work across the room

Keep the illustrated collage, but add an always-visible common-name caption directly below each bird. Start with a modest, high-contrast caption on a quiet background; allow two lines for long names. Show scientific names in detail/atlas views rather than making every caption longer. Use the scientific name as a fallback when `com` is absent.

The packing algorithm currently reserves silhouette cells only. Reserve caption rectangles as occupied space alongside each silhouette, including safe gaps. Simply absolutely positioning text below the current tiles will cause overlaps. Keep captions attached to the same bird as positions change and use safe text-node rendering for names.

Preserve a readable minimum size. When the screen cannot fit all birds at that size, automatically page a stable labelled layout (suggested 15-second dwell, configurable), with a discreet page indicator. Do not shrink names indefinitely or hide birds behind “+N more” requiring a click. Avoid repacking unchanged content every poll.

Suggested initial target on a 1080p landscape screen: captions around 24–28 CSS pixels, adjusted after checking physical viewing distance and display scaling. Test actual screen dimensions before fixing density thresholds. Remote settings can offer labels on/off; the kiosk default is on.

Acceptance: long names, one bird, a busy flock, all three art styles, missing images, portrait/landscape, and dark/light themes remain readable without hover. Captions neither cover neighbouring birds nor leave the viewport. Every paged bird appears automatically within a bounded cycle.

## 4. “Heard last night” in the morning

Keep the one-hour collage as the primary area. Add a compact lower strip with smaller illustrations, common names, and last-heard times. Example content, not a recorded observation:

```text
HEARD RECENTLY                         Past hour

       [Live bird illustrations with common-name captions]

HEARD LAST NIGHT                       6 pm–6 am
  [owl] Southern Boobook · 2:14 am     [bird] …

Updated 7:32 am
```

Suggested configurable defaults:

- Site timezone: `Australia/Brisbane`, shared by detection windows, library schedule, labels, and display settings.
- Overnight interval: previous day 18:00 inclusive to today 06:00 exclusive.
- Morning strip visible: 06:00 inclusive to 12:00 exclusive. Outside this period, hide it automatically.
- Show it alongside the 1H view. Keep 12H/24H/7D/ALL meanings unchanged; avoid a redundant strip in those views.
- Include all eligible overnight species initially, not only owls. Prioritise configurable favourites/nocturnal visitors, then less frequent visitors, with deterministic tie-breaking. Label these as detections rather than confirmed individuals.
- If a species is also in the live hour, show it once in the main area with a small “Also heard last night” annotation. It returns to the overnight strip if it ages out of the live window during the morning.
- Page the overnight strip automatically if necessary, with a fixed height so live birds do not continually move. Hide an empty strip; an unavailable overnight query must not be described as an empty night.

Add a server-side overnight endpoint returning explicit interval boundaries, timezone, server time, canonical species, count, best confidence, and last overnight detection. Keep the top-confidence recording timestamp distinct from the last-heard timestamp. Return offset-bearing timestamps/epoch values so remote browsers do not reinterpret Pi-local timestamps in their own timezone.

Derive overnight data from stored detections, not browser memory: it must work after a morning reboot. Refresh at morning boundaries and during the normal polling lifecycle. Compute bounded timestamp queries centrally; do not approximate “last night” as the previous 12 hours. Longer term, sunrise/sunset windows could be optional, but fixed local hours are easier to understand and test first.

Acceptance: a 02:00 owl appears at 08:00 without being added to the live-hour count; an 18:00 detection belongs to the night and a 06:00 detection does not; the strip expires at noon; rebooting at 09:00 preserves it; duplicate live/overnight species have correct annotations and counts; remote timezone changes do not alter the site's night; failed queries retain clearly dated last-good data or show unavailability.

## 5. Unattended operation and remote UX

### Screen behaviour

- Add a kiosk profile with one-hour default, labels on, morning strip on, and automatic return to the main display after inactivity. Hide navigation chrome where appropriate, while retaining the full interface for remote users.
- Store kiosk settings server-side with validated ranges, a configuration revision, and explicit profile selection. Keep personal browser preferences separate; show when a setting applies to the physical display.
- Display a small last-successful-refresh time. After a proposed two minutes without successful refreshes, show “Updates delayed”; preserve the dated last-good view. Use a separate minimal pipeline-health response so a healthy HTTP server does not imply a working microphone.
- Add fetch timeouts, bounded exponential retry, a single active refresh, and monotonically ordered responses. Recover on connection restoration without requiring a reload. Persist only a small validated snapshot if startup during an outage must work, with its date and freshness clearly shown.
- Preserve reduced-motion support. Avoid replaying entrance animations, resetting audio, or rebuilding hidden atlas/stat views during routine unchanged polls.

### Remote operation

Inspect the actual kiosk startup and service setup before choosing OS changes. Document browser autostart, display power/sleep policy, network reconnection, cursor hiding, and recovery after power loss. Use a supervised browser process with bounded restart/backoff and an observable heartbeat; avoid reboot loops or repeatedly restarting analysis because birds are quiet.

Extend the remote admin view with screen heartbeat/revision, last data refresh, recording/analysis health, selected library/revision, artwork backlog, last/next generation run, and recent failures. Provide authenticated settings and explicit retry/rollback actions. Capture microphone failures independently from the last detection time. Keep expensive diagnostic collection out of the 30-second public polling path.

Verify access controls against the actual deployment: hiding the menu is not authentication. Protect configuration, service controls, and future job controls with validated credentials; use CSRF protection for browser-authenticated writes and narrow service permissions. The passive display should not need administrator credentials just to fetch birds. Do not assume an arbitrary Authorization header is sufficient.

For remote releases, stage and validate first, preserve current configuration and detection data, verify a candidate's health, then switch with a documented rollback command. Test database backups using a SQLite-consistent method. Do not run `scripts/createdb.sh` as a migration: it drops the detections table.

## 6. Performance and maintainability

Measure API latency, query plans, browser render time, memory, and recording continuity on the target Pi before optimising. The database creation script already defines a Date/Time index; inspect whether bounded comparisons can use it instead of evaluating `julianday(Date||' '||Time)` per row. Preserve taxonomy alias grouping and deterministic best-recording selection when reducing per-species queries.

Fetch current detections on the existing 30-second cadence; refresh historical statistics less often or on demand. Use short server-side caching only where its staleness is explicit. Render the active view and mark hidden views dirty for the next visit. Re-layout when membership, relevant weights, screen dimensions, labels, or artwork revision changes rather than rebuilding everything unconditionally.

Correct rolling-window wording: the current `windowLabel()` calls a rolling 24 hours “today” and 168 hours “this week.” Prefer “past 24 hours” and “past 7 days”; use “past hour” consistently. Detection counts represent classifier detections, not necessarily distinct calls or birds.

Add focused tests for timestamp boundaries, missing-assets fallback, queue idempotency, release consistency, and stale-data recovery. Extend CI to the deployed branch and changed PHP/JS/Python paths. Separate display data/state, layout, and admin code incrementally as those areas change; a framework rewrite is unnecessary for this scope.

## Delivery sequence

1. **Confirm deployment facts:** record revision, resolution, browser launch method, timezone agreement between OS/PHP/database, authentication routing, disk headroom, and current performance. Take consistent backups before later changes.
2. **Repair visibility and freshness:** placeholders, metadata recovery, timestamp correctness, truthful loading/empty/offline states, and protected remote controls where verification finds gaps.
3. **Deliver names and morning visitors together:** implement the overnight API, caption-aware layout, overflow paging, and server-backed kiosk settings. Validate on the actual screen from its normal viewing distance.
4. **Automate artwork:** durable inventory, per-style jobs, staging validation, revisioned releases, weekly timer, admin status, and rollback. First run with saved API fixtures and a fake generation provider, then a capped real batch during implementation.
5. **Harden and optimise:** supervised kiosk recovery, measured query/render changes, CI and runbook updates, then a 48-hour soak spanning midnight and the morning boundaries. Separately simulate Friday/weekend artwork transitions and a missed weekly timer run.

Completion means no eligible bird is silently omitted, names require no input, a night visitor survives until the morning cutoff, artwork gaps are processed without manual discovery, and network/service/release failures recover or remain clearly visible to a remote administrator.

## Decisions to confirm during implementation

The defaults above allow work to proceed without a long design questionnaire. Confirm the physical display dimensions, preferred morning hours, generation worker availability/provider budget, and whether new artwork may auto-publish after validation or requires remote visual review. These affect rollout configuration; they do not block the passive review or this plan.
