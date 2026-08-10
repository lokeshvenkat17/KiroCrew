"""Tests for the filesystem-root shims in :mod:`kiro_crew.platform_compat`.

Windows has one filesystem root per drive and nothing above them, so a directory
browser that only walks up parents can never leave the drive it started on.
These cover the discovery mechanism for that missing level.

Every Windows behavior here is exercised from ANY host: the drive bitmask, the
platform flags and the accessibility probe are all injected, because CI machines
have no ``D:``/``E:`` and asserting against real hardware would make the suite
depend on the runner's disk layout.
"""

from __future__ import annotations

import contextlib
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from kiro_crew import platform_compat


@pytest.fixture(autouse=True)
def _clear_roots_cache():
    """Drop the TTL cache around every test so one test's roots never leak."""
    platform_compat._roots_cache = None
    yield
    platform_compat._roots_cache = None


def _drive_mask(*letters: str) -> int:
    """The ``GetLogicalDrives`` bitmask for the given drive letters."""
    return sum(1 << platform_compat._DRIVE_LETTERS.index(letter) for letter in letters)


def _fake_windll(mask: int) -> MagicMock:
    windll = MagicMock()
    windll.kernel32.GetLogicalDrives.return_value = mask
    return windll


@contextlib.contextmanager
def _kernel32_reporting(*letters: str):
    """Patch in a Windows kernel32 whose drive bitmask holds *letters*."""
    fake = _fake_windll(_drive_mask(*letters))
    with patch.object(platform_compat.ctypes, "windll", fake, create=True):
        yield


@contextlib.contextmanager
def _windows_host(candidates: list[str], isdir):
    """Present a Windows host whose drive candidates probe through *isdir*."""
    with patch.object(platform_compat, "IS_POSIX", False), \
            patch.object(platform_compat, "_windows_drive_roots", return_value=candidates), \
            patch("os.path.isdir", side_effect=isdir):
        yield


@contextlib.contextmanager
def _counting_windows_host(candidates: list[str]):
    """As :func:`_windows_host`, yielding the drive-enumeration mock to count calls."""
    with patch.object(platform_compat, "IS_POSIX", False), \
            patch.object(platform_compat, "_windows_drive_roots", return_value=candidates) as m, \
            patch("os.path.isdir", return_value=True):
        yield m


class TestWindowsDriveRoots:
    def test_decodes_bitmask_into_drive_roots(self):
        with _kernel32_reporting("C", "D", "E"):
            assert platform_compat._windows_drive_roots() == ["C:\\", "D:\\", "E:\\"]

    def test_non_contiguous_drives(self):
        # A machine with C: and Z: and nothing between must not report the gap.
        with _kernel32_reporting("C", "Z"):
            assert platform_compat._windows_drive_roots() == ["C:\\", "Z:\\"]

    def test_no_drive_letter_is_hardcoded(self):
        # An empty mask yields NO drives — proof that C:\ is discovered, never assumed.
        with _kernel32_reporting():
            assert platform_compat._windows_drive_roots() == []

    def test_falls_back_to_full_alphabet_when_kernel32_unreachable(self):
        windll = MagicMock()
        windll.kernel32.GetLogicalDrives.side_effect = OSError("boom")
        with patch.object(platform_compat.ctypes, "windll", windll, create=True):
            roots = platform_compat._windows_drive_roots()
        # Every letter becomes a CANDIDATE for the caller to probe; nothing is
        # claimed to exist, and no specific letter is privileged.
        assert len(roots) == 26
        assert roots[0] == "A:\\" and roots[-1] == "Z:\\"


