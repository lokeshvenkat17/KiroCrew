"""Tests for /api/browse-dirs endpoint."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from kiro_crew.dashboard.handlers import api_browse_dirs


def _make_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/api/browse-dirs", api_browse_dirs)
    return app


@pytest.fixture()
def mock_sel():
    with patch("kiro_crew.dashboard.handlers.sel") as m:
        m.return_value = MagicMock()
        yield m.return_value


class TestBrowseDirs:
    @pytest.mark.asyncio
    async def test_default_path_is_home(self, tmp_path, mock_sel):
        (tmp_path / "projects").mkdir()
        with patch("os.path.expanduser", side_effect=lambda p: p.replace("~", str(tmp_path))):
            async with TestClient(TestServer(_make_app())) as client:
                resp = await client.get("/api/browse-dirs")
                data = await resp.json()
                assert data["path"] == str(tmp_path)
                names = {d["name"] for d in data["dirs"]}
                assert "projects" in names

    @pytest.mark.asyncio
    async def test_lists_subdirectories(self, tmp_path, mock_sel):
        (tmp_path / "alpha").mkdir()
        (tmp_path / "beta").mkdir()
        (tmp_path / "file.txt").write_text("x")
        async with TestClient(TestServer(_make_app())) as client:
            resp = await client.get(f"/api/browse-dirs?path={tmp_path}")
            data = await resp.json()
            names = [d["name"] for d in data["dirs"]]
            assert "alpha" in names
            assert "beta" in names
            assert "file.txt" not in names  # files excluded

    @pytest.mark.asyncio
    async def test_sorted_alphabetically(self, tmp_path, mock_sel):
        (tmp_path / "zebra").mkdir()
        (tmp_path / "apple").mkdir()
        (tmp_path / "mango").mkdir()
        async with TestClient(TestServer(_make_app())) as client:
            resp = await client.get(f"/api/browse-dirs?path={tmp_path}")
            names = [d["name"] for d in (await resp.json())["dirs"]]
            assert names == ["apple", "mango", "zebra"]

    @pytest.mark.asyncio
    async def test_skips_hidden_and_excluded(self, tmp_path, mock_sel):
        (tmp_path / ".git").mkdir()
        (tmp_path / ".hidden").mkdir()
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "__pycache__").mkdir()
        (tmp_path / "src").mkdir()
        async with TestClient(TestServer(_make_app())) as client:
            resp = await client.get(f"/api/browse-dirs?path={tmp_path}")
            names = {d["name"] for d in (await resp.json())["dirs"]}
            assert names == {"src"}

    @pytest.mark.asyncio
    async def test_returns_parent(self, tmp_path, mock_sel):
        child = tmp_path / "child"
        child.mkdir()
        async with TestClient(TestServer(_make_app())) as client:
            resp = await client.get(f"/api/browse-dirs?path={child}")
            data = await resp.json()
            assert data["parent"] == str(tmp_path)

    @pytest.mark.asyncio
    async def test_invalid_path_returns_400(self, mock_sel):
        async with TestClient(TestServer(_make_app())) as client:
            resp = await client.get("/api/browse-dirs?path=/nonexistent_xyz_123")
            assert resp.status == 400

    @pytest.mark.asyncio
    async def test_permission_error_returns_empty_dirs(self, tmp_path, mock_sel):
        restricted = tmp_path / "restricted"
        restricted.mkdir()
        restricted.chmod(0o000)
        try:
            async with TestClient(TestServer(_make_app())) as client:
                resp = await client.get(f"/api/browse-dirs?path={restricted}")
                data = await resp.json()
                assert data["dirs"] == []
        finally:
            restricted.chmod(0o755)

    @pytest.mark.asyncio
    async def test_sensitive_path_is_still_denied(self, tmp_path, mock_sel):
        # The Windows-drive work must not have widened the security gate.
        with patch("kiro_crew.security.is_sensitive_path", return_value=True):
            async with TestClient(TestServer(_make_app())) as client:
                resp = await client.get(f"/api/browse-dirs?path={tmp_path}")
                assert resp.status == 403


class TestBrowseDirsFilesystemRoots:
    """The drives level: Windows has one root per drive and nothing above them.

    Windows behavior is injected at the :mod:`platform_compat` seam rather than
    exercised against real hardware — CI machines have no ``D:``/``E:``, and a
    test that needed them would be unrunnable.
    """

    @pytest.mark.asyncio
    async def test_posix_reports_the_single_root(self, tmp_path, mock_sel):
        with patch("kiro_crew.platform_compat.filesystem_roots", return_value=["/"]):
            async with TestClient(TestServer(_make_app())) as client:
                data = await (await client.get(f"/api/browse-dirs?path={tmp_path}")).json()
        # One root -> the frontend shows no drives level, so POSIX navigation is
        # exactly what it was before.
        assert data["roots"] == [{"name": "/", "path": "/"}]
        assert data["isRoot"] is False

    @pytest.mark.asyncio
    async def test_windows_drives_are_reported_as_roots(self, tmp_path, mock_sel):
        with patch("kiro_crew.platform_compat.filesystem_roots", return_value=["C:\\", "D:\\", "E:\\"]):
            async with TestClient(TestServer(_make_app())) as client:
                data = await (await client.get(f"/api/browse-dirs?path={tmp_path}")).json()
        assert [r["path"] for r in data["roots"]] == ["C:\\", "D:\\", "E:\\"]

    @pytest.mark.asyncio
    async def test_inaccessible_drive_is_absent_from_roots(self, tmp_path, mock_sel):
        # E: is in the machine's drive list but not accessible, so it is never
        # offered — an unusable drive must not reach the picker at all.
        with patch("kiro_crew.platform_compat.filesystem_roots", return_value=["C:\\", "D:\\"]):
            async with TestClient(TestServer(_make_app())) as client:
                data = await (await client.get(f"/api/browse-dirs?path={tmp_path}")).json()
        assert [r["path"] for r in data["roots"]] == ["C:\\", "D:\\"]

    @pytest.mark.asyncio
    async def test_root_listing_is_flagged(self, tmp_path, mock_sel):
        # A listing whose own parent is itself (a drive root, or POSIX `/`) is
        # flagged so the browser can offer the drives level instead of a dead Back.
        with patch("kiro_crew.platform_compat.is_filesystem_root", return_value=True), \
                patch("kiro_crew.platform_compat.filesystem_roots", return_value=["C:\\", "D:\\"]):
            async with TestClient(TestServer(_make_app())) as client:
                data = await (await client.get(f"/api/browse-dirs?path={tmp_path}")).json()
        assert data["isRoot"] is True

    @pytest.mark.asyncio
    async def test_roots_probe_failure_does_not_break_browsing(self, tmp_path, mock_sel):
        (tmp_path / "alpha").mkdir()
        # Losing the drive list must degrade to "no drives listed", never fail the
        # request — the directory the user asked for still enumerates.
        with patch("kiro_crew.platform_compat.filesystem_roots", return_value=[]):
            async with TestClient(TestServer(_make_app())) as client:
                resp = await client.get(f"/api/browse-dirs?path={tmp_path}")
                data = await resp.json()
        assert resp.status == 200
        assert data["roots"] == []
        assert [d["name"] for d in data["dirs"]] == ["alpha"]


class TestBrowseDirsEnumerationRobustness:
    """Navigating into a drive's directories, including the awkward names."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "name",
        [
            "My Projects",            # spaces
            "Program Files (x86)",    # spaces + parentheses
            "prøjekt-ünïcode-日本語",  # non-ASCII
            "trailing space ",        # a name the shell would mangle
        ],
    )
    async def test_awkward_directory_names_enumerate(self, tmp_path, mock_sel, name):
        (tmp_path / name).mkdir()
        async with TestClient(TestServer(_make_app())) as client:
            data = await (await client.get(f"/api/browse-dirs?path={tmp_path}")).json()
        entry = next(d for d in data["dirs"] if d["name"] == name)
        # The path is returned verbatim so the frontend can send it straight back.
        assert entry["path"].endswith(name)

    @pytest.mark.asyncio
    async def test_nested_navigation_reports_the_real_parent(self, tmp_path, mock_sel):
        nested = tmp_path / "Kiro" / "KiroCrew"
        nested.mkdir(parents=True)
        (nested / "src").mkdir()
        async with TestClient(TestServer(_make_app())) as client:
            data = await (await client.get(f"/api/browse-dirs?path={nested}")).json()
        assert data["parent"] == str(tmp_path / "Kiro")
        assert [d["name"] for d in data["dirs"]] == ["src"]
        assert data["isRoot"] is False

    @pytest.mark.asyncio
    async def test_empty_directory_lists_nothing_and_succeeds(self, tmp_path, mock_sel):
        empty = tmp_path / "empty"
        empty.mkdir()
        async with TestClient(TestServer(_make_app())) as client:
            resp = await client.get(f"/api/browse-dirs?path={empty}")
            assert resp.status == 200
            assert (await resp.json())["dirs"] == []

    @pytest.mark.asyncio
    async def test_one_unreadable_entry_does_not_blank_its_siblings(self, tmp_path, mock_sel):
        # A Windows drive root holds entries that refuse to stat (System Volume
        # Information, stale reparse points). Isolation is per ENTRY: the rest of
        # the listing must survive.
        for name in ("alpha", "broken", "zeta"):
            (tmp_path / name).mkdir()
        real_scandir = os.scandir

        def _scandir(path):
            for entry in real_scandir(path):
                yield _Exploding(entry) if entry.name == "broken" else entry

        with patch("os.scandir", side_effect=_scandir):
            async with TestClient(TestServer(_make_app())) as client:
                data = await (await client.get(f"/api/browse-dirs?path={tmp_path}")).json()
        assert [d["name"] for d in data["dirs"]] == ["alpha", "zeta"]

    @pytest.mark.asyncio
    async def test_windows_hidden_and_system_entries_are_skipped(self, tmp_path, mock_sel):
        # Windows marks these by ATTRIBUTE, not by a leading dot, so without the
        # attribute check `$RECYCLE.BIN` clutters every drive root.
        (tmp_path / "$RECYCLE.BIN").mkdir()
        (tmp_path / "System Volume Information").mkdir()
        (tmp_path / "Kiro").mkdir()
        hidden = {"$RECYCLE.BIN", "System Volume Information"}
        with patch(
            "kiro_crew.platform_compat.entry_is_hidden_or_system",
            side_effect=lambda entry: entry.name in hidden,
        ):
            async with TestClient(TestServer(_make_app())) as client:
                data = await (await client.get(f"/api/browse-dirs?path={tmp_path}")).json()
        assert [d["name"] for d in data["dirs"]] == ["Kiro"]

    @pytest.mark.asyncio
    async def test_unreadable_directory_returns_empty_not_500(self, tmp_path, mock_sel):
        with patch("os.scandir", side_effect=OSError("device not ready")):
            async with TestClient(TestServer(_make_app())) as client:
                resp = await client.get(f"/api/browse-dirs?path={tmp_path}")
                assert resp.status == 200
                assert (await resp.json())["dirs"] == []

    @pytest.mark.asyncio
    async def test_nonexistent_drive_style_path_returns_400(self, mock_sel):
        # What the browser gets when a drive vanished between listing and click.
        async with TestClient(TestServer(_make_app())) as client:
            resp = await client.get("/api/browse-dirs?path=Q:\\definitely\\not\\here")
            assert resp.status == 400


class _Exploding:
    """A DirEntry whose ``is_dir`` raises, as an unreadable entry's does."""

    def __init__(self, entry):
        self.name = entry.name
        self.path = entry.path

    def is_dir(self, follow_symlinks: bool = True) -> bool:
        raise OSError("cannot stat")
