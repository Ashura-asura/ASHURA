"""Persistent launch token for the local web interface.

The token authenticates the single operator. Persisting it lets a browser stay signed in
across server restarts without turning authentication off: the cookie is still HttpOnly,
SameSite=Strict, and every API request is still checked against the stored token.

Threat model: this protects against other web origins and casual local users, not against a
process running as the same OS user. On POSIX the file is created 0600 inside a 0700 directory.
On Windows ``os.chmod`` does not implement POSIX ACLs, so the file inherits the directory ACL;
the calling operator is responsible for the profile's filesystem permissions. The file is never
served by the HTTP handler and is excluded from version control.
"""
from __future__ import annotations

import os
import secrets
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path

TOKEN_MIN_LENGTH = 24
TOKEN_MAX_LENGTH = 512


class TokenStoreError(RuntimeError):
    pass


@dataclass(frozen=True)
class StoredToken:
    token: str
    path: Path
    created: bool
    permissions_note: str

    @property
    def status(self) -> str:
        return "created" if self.created else "loaded"


def _validate(token: str) -> bool:
    return (TOKEN_MIN_LENGTH <= len(token) <= TOKEN_MAX_LENGTH
            and not any(ch.isspace() for ch in token))


def _ensure_directory(path: Path) -> str:
    path.mkdir(parents=True, exist_ok=True)
    note = "directory permissions not restricted on this platform"
    if os.name == "posix":
        try:
            path.chmod(0o700)
            mode = stat.S_IMODE(path.stat().st_mode)
            note = f"directory mode {mode:04o}"
        except OSError as error:
            note = f"directory permissions could not be restricted: {error}"
    return note


def _atomic_write(path: Path, token: str) -> None:
    """Write the token without a window where a partial value is readable."""
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        if os.name == "posix":
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(token + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
        if os.name == "posix":
            path.chmod(0o600)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def load_or_create_token(path: str | os.PathLike) -> StoredToken:
    """Load the token file, or create it with a fresh 256-bit token.

    A malformed, empty, or unreadable file is treated as absent rather than trusted. The caller
    should treat a changed token as a deliberate rotation: existing cookies stop working.
    """
    target = Path(path).expanduser()
    if target.is_symlink():
        raise TokenStoreError(f"refusing to use a symlink as the token file: {target}")
    note = _ensure_directory(target.parent)
    if not target.exists():
        token = secrets.token_urlsafe(32)
        try:
            _atomic_write(target, token)
        except OSError as error:
            raise TokenStoreError(f"could not write the token file: {error}") from error
        return StoredToken(token, target, True, note)
    if not target.is_file():
        raise TokenStoreError(f"token path is not a regular file: {target}")
    try:
        token = target.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as error:
        raise TokenStoreError(f"could not read the token file: {error}") from error
    if not _validate(token):
        token = secrets.token_urlsafe(32)
        try:
            _atomic_write(target, token)
        except OSError as error:
            raise TokenStoreError(f"could not replace an invalid token file: {error}") from error
        return StoredToken(token, target, True, note)
    if os.name == "posix":
        try:
            mode = stat.S_IMODE(target.stat().st_mode)
            if mode & 0o077:
                note = f"warning: token file mode {mode:04o} is readable by other users"
            else:
                note = f"token file mode {mode:04o}"
        except OSError as error:
            note = f"could not inspect token file permissions: {error}"
    return StoredToken(token, target, False, note)


def default_token_path(data_directory: str | os.PathLike) -> Path:
    return Path(data_directory) / "web_token"
