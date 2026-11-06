import os
import stat
import sys

import pytest

from app.token_store import (TOKEN_MIN_LENGTH, TokenStoreError, default_token_path,
                             load_or_create_token)


def test_creates_then_reuses_a_token(tmp_path):
    path = tmp_path / "data" / "web_token"
    first = load_or_create_token(path)
    assert first.created is True
    assert first.path == path
    assert len(first.token) >= TOKEN_MIN_LENGTH
    assert path.read_text(encoding="utf-8").strip() == first.token

    second = load_or_create_token(path)
    assert second.created is False
    assert second.token == first.token


def test_replaces_an_empty_or_malformed_token(tmp_path):
    path = tmp_path / "web_token"
    path.write_text("short\n", encoding="utf-8")
    replaced = load_or_create_token(path)
    assert replaced.created is True
    assert len(replaced.token) >= TOKEN_MIN_LENGTH
    assert path.read_text(encoding="utf-8").strip() == replaced.token

    path.write_text("has whitespace inside\n", encoding="utf-8")
    replaced_again = load_or_create_token(path)
    assert replaced_again.created is True
    assert replaced_again.token != "has whitespace inside"


def test_token_file_has_restrictive_mode_on_posix(tmp_path):
    if os.name != "posix":
        pytest.skip("POSIX permissions are not available on this platform")
    path = tmp_path / "nested" / "web_token"
    stored = load_or_create_token(path)
    assert stored.created is True
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode & 0o077 == 0, f"token file mode {mode:04o} is too open"
    directory_mode = stat.S_IMODE(path.parent.stat().st_mode)
    assert directory_mode & 0o077 == 0


def test_symlink_token_path_is_refused(tmp_path):
    if os.name == "nt":
        pytest.skip("creating symlinks requires elevated privileges on Windows")
    target = tmp_path / "real_token"
    target.write_text("x" * 40, encoding="utf-8")
    link = tmp_path / "web_token"
    link.symlink_to(target)
    with pytest.raises(TokenStoreError):
        load_or_create_token(link)


def test_a_directory_in_place_of_the_token_file_is_refused(tmp_path):
    path = tmp_path / "web_token"
    path.mkdir()
    with pytest.raises(TokenStoreError):
        load_or_create_token(path)


def test_default_token_path_is_inside_the_data_directory():
    assert default_token_path("data") == __import__("pathlib").Path("data") / "web_token"