class TestFilesystemRoots:
    def test_posix_returns_single_root(self):
        with patch.object(platform_compat, "IS_POSIX", True):
            assert platform_compat.filesystem_roots() == ["/"]

    def test_windows_returns_only_accessible_drives(self):
        # D: is present in the bitmask but inaccessible (empty card reader,
        # disconnected mapping) — it must not be offered.
        accessible = {"C:\\", "E:\\"}
        with _windows_host(["C:\\", "D:\\", "E:\\"], lambda p: p in accessible):
            assert platform_compat.filesystem_roots() == ["C:\\", "E:\\"]

    def test_drive_that_raises_on_stat_is_skipped_not_fatal(self):
        def _isdir(path: str) -> bool:
            if path == "D:\\":
                raise OSError("device not ready")
            return True

        with _windows_host(["C:\\", "D:\\"], _isdir):
            assert platform_compat.filesystem_roots() == ["C:\\"]

    def test_all_drives_inaccessible_returns_empty_without_raising(self):
        with _windows_host(["C:\\"], lambda p: False):
            assert platform_compat.filesystem_roots() == []

    def test_result_is_cached_so_navigation_does_not_reprobe(self):
        with _counting_windows_host(["C:\\"]) as drives:
            first = platform_compat.filesystem_roots()
            second = platform_compat.filesystem_roots()
        assert first == second == ["C:\\"]
        assert drives.call_count == 1

    def test_cache_expires(self):
        with _counting_windows_host(["C:\\"]) as drives:
            platform_compat.filesystem_roots()
            # Expire the entry by rewinding its deadline rather than sleeping, so
            # the test asserts the TTL contract without paying wall-clock time.
            deadline, roots = platform_compat._roots_cache  # type: ignore[misc]
            platform_compat._roots_cache = (deadline - platform_compat._ROOTS_TTL_SECS - 1, roots)
            platform_compat.filesystem_roots()
        assert drives.call_count == 2

    def test_caller_cannot_mutate_the_cache(self):
        with _windows_host(["C:\\"], lambda p: True):
            platform_compat.filesystem_roots().append("Q:\\")
            assert platform_compat.filesystem_roots() == ["C:\\"]


class TestIsFilesystemRoot:
    @pytest.mark.parametrize("path", ["C:\\", "D:\\", "E:\\", "\\\\server\\share\\"])
    def test_windows_roots(self, path):
        with patch.object(platform_compat, "IS_WINDOWS", True):
            assert platform_compat.is_filesystem_root(path) is True

    @pytest.mark.parametrize("path", ["D:\\Kiro", "D:\\Kiro\\KiroCrew", "C:\\Users\\me"])
    def test_windows_non_roots(self, path):
        with patch.object(platform_compat, "IS_WINDOWS", True):
            assert platform_compat.is_filesystem_root(path) is False

    def test_posix_root_and_non_roots(self):
        with patch.object(platform_compat, "IS_WINDOWS", False):
            assert platform_compat.is_filesystem_root("/") is True
            assert platform_compat.is_filesystem_root("/home/me") is False

    def test_windows_path_is_not_a_root_on_a_posix_gateway(self):
        # A backslash path means nothing to a POSIX gateway — the flavour comes
        # from the platform, not from the string.
        with patch.object(platform_compat, "IS_WINDOWS", False):
            assert platform_compat.is_filesystem_root("C:\\") is False

    def test_empty_path_is_not_a_root(self):
        assert platform_compat.is_filesystem_root("") is False


class TestEntryIsHiddenOrSystem:
    @staticmethod
    def _entry(attrs: int | None = None, error: type[Exception] | None = None):
        entry = MagicMock()
        if error is not None:
            entry.stat.side_effect = error("nope")
        else:
            entry.stat.return_value = SimpleNamespace(st_file_attributes=attrs)
        return entry

    def test_posix_never_reports_hidden(self):
        with patch.object(platform_compat, "IS_POSIX", True):
            # Even an entry carrying the attribute bits: on POSIX hiding is a
            # naming convention the caller already handles.
            assert platform_compat.entry_is_hidden_or_system(self._entry(attrs=0x2)) is False

    @pytest.mark.parametrize("attrs", [0x2, 0x4, 0x6])
    def test_windows_hidden_or_system(self, attrs):
        with patch.object(platform_compat, "IS_POSIX", False):
            assert platform_compat.entry_is_hidden_or_system(self._entry(attrs=attrs)) is True

    def test_windows_ordinary_directory(self):
        with patch.object(platform_compat, "IS_POSIX", False):
            assert platform_compat.entry_is_hidden_or_system(self._entry(attrs=0x10)) is False

    @pytest.mark.parametrize("error", [OSError, AttributeError])
    def test_unreadable_attributes_are_not_treated_as_hidden(self, error):
        # Fail OPEN here on purpose: dropping an entry whose attributes cannot be
        # read would hide real project directories, and the caller's own
        # permission and sensitivity checks still apply.
        with patch.object(platform_compat, "IS_POSIX", False):
            assert platform_compat.entry_is_hidden_or_system(self._entry(error=error)) is False
