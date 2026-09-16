Game soundtrack: Shy FX — This Style, supplied by the user as
`Shy_FX_-_This_Style_(mp3.pm).mp3`.

`shy-fx-this-style.mp4` contains stereo AAC audio only (no video), about 5:32,
at 32 kHz and approximately 72 kbps.
The MP4 container is already supported by the game's public asset allowlist.
The original is 9,297,965 bytes; this version is 2,997,198 bytes (3.00 MB,
67.8% smaller). The full track is preserved.

Encoded on macOS with its built-in AAC encoder:

```sh
afconvert 'Shy_FX_-_This_Style_(mp3.pm).mp3' shy-fx-this-style.mp4 -f mp4f -d aac -b 72000 -q 127 -s 1
```

`app.js` loads the shared music controls. The audio is fetched only after music
is enabled. Playback loops, pauses in hidden tabs, and resumes the saved position
when navigating within the same tab. Preferences persist in local storage;
position uses a track-specific session storage key, so switching tracks starts
from the beginning. Browsers can require another Play click on a new
page. Music starts off, at 30% volume. The settings button controls the volume.

Upload with the game assets. Render needs Manual Deploy; no class reset is needed.

Playback behavior regression checks: `node --test tests/test_game_music.cjs`.
