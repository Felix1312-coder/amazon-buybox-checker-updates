#!/usr/bin/env python3
"""Publish only the two reviewed Cockpit updater artifacts. No signing secrets."""
import base64
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile

TARGET = "refs/heads/felix-desktop-updates"
EXPECTED = {'product-cockpit/1.3.1.bundle.txt': (504153, 'dd9c6b189232569b0e09cb9f94bf9870fbf1b817c5c28063caee1044e207b1c6'), 'product-cockpit/latest.json': (818, '58ca17a07c7aa08291d24edc39a0617ad12d7fd3055d02c7c5d809cd143e97df')}
PART_COUNT = 6
PREFIX = "cockpit-1.3.1-part"
PREVIOUS_MANIFEST = "36536a6859bb31fe2460bd948593483804f39e2d"


def git(*args, data=None, env=None):
    result = subprocess.run(["git", *args], input=data, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, env=env, timeout=120, check=False)
    if result.returncode:
        raise RuntimeError("git " + args[0] + " failed: " + result.stderr.decode(errors="replace")[-2000:])
    return result.stdout.decode().strip()


def payloads(folder):
    parts = sorted(folder.glob(PREFIX + "-*.b64"))
    if len(parts) != PART_COUNT or not 1 <= PART_COUNT <= 128:
        raise ValueError("Missing or unexpected transfer pieces")
    blocks = []
    for index, file in enumerate(parts):
        if file.name != f"{PREFIX}-{index:03d}.b64":
            raise ValueError("Missing or unexpected transfer piece")
        raw = file.read_bytes().strip()
        if not raw or len(raw) > 128 * 1024:
            raise ValueError("Invalid transfer piece size")
        block = base64.b64decode(raw, validate=True)
        if len(block) > 98304 or (index < PART_COUNT - 1 and len(block) != 98304):
            raise ValueError("Invalid decoded transfer piece size")
        blocks.append(block)
    files = {
        "product-cockpit/1.3.1.bundle.txt": b"".join(blocks),
        "product-cockpit/latest.json": (folder / "cockpit-1.3.1.latest.json").read_bytes(),
    }
    if set(EXPECTED) != set(files):
        raise ValueError("Unexpected approved publication path")
    for name, data in files.items():
        size, digest = EXPECTED[name]
        if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
            raise ValueError("Artifact verification failed: " + name)
    return files


def publish(folder):
    files = payloads(folder)
    print("Verified both encrypted Cockpit update artifacts.", flush=True)
    blobs = {name: git("hash-object", "-w", "--stdin", data=data) for name, data in files.items()}
    with tempfile.TemporaryDirectory(prefix="update-index-") as tmp:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(tmp) / "index"),
                   GIT_AUTHOR_NAME="Desktop Update Publisher", GIT_AUTHOR_EMAIL="desktop-updates@users.noreply.github.com",
                   GIT_COMMITTER_NAME="Desktop Update Publisher", GIT_COMMITTER_EMAIL="desktop-updates@users.noreply.github.com")
        for attempt in range(3):
            git("fetch", "--no-tags", "--depth=1", "origin", TARGET)
            parent = git("rev-parse", "FETCH_HEAD")
            current = git("rev-parse", parent + ":product-cockpit/latest.json")
            if current not in {PREVIOUS_MANIFEST, blobs["product-cockpit/latest.json"]}:
                raise RuntimeError("Another release changed the Cockpit update channel; refusing to overwrite")
            git("read-tree", parent, env=env)
            for name, blob in blobs.items():
                git("update-index", "--add", "--cacheinfo", f"100644,{blob},{name}", env=env)
            tree = git("write-tree", env=env)
            changed = set(git("diff-tree", "--no-commit-id", "--name-only", "-r", parent, tree).splitlines())
            if not changed:
                print("Both Cockpit artifacts are already published at " + parent, flush=True)
                return parent
            if not changed <= set(EXPECTED):
                raise RuntimeError("Unexpected path in publication")
            # An unrelated Workspace release is preserved from the fresh parent.
            if git("rev-parse", parent + ":workspace") != git("rev-parse", tree + ":workspace"):
                raise RuntimeError("Workspace tree unexpectedly changed")
            commit = git("commit-tree", tree, "-p", parent,
                         "-m", "Fix Product Cockpit 1.3.1 embedded EWS product links", env=env)
            try:
                git("push", "origin", commit + ":" + TARGET)
            except RuntimeError:
                if attempt == 2:
                    raise
                print("Target changed or push failed; rebuilding against the current branch.", flush=True)
                continue
            print("Published two verified Cockpit update artifacts at " + commit, flush=True)
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
