"""Plain JSON and OpenSSL-compatible encrypted backup persistence."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any

from zpa_backup_restore.errors import CliError


DEFAULT_OPENSSL_BIN = "openssl"
DEFAULT_BACKUP_PASSPHRASE_ENV = "ZPA_BACKUP_PASSPHRASE"
OPENSSL_INTERNAL_PASSPHRASE_ENV = "ZPA_BACKUP_OPENSSL_PASSPHRASE"
OPENSSL_CIPHER = "aes-256-cbc"
OPENSSL_DIGEST = "sha256"
OPENSSL_PBKDF2_ITERATIONS = "200000"


def dump_json(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False)


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_json(payload) + "\n", encoding="utf-8")


def is_encrypted_path(path: Path) -> bool:
    return path.name.endswith(".enc")


def encrypted_path(path: Path) -> Path:
    return path if is_encrypted_path(path) else path.with_suffix(path.suffix + ".enc")


def openssl_binary(openssl_bin: str) -> str:
    resolved = shutil.which(openssl_bin)
    if not resolved:
        raise CliError(
            f"OpenSSL executable not found: {openssl_bin!r}. "
            "Install OpenSSL or pass --openssl-bin with the full path."
        )
    return resolved


def backup_passphrase(passphrase_env: str) -> str:
    value = os.environ.get(passphrase_env)
    if not value:
        raise CliError(
            f"Missing backup encryption passphrase. Set {passphrase_env} "
            "before reading or writing encrypted backups."
        )
    return value


def openssl_env(passphrase: str) -> dict[str, str]:
    run_env = {
        key: os.environ[key]
        for key in (
            "PATH",
            "HOME",
            "TMPDIR",
            "LANG",
            "LC_ALL",
            "OPENSSL_CONF",
            "OPENSSL_MODULES",
        )
        if key in os.environ
    }
    run_env[OPENSSL_INTERNAL_PASSPHRASE_ENV] = passphrase
    return run_env


def openssl_enc_command(openssl_bin: str, *, decrypt: bool = False) -> list[str]:
    command = [
        openssl_binary(openssl_bin),
        "enc",
        f"-{OPENSSL_CIPHER}",
        "-salt",
        "-pbkdf2",
        "-iter",
        OPENSSL_PBKDF2_ITERATIONS,
        "-md",
        OPENSSL_DIGEST,
        "-pass",
        f"env:{OPENSSL_INTERNAL_PASSPHRASE_ENV}",
    ]
    if decrypt:
        command.insert(2, "-d")
    return command


def openssl_decrypt_command(path: Path, passphrase_env: str = DEFAULT_BACKUP_PASSPHRASE_ENV) -> str:
    input_path = shlex.quote(str(path))
    output_path = shlex.quote(str(path.with_suffix("")))
    return (
        f"openssl enc -d -{OPENSSL_CIPHER} "
        f"-pbkdf2 -iter {OPENSSL_PBKDF2_ITERATIONS} -md {OPENSSL_DIGEST} "
        f"-in {input_path} -out {output_path} -pass env:{passphrase_env}"
    )


def save_encrypted_json(
    path: Path,
    payload: Any,
    *,
    passphrase_env: str = DEFAULT_BACKUP_PASSPHRASE_ENV,
    openssl_bin: str = DEFAULT_OPENSSL_BIN,
) -> None:
    passphrase = backup_passphrase(passphrase_env)
    path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [*openssl_enc_command(openssl_bin), "-out", str(path)],
        input=(dump_json(payload) + "\n").encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=openssl_env(passphrase),
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", "replace").strip()
        raise CliError(f"OpenSSL backup encryption failed for {path}: {stderr}")


def decrypt_json_text(
    path: Path,
    *,
    passphrase_env: str = DEFAULT_BACKUP_PASSPHRASE_ENV,
    openssl_bin: str = DEFAULT_OPENSSL_BIN,
) -> str:
    passphrase = backup_passphrase(passphrase_env)
    result = subprocess.run(
        [*openssl_enc_command(openssl_bin, decrypt=True), "-in", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=openssl_env(passphrase),
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", "replace").strip()
        raise CliError(f"OpenSSL backup decryption failed for {path}: {stderr}")
    return result.stdout.decode("utf-8")


def save_backup_json(
    path: Path,
    payload: Any,
    *,
    encrypted: bool = False,
    passphrase_env: str = DEFAULT_BACKUP_PASSPHRASE_ENV,
    openssl_bin: str = DEFAULT_OPENSSL_BIN,
) -> None:
    if encrypted:
        save_encrypted_json(path, payload, passphrase_env=passphrase_env, openssl_bin=openssl_bin)
    else:
        save_json(path, payload)


def load_json_file(
    path: Path,
    *,
    passphrase_env: str = DEFAULT_BACKUP_PASSPHRASE_ENV,
    openssl_bin: str = DEFAULT_OPENSSL_BIN,
) -> Any:
    try:
        text = (
            decrypt_json_text(path, passphrase_env=passphrase_env, openssl_bin=openssl_bin)
            if is_encrypted_path(path)
            else path.read_text(encoding="utf-8")
        )
        return json.loads(text)
    except FileNotFoundError as error:
        raise CliError(f"File not found: {path}") from error
    except json.JSONDecodeError as error:
        raise CliError(f"Invalid JSON in {path}: {error}") from error


__all__ = [
    "DEFAULT_BACKUP_PASSPHRASE_ENV",
    "DEFAULT_OPENSSL_BIN",
    "OPENSSL_CIPHER",
    "OPENSSL_DIGEST",
    "OPENSSL_INTERNAL_PASSPHRASE_ENV",
    "OPENSSL_PBKDF2_ITERATIONS",
    "backup_passphrase",
    "decrypt_json_text",
    "dump_json",
    "encrypted_path",
    "is_encrypted_path",
    "load_json_file",
    "openssl_binary",
    "openssl_decrypt_command",
    "openssl_enc_command",
    "openssl_env",
    "save_backup_json",
    "save_encrypted_json",
    "save_json",
]
