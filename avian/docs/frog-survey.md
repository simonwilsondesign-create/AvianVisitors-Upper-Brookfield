# Native frog survey collector

The first frog-monitoring stage is collection only. BirdNET continues to own
the microphone. Every two seconds, the collector reads completed 15-second WAV
files from `/home/pi/BirdSongs/StreamData`, keeps recordings made from 17:00
through 08:59 Brisbane time, and stores mono 48 kHz FLAC copies under
`/var/lib/avian-frog/recordings/YYYY-MM-DD/`.

It does not claim frog species or issue frog notifications. The archive retains
seven days so calls can be reviewed before a local, native-frog recogniser is
trained and tested. Its SQLite index is `/var/lib/avian-frog/state.sqlite`.

Install on the Pi:

```sh
sudo install -d -o pi -g pi /var/lib/avian-frog
sudo install -m 0644 avian/systemd/avian-frog-survey.service avian/systemd/avian-frog-survey.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now avian-frog-survey.timer
```
