Game soundtrack: `CLS No. 1 I in G Major 2nd rev.mp3`, supplied by the user.

`cls-no-1-g-major.mp4` contains stereo AAC audio only (no video), about 4:52.
The MP4 container is already supported by the game's public asset allowlist.
The original is 4,856,323 bytes; this version is 2,421,733 bytes (50.1% smaller).

Encoded on macOS with its built-in AAC encoder:

```sh
afconvert 'CLS No. 1 I in G Major 2nd rev.mp3' cls-no-1-g-major.mp4 -f mp4f -d aac -b 64000 -q 127 -s 2
```

`app.js` loads the shared music controls. The audio is fetched only after music
is enabled. Playback loops, pauses in hidden tabs, and resumes the saved position
when navigating within the same tab. Preferences persist in local storage;
position uses session storage. Browsers can require another Play click on a new
page. Music starts off, at 30% volume. The settings button controls the volume.

Upload with the game assets. Render needs Manual Deploy; no class reset is needed.

Playback behavior regression checks: `node --test tests/test_game_music.cjs`.
