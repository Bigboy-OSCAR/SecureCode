from pathlib import Path

from securecode_context.pointers.source.store import SourceStore


def test_source_register_and_read(tmp_path: Path):
    file_path = tmp_path / "sample.txt"
    file_path.write_text("line1\nline2\nline3")

    store = SourceStore(root_dir=str(tmp_path))
    source_id = store.register("sample.txt", workspace_id="w1")

    result = store.read(
        source_id=source_id,
        workspace_id="w1",
        start_line=2,
        end_line=3,
    )

    assert result == "line2\nline3"
