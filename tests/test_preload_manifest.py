"""The loading screen must cover the complete shipped game media pack."""

from __future__ import annotations

import preload_manifest


def test_manifest_contains_every_public_media_asset():
    manifest = preload_manifest.build()
    paths = {url.split("?", 1)[0] for url, _ in manifest["all"]}
    expected = {path.relative_to(preload_manifest.ROOT).as_posix()
                for path in preload_manifest.assets()}

    assert paths == expected
    assert sum(path.stat().st_size for path in preload_manifest.assets()) > 160_000_000
    assert preload_manifest.render(manifest) == preload_manifest.OUT.read_text()
