#!/usr/bin/env python3
"""Publish only the four reviewed encrypted updater artifacts. No signing secrets."""
import base64
import hashlib
import os
from pathlib import Path
import re
import subprocess
import tempfile

TARGET = "refs/heads/felix-desktop-updates"
EXPECTED = {
    "product-cockpit/1.1.0.bundle.txt": (140313, "8d3a1fbb05266e90bb79dfd712e1e09bc0b97008a57e34e6e62622eec4e87b32"),
    "product-cockpit/latest.json": (818, "8b67c9baf7ffdc76f19ee5feb4f3362dd89a5b832aacb54125df8ecafb710500"),
    "workspace/0.2.70.bundle.gz": (3649189, "6ed3c656f751c91fc1b1d2e66f2f47982a4b47e65722d9221e198beb4aea882d"),
    "workspace/latest.json": (741, "c8dd5f59a0fb3c26aa93f994ec116df875e4ee7a583afaaa0c5f12d8d448805e"),
}

def git(*args, data=None, env=None):
    result = subprocess.run(["git", *args], input=data, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, env=env, timeout=120, check=False)
    if result.returncode:
        raise RuntimeError("git " + args[0] + " failed: " + result.stderr.decode(errors="replace")[-2000:])
    return result.stdout.decode().strip()


def payloads(folder):
    parts = sorted(folder.glob("part-*.b64"))
    if not 1 <= len(parts) <= 128:
        raise ValueError("Missing transfer pieces")
    blocks = []
    for index, file in enumerate(parts):
        if file.name != f"part-{index:03d}.b64":
            raise ValueError("Missing or unexpected transfer piece")
        raw = file.read_bytes().strip()
        if not raw or len(raw) > 256 * 1024:
            raise ValueError("Invalid transfer piece size")
        blocks.append(base64.b64decode(raw, validate=True))
    files = {
        "product-cockpit/1.1.0.bundle.txt": (folder / "cockpit.bundle.txt").read_bytes(),
        "product-cockpit/latest.json": (folder / "cockpit.latest.json").read_bytes(),
        "workspace/0.2.70.bundle.gz": b"".join(blocks),
        "workspace/latest.json": (folder / "workspace.latest.json").read_bytes(),
    }
    for name, data in files.items():
        size, digest = EXPECTED[name]
        if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
            raise ValueError("Artifact verification failed: " + name)
    return files


def publish(folder):
    files = payloads(folder)
    print("Verified all four encrypted update artifacts.", flush=True)
    blobs = {name: git("hash-object", "-w", "--stdin", data=data) for name, data in files.items()}
    with tempfile.TemporaryDirectory(prefix="update-index-") as tmp:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(tmp) / "index"),
                   GIT_AUTHOR_NAME="Desktop Update Publisher", GIT_AUTHOR_EMAIL="desktop-updates@users.noreply.github.com",
                   GIT_COMMITTER_NAME="Desktop Update Publisher", GIT_COMMITTER_EMAIL="desktop-updates@users.noreply.github.com")
        for attempt in range(3):
            git("fetch", "--no-tags", "--depth=1", "origin", TARGET)
            parent = git("rev-parse", "FETCH_HEAD")
            git("read-tree", parent, env=env)
            for name, blob in blobs.items():
                git("update-index", "--add", "--cacheinfo", f"100644,{blob},{name}", env=env)
            tree = git("write-tree", env=env)
            changed = set(git("diff-tree", "--no-commit-id", "--name-only", "-r", parent, tree).splitlines())
            if not changed:
                print("All four updates are already published at " + parent, flush=True)
                return parent
            if not changed <= set(EXPECTED):
                raise RuntimeError("Unexpected path in publication")
            commit = git("commit-tree", tree, "-p", parent,
                         "-m", "Publish Product Cockpit 1.1.0 and Workspace 0.2.70", env=env)
            try:
                git("push", "origin", commit + ":" + TARGET)
            except RuntimeError:
                if attempt == 2:
                    raise
                print("Target changed or push failed; rebuilding against the current branch.", flush=True)
                continue
            print("Published four verified update artifacts at " + commit, flush=True)
            return commit
    raise RuntimeError("Publication failed")


if __name__ == "__main__":
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("Run only in the release transfer workflow")
    if os.environ.get("GITHUB_REPOSITORY") != "Felix1312-coder/amazon-buybox-checker-updates":
        raise SystemExit("Unexpected repository")
    if os.environ.get("GITHUB_REF") != "refs/heads/release-transfer-20261027":
        raise SystemExit("Unexpected release transfer branch")
    publish(Path(__file__).resolve().parent)
