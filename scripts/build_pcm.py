#!/usr/bin/env python3
"""Validate the KiCad library and build a static KiCad PCM repository.

The generated ``dist`` directory is suitable for GitHub Pages. The package
metadata uses KiCad's PCM v2 schema because the retained Nordic license is
represented by an SPDX-style LicenseRef rather than a v1 license enum.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import os
import re
import shutil
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SYMBOL = ROOT / "PCA10059_nRF52840_Dongle.kicad_sym"
FOOTPRINT_DIR = ROOT / "PCA10059_nRF52840_Dongle.pretty"
FOOTPRINT = FOOTPRINT_DIR / "PCA10059_nRF52840_Dongle.kicad_mod"
PINOUT = ROOT / "pinout.csv"
VERSION_FILE = ROOT / "VERSION"

PACKAGE_NAME = "PCA10059 nRF52840 USB Dongle Library"
PACKAGE_SLUG = "pca10059-nrf52840-dongle"
DESCRIPTION = "KiCad symbol and carrier footprint for the Nordic PCA10059 nRF52840 USB Dongle."
DESCRIPTION_FULL = (
    "A simplified 22-pin KiCad symbol and host-board footprint for mounting "
    "the Nordic Semiconductor PCA10059 nRF52840 USB Dongle as a castellated "
    "module. Includes the exact module outline, USB envelope, antenna keepout, "
    "pin numbering, and SWD contacts. It does not reproduce the dongle's "
    "internal circuitry."
)
SCHEMA_URL = "https://go.kicad.org/pcm/schemas/v2"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--github-repository",
        default=os.environ.get(
            "GITHUB_REPOSITORY", "binloan/nrf52840-dongle-kicad"
        ),
        help="GitHub owner/repository slug (default: GITHUB_REPOSITORY)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "dist",
        help="output directory (default: repository dist/)",
    )
    parser.add_argument(
        "--version",
        help="package version; defaults to the contents of VERSION",
    )
    return parser.parse_args()


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize_identifier_part(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")
    if not normalized:
        raise ValueError(f"Cannot form a package identifier from {value!r}")
    return normalized


def split_repository(value: str) -> tuple[str, str]:
    parts = value.strip().strip("/").split("/")
    if len(parts) != 2 or not all(parts):
        raise ValueError("--github-repository must have the form OWNER/REPOSITORY")
    return parts[0], parts[1]


def blocks(text: str, token: str) -> list[str]:
    """Return balanced S-expression blocks beginning with ``(token``."""
    result: list[str] = []
    cursor = 0
    needle = f"({token}"
    while True:
        start = text.find(needle, cursor)
        if start < 0:
            return result
        depth = 0
        quoted = False
        escaped = False
        for index in range(start, len(text)):
            character = text[index]
            if quoted:
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == '"':
                    quoted = False
            elif character == '"':
                quoted = True
            elif character == "(":
                depth += 1
            elif character == ")":
                depth -= 1
                if depth == 0:
                    result.append(text[start : index + 1])
                    cursor = index + 1
                    break
        else:
            raise ValueError(f"Unclosed {token} block")


def validate_library() -> None:
    missing = [path for path in (SYMBOL, FOOTPRINT, PINOUT, VERSION_FILE) if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing required files: " + ", ".join(map(str, missing)))

    with PINOUT.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 22:
        raise ValueError(f"pinout.csv must contain 22 pins; found {len(rows)}")
    pinout = {int(row["Pin"]): row["Signal"] for row in rows}
    expected_numbers = set(range(1, 23))
    if set(pinout) != expected_numbers:
        raise ValueError("pinout.csv pin numbers must be exactly 1 through 22")

    footprint_text = FOOTPRINT.read_text(encoding="utf-8")
    pad_numbers = {
        int(match.group(1))
        for block in blocks(footprint_text, "pad")
        if (match := re.match(r'^\(pad\s+"(\d+)"\s+smd\s+', block))
    }
    if pad_numbers != expected_numbers:
        raise ValueError(f"Footprint pad numbers differ from 1..22: {sorted(pad_numbers)}")

    symbol_text = SYMBOL.read_text(encoding="utf-8")
    symbol_pins: dict[int, str] = {}
    for block in blocks(symbol_text, "pin"):
        name = re.search(r'\(name\s+"([^"]*)"', block)
        number = re.search(r'\(number\s+"(\d+)"', block)
        if name and number:
            symbol_pins[int(number.group(1))] = name.group(1)
    if set(symbol_pins) != expected_numbers:
        raise ValueError(f"Symbol pin numbers differ from 1..22: {sorted(symbol_pins)}")

    mismatches = {
        number: (pinout[number], symbol_pins[number])
        for number in expected_numbers
        if pinout[number] != symbol_pins[number]
    }
    if mismatches:
        raise ValueError(f"Symbol/pinout signal mismatches: {mismatches}")

    expected_footprint = (
        '"PCA10059_nRF52840_Dongle:PCA10059_nRF52840_Dongle"'
    )
    if expected_footprint not in symbol_text:
        raise ValueError("Symbol does not reference the packaged footprint nickname")


def add_zip_member(archive: zipfile.ZipFile, name: str, data: bytes) -> None:
    info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    archive.writestr(info, data)


def build_package_archive(path: Path, metadata: dict[str, object]) -> int:
    source_symbol = SYMBOL.read_text(encoding="utf-8")
    source_nickname = "PCA10059_nRF52840_Dongle:PCA10059_nRF52840_Dongle"
    pcm_nickname = "PCM_PCA10059_nRF52840_Dongle:PCA10059_nRF52840_Dongle"
    if source_nickname not in source_symbol:
        raise ValueError("Cannot rewrite the source footprint nickname for PCM")
    pcm_symbol = source_symbol.replace(source_nickname, pcm_nickname, 1).encode("utf-8")
    members = {
        "metadata.json": json_bytes(metadata),
        f"symbols/{SYMBOL.name}": pcm_symbol,
        f"footprints/{FOOTPRINT_DIR.name}/{FOOTPRINT.name}": FOOTPRINT.read_bytes(),
    }
    with zipfile.ZipFile(path, "w") as archive:
        for name in sorted(members):
            add_zip_member(archive, name, members[name])
    return sum(len(data) for data in members.values())


def main() -> None:
    args = parse_args()
    validate_library()

    owner, repository = split_repository(args.github_repository)
    version = (args.version or VERSION_FILE.read_text(encoding="utf-8")).strip()
    if not re.fullmatch(r"\d{1,4}(?:\.\d{1,4}(?:\.\d{1,6})?)?", version):
        raise ValueError(f"VERSION must be numeric major[.minor[.patch]]; got {version!r}")

    owner_id = normalize_identifier_part(owner)
    repository_id = normalize_identifier_part(repository)
    identifier = f"com.github.{owner_id}.{repository_id}"
    if len(identifier) > 50:
        raise ValueError(f"Generated package identifier exceeds 50 characters: {identifier}")

    github_url = f"https://github.com/{owner}/{repository}"
    if repository.lower() == f"{owner.lower()}.github.io":
        pages_url = f"https://{owner.lower()}.github.io"
    else:
        pages_url = f"https://{owner.lower()}.github.io/{repository}"

    contact = {"name": owner, "contact": {"web": github_url}}
    package_metadata: dict[str, object] = {
        "$schema": SCHEMA_URL,
        "name": PACKAGE_NAME,
        "description": DESCRIPTION,
        "description_full": DESCRIPTION_FULL,
        "identifier": identifier,
        "type": "library",
        "author": contact,
        "maintainer": contact,
        "license": "LicenseRef-Nordic-5-Clause",
        "resources": {
            "homepage": github_url,
            "documentation": f"{github_url}#readme",
        },
        "tags": ["nrf52840", "pca10059", "module", "footprint", "symbol"],
        "versions": [
            {
                "version": version,
                "status": "stable",
                "kicad_version": "10.0",
            }
        ],
    }

    output = args.output.resolve()
    if output.exists():
        shutil.rmtree(output)
    packages_dir = output / "packages"
    packages_dir.mkdir(parents=True)

    archive_name = f"{PACKAGE_SLUG}-{version}.zip"
    archive_path = packages_dir / archive_name
    install_size = build_package_archive(archive_path, package_metadata)
    archive_data = archive_path.read_bytes()

    listing_metadata = json.loads(json.dumps(package_metadata))
    listing_version = listing_metadata["versions"][0]
    listing_version.update(
        {
            "download_url": f"{pages_url}/packages/{archive_name}",
            "download_sha256": sha256(archive_data),
            "download_size": len(archive_data),
            "install_size": install_size,
        }
    )
    packages_data = json_bytes({"packages": [listing_metadata]})
    (output / "packages.json").write_bytes(packages_data)

    timestamp = int(os.environ.get("SOURCE_DATE_EPOCH", str(int(time.time()))))
    update_time = datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    repository_metadata = {
        "$schema": SCHEMA_URL,
        "schema_version": 2,
        "name": PACKAGE_NAME,
        "maintainer": contact,
        "packages": {
            "url": f"{pages_url}/packages.json",
            "sha256": sha256(packages_data),
            "update_timestamp": timestamp,
            "update_time_utc": update_time,
        },
    }
    (output / "repository.json").write_bytes(json_bytes(repository_metadata))
    (output / ".nojekyll").write_text("", encoding="utf-8")

    repository_url = f"{pages_url}/repository.json"
    index = f"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(PACKAGE_NAME)}</title>
<style>
body{{font:16px/1.55 system-ui,sans-serif;max-width:760px;margin:4rem auto;padding:0 1.25rem;color:#172033}}
code{{background:#eef2f7;padding:.15rem .35rem;border-radius:.25rem;word-break:break-all}}
a{{color:#145ea8}} img{{max-width:100%}}
</style>
<h1>{html.escape(PACKAGE_NAME)}</h1>
<p>KiCad Plugin and Content Manager repository for the PCA10059 module library.</p>
<p>Add this URL in KiCad's <strong>Plugin and Content Manager → Manage Repositories</strong>:</p>
<p><code>{html.escape(repository_url)}</code></p>
<p><a href="repository.json">repository.json</a> · <a href="packages.json">packages.json</a> · <a href="packages/{html.escape(archive_name)}">package {html.escape(version)}</a> · <a href="{html.escape(github_url)}">source</a></p>
"""
    (output / "index.html").write_text(index, encoding="utf-8")

    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
    required = {
        "metadata.json",
        f"symbols/{SYMBOL.name}",
        f"footprints/{FOOTPRINT_DIR.name}/{FOOTPRINT.name}",
    }
    if names != required:
        raise ValueError(f"Unexpected package contents: {sorted(names)}")

    print(f"Validated: 22 symbol pins, 22 footprint pads, and pinout parity")
    print(f"Package:   {archive_path} ({len(archive_data)} bytes)")
    print(f"SHA-256:   {sha256(archive_data)}")
    print(f"PCM URL:   {repository_url}")


if __name__ == "__main__":
    main()

