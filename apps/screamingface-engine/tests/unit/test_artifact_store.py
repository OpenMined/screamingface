"""ArtifactStore: content-addressed spill files for over-threshold results (OME-892).

FEATURE: deliver large results in full instead of cutting them off at 1 MiB.
INVARIANT: the store only ever serves complete, verifiable content — a returned path names
a file whose name IS its sha256, so a corrupted or foreign file is detectable by the same
digest the client checks. Ids that are not lowercase sha256 hex resolve to nothing, so the
store cannot be used to read outside its root.
"""

import hashlib
import os
import time
from pathlib import Path

from screamingface_engine.artifacts import ArtifactStore


def _store(tmp_path: Path) -> ArtifactStore:
    return ArtifactStore(tmp_path / "artifacts")


def test_write_text_returns_content_addressed_ref(tmp_path: Path) -> None:
    body = '{"cases":[' + "1," * 100 + "1]}"
    store = _store(tmp_path)
    ref = store.write_text(body)
    expected = hashlib.sha256(body.encode("utf-8")).hexdigest()
    assert ref.id == expected
    assert ref.sha256 == expected
    assert ref.size_bytes == len(body.encode("utf-8"))
    path = store.path_for(ref.id)
    assert path is not None
    assert path.read_text(encoding="utf-8") == body


def test_write_text_is_idempotent_per_content(tmp_path: Path) -> None:
    # WHY: content addressing makes a re-run of the same result a no-op, not a duplicate.
    store = _store(tmp_path)
    first = store.write_text("same body")
    second = store.write_text("same body")
    assert first == second
    assert len(list((tmp_path / "artifacts").iterdir())) == 1


def test_path_for_rejects_ids_that_are_not_sha256_hex(tmp_path: Path) -> None:
    store = _store(tmp_path)
    (tmp_path / "secret.txt").write_text("nope")
    # INVARIANT: a malformed id can never escape the store root (path traversal guard).
    assert store.path_for("../secret.txt") is None
    assert store.path_for("9F" * 32) is None
    assert store.path_for("9f" * 31) is None


def test_path_for_missing_artifact_is_none(tmp_path: Path) -> None:
    assert _store(tmp_path).path_for("9f" * 32) is None


def test_delete_removes_and_tolerates_absence(tmp_path: Path) -> None:
    store = _store(tmp_path)
    ref = store.write_text("bye")
    store.delete(ref.id)
    assert store.path_for(ref.id) is None
    store.delete(ref.id)  # second delete must not raise


def test_sweep_removes_only_files_older_than_ttl(tmp_path: Path) -> None:
    store = _store(tmp_path)
    stale = store.write_text("stale result")
    fresh = store.write_text("fresh result")
    stale_path = store.path_for(stale.id)
    assert stale_path is not None
    two_days_ago = time.time() - 2 * 86_400
    os.utime(stale_path, (two_days_ago, two_days_ago))
    removed = store.sweep(ttl_seconds=86_400)
    assert removed == 1
    assert store.path_for(stale.id) is None
    assert store.path_for(fresh.id) is not None


def test_sweep_on_missing_root_is_a_noop(tmp_path: Path) -> None:
    assert ArtifactStore(tmp_path / "never-created").sweep(ttl_seconds=1) == 0


def test_sweep_collects_stale_tmp_write_leftovers(tmp_path: Path) -> None:
    # WHY: a crash mid-write leaves a `.tmp` file that `path_for` can never see — without
    # this it would hold real bytes on disk forever, invisible to every other mechanism.
    store = _store(tmp_path)
    store.write_text("anchor")  # ensures the root exists
    orphan = tmp_path / "artifacts" / (".{}.deadbeef.tmp".format("9f" * 32))
    orphan.write_bytes(b"half-written parcel")
    two_days_ago = time.time() - 2 * 86_400
    os.utime(orphan, (two_days_ago, two_days_ago))

    removed = store.sweep(ttl_seconds=86_400)

    assert removed == 1
    assert not orphan.exists()


def test_sweep_tolerates_files_vanishing_mid_scan(tmp_path: Path) -> None:
    # INVARIANT: a file deleted between listing and stat is a completed job, not a crash —
    # the periodic sweeper must survive racing with anything else that removes files.
    store = _store(tmp_path)
    ref = store.write_text("here then gone")
    real_stat = Path.stat

    def racing_stat(self: Path, *, follow_symlinks: bool = True) -> os.stat_result:
        if self.name == ref.id:
            self.unlink(missing_ok=True)  # simulate a concurrent deletion
        return real_stat(self, follow_symlinks=follow_symlinks)

    from unittest.mock import patch

    with patch.object(Path, "stat", racing_stat):
        removed = store.sweep(ttl_seconds=0)
    assert removed >= 0  # no exception is the assertion; count depends on race timing
