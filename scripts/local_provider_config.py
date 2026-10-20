#!/usr/bin/env python3
"""Private local provider configuration; Linux stdlib only, with no network access."""

from __future__ import annotations

import argparse
import errno
import getpass
import json
import os
from pathlib import Path
import secrets
import stat
import sys
import warnings


CONFIG_PATH = Path("/home/aegml/.config/aegml/provider.json")
EXPECTED_USER = "aegml"
OFFICIAL_BASE_URL = "https://changellenge.up.railway.app/v1"
EXPECTED_MODEL = "qwen/qwen3.8-27b"
FIELDS = ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL")
MAX_KEY_CHARS = 16_384
MAX_CONFIG_BYTES = 32_768


class ConfigError(Exception):
    """Only fixed, non-secret codes may cross the CLI boundary."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class SafeParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        # argparse's normal error includes argv values; never print them.
        raise ConfigError("INVALID_ARGUMENTS")


def _identity() -> int:
    if sys.platform != "linux" or not hasattr(os, "O_NOFOLLOW"):
        raise ConfigError("LINUX_REQUIRED")
    if os.getuid() != os.geteuid():
        raise ConfigError("USER_NOT_ALLOWED")
    import pwd

    uid = os.getuid()
    try:
        name = pwd.getpwuid(uid).pw_name
    except KeyError:
        raise ConfigError("USER_NOT_ALLOWED") from None
    if name != EXPECTED_USER:
        raise ConfigError("USER_NOT_ALLOWED")
    return uid


def _open_parent(uid: int, *, create: bool) -> int:
    """Resolve every component by directory FD, refusing symlinks."""
    path = CONFIG_PATH
    if not path.is_absolute() or path.name != "provider.json":
        raise ConfigError("INVALID_CONFIG_PATH")
    parts = path.parent.parts[1:]
    if not parts or any(part in (".", "..") for part in parts):
        raise ConfigError("INVALID_CONFIG_PATH")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = os.open("/", flags)
    try:
        for part in parts:
            created = False
            try:
                next_fd = os.open(part, flags, dir_fd=fd)
            except FileNotFoundError:
                if not create:
                    raise ConfigError("CONFIG_NOT_FOUND") from None
                try:
                    os.mkdir(part, mode=0o700, dir_fd=fd)
                    created = True
                except FileExistsError:
                    pass
                next_fd = os.open(part, flags, dir_fd=fd)
            try:
                if created:
                    os.fchmod(next_fd, 0o700)
                ancestor = os.fstat(next_fd)
                shared_sticky = ancestor.st_uid == 0 and bool(ancestor.st_mode & stat.S_ISVTX)
                if ancestor.st_uid not in (0, uid) or (
                    stat.S_IMODE(ancestor.st_mode) & 0o022 and not shared_sticky
                ):
                    raise ConfigError("UNSAFE_ANCESTOR")
            except BaseException:
                os.close(next_fd)
                raise
            os.close(fd)
            fd = next_fd
        info = os.fstat(fd)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != uid:
            raise ConfigError("UNSAFE_DIRECTORY_OWNER")
        if stat.S_IMODE(info.st_mode) != 0o700:
            raise ConfigError("UNSAFE_DIRECTORY_MODE")
        return fd
    except BaseException:
        os.close(fd)
        raise


def _assert_missing(parent_fd: int) -> None:
    try:
        info = os.stat(CONFIG_PATH.name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    if stat.S_ISLNK(info.st_mode):
        raise ConfigError("CONFIG_SYMLINK")
    raise ConfigError("CONFIG_EXISTS")


def _public_values(base_url: str, model: str) -> tuple[str, str]:
    # Only the published public values may appear in metadata. Reject accidental
    # credentials, query strings, alternate hosts and model strings.
    if base_url.rstrip("/") != OFFICIAL_BASE_URL:
        raise ConfigError("BASE_URL_NOT_ALLOWED")
    if model != EXPECTED_MODEL:
        raise ConfigError("MODEL_NOT_ALLOWED")
    return OFFICIAL_BASE_URL, EXPECTED_MODEL


def _valid_key(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > MAX_KEY_CHARS
        or any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in value)
    ):
        raise ConfigError("INVALID_KEY")
    return value


def _read_secret(from_stdin: bool) -> str:
    if from_stdin:
        line = sys.stdin.readline(MAX_KEY_CHARS + 2)
        return _valid_key(line.rstrip("\r\n"))
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            value = getpass.getpass("API key (hidden): ")
    except (getpass.GetPassWarning, EOFError):
        raise ConfigError("SECURE_INPUT_UNAVAILABLE") from None
    return _valid_key(value)


def _decode_config(raw: bytes) -> dict[str, str]:
    def unique_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
        value = {}
        for name, item in pairs:
            if name in value:
                raise ConfigError("INVALID_CONFIG_FIELDS")
            value[name] = item
        return value

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_fields)
    except (UnicodeError, ValueError, RecursionError):
        raise ConfigError("INVALID_CONFIG_JSON") from None
    if not isinstance(value, dict) or set(value) != set(FIELDS):
        raise ConfigError("INVALID_CONFIG_FIELDS")
    if any(not isinstance(value[field], str) or not value[field] for field in FIELDS):
        raise ConfigError("INVALID_CONFIG_FIELDS")
    _valid_key(value["OPENAI_API_KEY"])
    _public_values(value["OPENAI_BASE_URL"], value["OPENAI_MODEL"])
    return value


def _read_checked(parent_fd: int, uid: int) -> tuple[dict[str, str], os.stat_result]:
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
    try:
        fd = os.open(CONFIG_PATH.name, flags, dir_fd=parent_fd)
    except FileNotFoundError:
        raise ConfigError("CONFIG_NOT_FOUND") from None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ConfigError("CONFIG_NOT_REGULAR")
        if info.st_uid != uid:
            raise ConfigError("UNSAFE_FILE_OWNER")
        if stat.S_IMODE(info.st_mode) != 0o600:
            raise ConfigError("UNSAFE_FILE_MODE")
        if info.st_nlink != 1:
            raise ConfigError("UNSAFE_FILE_LINKS")
        if not 0 < info.st_size <= MAX_CONFIG_BYTES:
            raise ConfigError("INVALID_CONFIG_SIZE")
        chunks = bytearray()
        while len(chunks) <= MAX_CONFIG_BYTES:
            chunk = os.read(fd, min(8192, MAX_CONFIG_BYTES + 1 - len(chunks)))
            if not chunk:
                break
            chunks.extend(chunk)
        after = os.fstat(fd)
        if (
            len(chunks) > MAX_CONFIG_BYTES
            or len(chunks) != info.st_size
            or (info.st_size, info.st_mtime_ns, info.st_ctime_ns)
            != (after.st_size, after.st_mtime_ns, after.st_ctime_ns)
        ):
            raise ConfigError("CONFIG_CHANGED")
        return _decode_config(bytes(chunks)), after
    finally:
        os.close(fd)


def _metadata(
    parent_fd: int, uid: int, value: dict[str, str], info: os.stat_result
) -> dict[str, object]:
    return {
        "status": "CONFIGURED_UNVERIFIED",
        "path": str(CONFIG_PATH),
        "uid": uid,
        "modes": {
            "parent": format(stat.S_IMODE(os.fstat(parent_fd).st_mode), "04o"),
            "file": format(stat.S_IMODE(info.st_mode), "04o"),
        },
        "fields_present": list(FIELDS),
        "base_url": value["OPENAI_BASE_URL"],
        "model": value["OPENAI_MODEL"],
        "real_api_requests": 0,
    }


def configure(
    *, from_stdin: bool, base_url: str, model: str
) -> dict[str, object]:
    uid = _identity()
    base_url, model = _public_values(base_url, model)
    parent_fd = _open_parent(uid, create=True)
    temporary = None
    try:
        # Refuse an existing target before reading any secret.
        _assert_missing(parent_fd)
        key = _read_secret(from_stdin)
        payload = json.dumps(
            {
                "OPENAI_API_KEY": key,
                "OPENAI_BASE_URL": base_url,
                "OPENAI_MODEL": model,
            },
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("utf-8") + b"\n"
        if len(payload) > MAX_CONFIG_BYTES:
            raise ConfigError("INVALID_CONFIG_SIZE")
        temporary_name = ".provider-" + secrets.token_hex(16) + ".tmp"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
        fd = os.open(temporary_name, flags, 0o600, dir_fd=parent_fd)
        temporary = temporary_name
        try:
            os.fchmod(fd, 0o600)
            position = 0
            while position < len(payload):
                written = os.write(fd, payload[position:])
                if written <= 0:
                    raise ConfigError("CONFIG_WRITE_FAILED")
                position += written
            os.fsync(fd)
        finally:
            os.close(fd)
        # link() publishes complete bytes atomically and never replaces a
        # concurrent target. Source/target stay in the already-open directory.
        try:
            os.link(
                temporary,
                CONFIG_PATH.name,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
                follow_symlinks=False,
            )
        except FileExistsError:
            raise ConfigError("CONFIG_EXISTS") from None
        os.unlink(temporary, dir_fd=parent_fd)
        temporary = None
        os.fsync(parent_fd)
        value, info = _read_checked(parent_fd, uid)
        return _metadata(parent_fd, uid, value, info)
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
        os.close(parent_fd)


def check() -> dict[str, object]:
    uid = _identity()
    parent_fd = _open_parent(uid, create=False)
    try:
        value, info = _read_checked(parent_fd, uid)
        return _metadata(parent_fd, uid, value, info)
    finally:
        os.close(parent_fd)


def _parse(argv: list[str]) -> argparse.Namespace:
    parser = SafeParser(add_help=False)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("configure", add_help=False)
    create.add_argument("--stdin", action="store_true", dest="from_stdin")
    create.add_argument("--base-url", default=OFFICIAL_BASE_URL)
    create.add_argument("--model", default=EXPECTED_MODEL)
    commands.add_parser("check", add_help=False)
    return parser.parse_args(argv)


def _emit(value: dict[str, object]) -> None:
    sys.stdout.write(json.dumps(value, ensure_ascii=True, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parse(sys.argv[1:] if argv is None else argv)
        if args.command == "configure":
            result = configure(
                from_stdin=args.from_stdin, base_url=args.base_url, model=args.model
            )
        else:
            result = check()
        _emit(result)
        return 0
    except ConfigError as exc:
        result = {"status": "ERROR", "error_code": exc.code, "real_api_requests": 0}
    except KeyboardInterrupt:
        result = {"status": "ERROR", "error_code": "CANCELLED", "real_api_requests": 0}
    except OSError as exc:
        code = "SYMLINK_OR_PATH_REJECTED" if exc.errno in (errno.ELOOP, errno.ENOTDIR) else "FILESYSTEM_ERROR"
        result = {"status": "ERROR", "error_code": code, "real_api_requests": 0}
    except Exception:
        result = {"status": "ERROR", "error_code": "INTERNAL_ERROR", "real_api_requests": 0}
    try:
        _emit(result)
    except OSError:
        pass
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

