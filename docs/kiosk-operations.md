# Kiosk operations

The display runs without an administrator login. Its read-only configuration is
available at `/avian/api/display-config.php`; that endpoint is suitable for the
kiosk's normal polling. A successful response only means the display settings
were read. It does not establish microphone, recorder, analyser, or artwork-job
health.

## Configure persistent settings

Create a directory outside the web root and make it writable only by the PHP
service account. On the deployed Pi this is normally `caddy`:

```sh
sudo install -d -o caddy -g caddy -m 0750 /var/lib/avian
```

Set these PHP-FPM environment values (for example in its pool configuration or
the deployment environment), then reload PHP-FPM:

```text
AV_DISPLAY_SETTINGS_PATH=/var/lib/avian/display-settings.json
AV_TIMEZONE=Australia/Brisbane
AV_DISPLAY_SETTINGS_TOKEN=<long random secret>
```

`AV_TIMEZONE` is authoritative for the display, its overnight boundaries, and
the overnight API. An invalid value falls back to `Australia/Brisbane`.

The settings file is written with a temporary file and atomic rename. Do not
place it under the Caddy document root or edit it while the API is writing it.
Back it up with the rest of the deployment configuration, not the detection
database.

The default kiosk profile is:

```json
{"profile":"kiosk","labels":true,"overnight_enabled":true,"night_start_hour":18,"night_end_hour":6,"morning_end_hour":9,"page_seconds":15,"theme":"light","default_hours":1,"kiosk_idle_seconds":120,"timezone":"Australia/Brisbane","revision":0}
```

Writes are `POST` JSON requests to the same endpoint. They accept only the
listed settings (timezone and profile are server-managed), validate strict JSON
types and ranges, and can include `expected_revision` to prevent overwriting a
newer remote change. Supply the configured secret in
`X-Avian-Display-Token`; an arbitrary `Authorization` header does not authorize
a write. This custom header also prevents cross-site form writes.

For browser-admin authentication instead of a token, configure the reverse
proxy to authenticate this path and to pass a verified `REMOTE_USER` to PHP.
Only then set `AV_DISPLAY_TRUST_PROXY_AUTH=1`. Browser-authenticated writes
also require same-origin requests and a matching `X-Avian-CSRF` value from the
`av_display_csrf` cookie returned on an authenticated GET. Do not set the trust
flag merely because an Authorization header reaches PHP.

## Night and morning scene

The overnight scene accumulates detections from `night_start_hour` (18:00 by
default). At local sunrise, those visitors move to the left and birds heard
since sunrise within the past hour appear on the right. At `morning_end_hour`
(09:00 by default), the overnight section clears. Stored detections restore the
scene after a morning restart. Sunrise uses the site's BirdNET latitude and
longitude; `night_end_hour` remains a legacy setting, not the dawn boundary.

Koalas occupy reserved space beside the bird area. The listener runs throughout
the day; recent candidates appear for an hour, and overnight candidates carry
through the morning cutoff. Unreviewed candidates are labelled “Possible koala”.
See [koala listener operations](../avian/docs/koala-listener.md) for saved audio
and history. Existing detections whose audio has already rotated away cannot
have their recordings recovered by this change.

For a release, update the frontend HTML, JavaScript and CSS together with the
API files and koala worker. Include `koala-recording.php`, grant the PHP service
read access to preserved candidate WAVs, and reload the kiosk browser. Verify
night, dawn, 09:00 and daytime-koala fixtures before checking the physical
display and the next worker run on the Pi.

## Check and recover the display

`GET /avian/api/display-config.php` returns `settings`, a small configuration
`health` object, and site-local `server_time`. A `health.status` other than
`ok` means the settings store is unreadable, malformed, or unsafe. It is not a
pipeline diagnostic. Keep recorder/analyser health checks separate from the
30-second public display poll.

Run the kiosk browser as a supervised user service with a bounded restart
policy. Its startup command should open the kiosk profile directly, hide the
cursor, and disable display sleep according to the installed desktop's supported
mechanism. Before deploying, record the actual browser command, display
resolution/orientation, and the service unit used on that Pi. After a power
loss, verify the browser process, network association, Caddy/PHP-FPM, recording,
and analysis services in that order. Do not restart analysis merely because no
birds have been detected recently.

When the display reports delayed updates, preserve its dated last-good view and
check network reachability, then the lightweight API health, then recorder and
analysis service logs. Test a candidate release against these checks before
switching it. Keep the previous release and settings file available so rollback
means switching back, never recreating the detection database. In particular,
do not use `scripts/createdb.sh` as a migration or recovery command: it drops
the detections table.
