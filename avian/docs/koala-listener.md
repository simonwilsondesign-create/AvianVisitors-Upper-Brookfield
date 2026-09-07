# Koala listener

The koala listener is a separate, review-first analysis path. BirdNET remains
the only process that owns the microphone and runs continuously. The koala
recogniser reads each closed BirdNET WAV file afterwards, so no evening bird
calls are missed while a second model runs.

## Schedule

Read `LATITUDE`, `LONGITUDE`, `RECS_DIR`, and `RECORDING_LENGTH` from
`/etc/birdnet/birdnet.conf`. Calculate the local sun events in
`Australia/Brisbane` using the installed `suntime` package. Process files only
from one hour after sunset until the next sunrise. Files outside that window
are recorded as intentionally skipped, rather than silently lost.

The installed Pi configuration is `-27.4704, 153.026`, with 15-second WAVs in
`/home/pi/BirdSongs/StreamData`.

## Recogniser and review

Use the unmodified NSW DPIRD `Koala_CNN_LG_071223` AviaNZ 3.2.3 recogniser.
Its licence is CC BY-NC 4.0 and requires attribution to NSW Department of
Primary Industries and Regional Development. Store it outside the web root and
do not adapt its files.

The recogniser identifies male bellows. Treat each result as a candidate until
the linked WAV is reviewed: the publisher identifies trucks, trains, and
kookaburras as possible false positives. A candidate can appear in a separate
"Koala heard overnight" display item, with the detection time, score, source
recording and a review status. Only reviewed candidates count as a confirmed
koala observation.

## Installation boundary

AviaNZ and the DPIRD recogniser must be installed in their own environment
under `/opt/avian-koala`; do not add their packages to BirdNET's environment.
The koala service must have read-only access to BirdNET recordings and write
only to `/var/lib/avian-koala`. A systemd timer should run every two minutes,
with a lock and checkpoint database, after the recording service has started.

The published recogniser is intended for offline WAV analysis. Verify a small,
saved recording set on the Pi before enabling the scheduled listener, then
inspect every initial candidate in the review queue.
