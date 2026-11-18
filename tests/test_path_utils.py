from pathlib import Path

from utils.path_utils import resolve_path


def test_virtual_prefix_cleaned(tmp_path):
    session = str(tmp_path / "output" / "session_1")
    assert resolve_path("/workspace/report.md", session) == str(Path(session) / "report.md")


def test_updated_special_resolves_to_cwd_relative():
    result = resolve_path("abc/updated/upload/file.pdf")
    parts = Path(result).parts
    assert "updated" in parts
    assert Path(result).name == "file.pdf"


def test_no_session_dir_resolves_to_cwd():
    assert resolve_path("sub/test.md", None) == str((Path.cwd() / "sub/test.md").resolve())


def test_relative_joins_session(tmp_path):
    session = str(tmp_path / "output" / "session_1")
    assert resolve_path("sub1/sub2/test.md", session) == str(Path(session) / "sub1" / "sub2" / "test.md")


def test_session_name_dedup(tmp_path):
    session = str(tmp_path / "output" / "session_1")
    assert resolve_path("session_1/report.md", session) == str(Path(session) / "report.md")


def test_output_prefix_joins_session(tmp_path):
    session = str(tmp_path / "output" / "session_1")
    assert resolve_path("output/report.md", session) == str(Path(session) / "report.md")


def test_absolute_inside_session(tmp_path):
    session = str(tmp_path / "output" / "session_1")
    inner = str(Path(session) / "sub" / "report.md")
    assert resolve_path(inner, session) == inner


def test_absolute_outside_session_preserved(tmp_path):
    session = str(tmp_path / "output" / "session_1")
    outside = str(tmp_path / "OtherDir" / "file.md")
    assert resolve_path(outside, session) == outside
