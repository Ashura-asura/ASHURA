import json
import zipfile
from pathlib import Path

import pytest

from brain.tools import ToolRegistry, task_needs_tools
from skills.perception.documents import (SUPPORTED_SUFFIXES, document_info,
                                         extract_file)


def make_docx(path: Path, text: str) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f'<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>'
        ))


def make_pptx(path: Path, text: str) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("ppt/slides/slide1.xml", (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
            'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
            f'<p:cSld><p:spTree><a:p><a:r><a:t>{text}</a:t></a:r></a:p></p:spTree></p:cSld></p:sld>'
        ))


def make_odt(path: Path, text: str) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("content.xml", (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<office:document-content '
            'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
            'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">'
            f'<office:body><text:p>{text}</text:p></office:body></office:document-content>'
        ))


def test_document_info_classifies_supported_and_unsupported_files():
    assert document_info("report.pdf").kind == "pdf"
    assert document_info("scan.PNG").kind == "image"
    assert document_info("notes.docx").kind == "office"
    assert document_info("page.html").kind == "text"
    assert document_info("payload.exe").kind == "unsupported"
    assert ".pdf" in SUPPORTED_SUFFIXES
    assert ".py" in SUPPORTED_SUFFIXES


def test_extract_plain_text_and_markdown(tmp_path):
    target = tmp_path / "notes.md"
    target.write_text("# Heading\n\nSome body text.", encoding="utf-8")
    result = extract_file(target)
    assert result.ok is True
    assert "Some body text." in result.text
    assert result.document_type == "text"
    assert result.verified is False


def test_extract_html_strips_scripts_and_reports_title(tmp_path):
    target = tmp_path / "page.html"
    target.write_text(
        "<html><head><title>Example title</title><style>.x{}</style></head>"
        "<body><h1>Visible</h1><script>alert('no')</script><p>Body copy.</p></body></html>",
        encoding="utf-8",
    )
    result = extract_file(target)
    assert result.ok is True
    assert "Visible" in result.text
    assert "Body copy." in result.text
    assert "alert('no')" not in result.text
    assert ".x{}" not in result.text


def test_extract_docx_pptx_and_odt_with_stdlib_only(tmp_path):
    docx = tmp_path / "letter.docx"
    make_docx(docx, "Hello from DOCX")
    result = extract_file(docx)
    assert result.ok is True
    assert "Hello from DOCX" in result.text
    assert "docx" in result.engine

    pptx = tmp_path / "deck.pptx"
    make_pptx(pptx, "Slide title")
    result = extract_file(pptx)
    assert result.ok is True
    assert "Slide title" in result.text
    assert result.pages == 1

    odt = tmp_path / "page.odt"
    make_odt(odt, "OpenDocument text")
    result = extract_file(odt)
    assert result.ok is True
    assert "OpenDocument text" in result.text


def test_a_fake_pdf_magic_byte_mismatch_is_reported_not_invented(tmp_path):
    fake = tmp_path / "fake.pdf"
    fake.write_bytes(b"this is not a pdf")
    result = extract_file(fake)
    assert result.ok is False
    assert "does not match" in result.reason


def test_office_archive_must_match_its_extension(tmp_path):
    fake = tmp_path / "fake.docx"
    with zipfile.ZipFile(fake, "w") as archive:
        archive.writestr("unrelated.xml", "<x/>")
    result = extract_file(fake)
    assert result.ok is False
    assert "archive content" in result.reason


def test_binary_text_file_is_refused(tmp_path):
    target = tmp_path / "binary.txt"
    target.write_bytes(b"text\x00with\x00nulls")
    result = extract_file(target)
    assert result.ok is False
    assert "binary" in result.reason


def test_unsupported_suffix_is_refused(tmp_path):
    target = tmp_path / "program.exe"
    target.write_bytes(b"MZ")
    result = extract_file(target)
    assert result.ok is False
    assert "unsupported file type" in result.reason


def test_tool_registry_lists_and_reads_inside_the_workspace(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("needle = 42\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    registry = ToolRegistry(tmp_path)

    listing = json.loads(registry.execute("list_files", {"path": ".", "pattern": "*.md"}).output)
    assert [entry["path"] for entry in listing["entries"]] == ["README.md"]

    read = registry.execute("read_text_file", {"path": "src/app.py"})
    assert read.ok is True
    assert "needle = 42" in json.loads(read.output)["text"]

    found = json.loads(registry.execute("search_text", {"query": "needle"}).output)
    assert found["matches"][0]["path"] == "src/app.py"

    info = json.loads(registry.execute("file_info", {"path": "README.md"}).output)
    assert info["bytes"] == (tmp_path / "README.md").stat().st_size
    assert info["lines"] >= 1
    assert len(info["sha256_prefix"]) == 16


def test_tool_registry_refuses_traversal_binary_and_unknown_tools(tmp_path):
    outside = tmp_path.parent / "outside-secret.txt"
    outside.write_text("secret", encoding="utf-8")
    (tmp_path / "data.bin").write_bytes(b"\x00\x01\x02")
    registry = ToolRegistry(tmp_path)

    escaped = registry.execute("read_text_file", {"path": "../outside-secret.txt"})
    assert escaped.ok is False
    assert "escapes" in escaped.error

    binary = registry.execute("read_text_file", {"path": "data.bin"})
    assert binary.ok is False
    assert "non-text" in binary.error

    unknown = registry.execute("run_shell", {"command": "dir"})
    assert unknown.ok is False
    assert "unknown tool" in unknown.error


def test_tool_calculate_and_note_sandbox(tmp_path):
    registry = ToolRegistry(tmp_path)
    result = registry.execute("calculate", {"expression": "37*24+19"})
    assert result.ok is True
    assert json.loads(result.output)["value"] == "907"

    written = registry.execute("write_note", {"name": "observation.md", "content": "hello"})
    assert written.ok is True
    assert (tmp_path / "data" / "agent" / "observation.md").read_text(encoding="utf-8") == "hello"

    rejected = registry.execute("write_note", {"name": "../escape.md", "content": "no"})
    assert rejected.ok is False
    assert not (tmp_path / "escape.md").exists()


def test_create_directory_uses_requested_workspace_path_and_refuses_escape(tmp_path):
    registry = ToolRegistry(tmp_path)
    result = registry.execute("create_directory", {"path": "projects/circuit notes"})
    assert result.ok is True
    payload = json.loads(result.output)
    assert payload["path"] == "projects/circuit notes"
    assert payload["created"] is True
    assert (tmp_path / "projects" / "circuit notes").is_dir()
    assert registry.execute("create_directory", {"path": "../outside"}).ok is False
    assert registry.execute("create_directory", {"path": ".git/hooks"}).ok is False


def test_task_needs_tools_only_for_environment_requests():
    assert task_needs_tools("List the files in this repository") is True
    assert task_needs_tools("What time is it?") is True
    assert task_needs_tools("Search the codebase for extract_file") is True
    assert task_needs_tools("Explain how you route a question") is False
    assert task_needs_tools("What is the capital of France?") is False


def test_tools_do_not_search_through_symlinks(tmp_path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    outside.write_text("outside secret needle", encoding="utf-8")
    link = tmp_path / "linked.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("creating symlinks requires elevated privileges on Windows")
    registry = ToolRegistry(tmp_path)
    found = json.loads(registry.execute("search_text", {"query": "needle"}).output)
    assert found["matches"] == []
    listing = json.loads(registry.execute("list_files", {"path": "."}).output)
    assert all(entry["path"] != "linked.txt" for entry in listing["entries"])
