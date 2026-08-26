"""Fail a worker image build if its pinned scientific packages drift."""

import argparse
import glob
import hashlib
import json
import os
import subprocess
import sys


def file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_package(prefix: str, expected: dict) -> dict:
    pattern = os.path.join(
        prefix,
        "conda-meta",
        f"{expected['name']}-{expected['version']}-{expected['build']}.json",
    )
    matches = glob.glob(pattern)
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one package record matching {pattern}; found {len(matches)}")
    with open(matches[0], "r", encoding="utf-8") as handle:
        actual = json.load(handle)
    for field in ("name", "version", "build", "url", "sha256"):
        if actual.get(field) != expected.get(field):
            raise RuntimeError(
                f"Package {expected['name']} {field} mismatch: expected {expected.get(field)!r}, "
                f"found {actual.get(field)!r}"
            )
    return {field: actual.get(field) for field in ("name", "version", "build", "url", "sha256")}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata", required=True)
    parser.add_argument("--prefix", required=True)
    args = parser.parse_args()

    with open(args.metadata, "r", encoding="utf-8") as handle:
        metadata = json.load(handle)

    vina = metadata["vina"]
    actual_path = os.path.realpath(vina["expected_path"])
    expected_path = os.path.realpath(vina["expected_path"])
    if actual_path != expected_path or not os.path.isfile(actual_path):
        raise RuntimeError(f"Trusted Vina executable is absent at {expected_path}")
    actual_digest = file_sha256(actual_path)
    if actual_digest != vina["expected_binary_sha256"]:
        raise RuntimeError(
            f"Vina executable digest mismatch: expected {vina['expected_binary_sha256']}, found {actual_digest}"
        )
    version_probe = subprocess.run(
        [actual_path, "--version"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    version_output = "\n".join(
        part for part in (version_probe.stdout, version_probe.stderr) if part
    ).strip()
    if version_probe.returncode != 0 or vina["expected_version"] not in version_output.splitlines():
        raise RuntimeError(
            f"Trusted Vina version probe mismatch: expected {vina['expected_version']!r}, "
            f"exit={version_probe.returncode}, output={version_output!r}"
        )

    evidence = {
        "release_id": metadata["release_id"],
        "vina_path": actual_path,
        "vina_binary_sha256": actual_digest,
        "vina_version": vina["expected_version"],
        "vina_package": verify_package(args.prefix, vina["package"]),
        "rdkit_package": verify_package(args.prefix, metadata["rdkit"]["package"]),
    }
    print(json.dumps(evidence, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
