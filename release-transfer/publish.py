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
EXPECTED = {'product-cockpit/1.3.0.bundle.txt': (375429, '71bb94d85eff54f2f151d6565066e5ca1938eeb0037662467e400180f54f8d12'), 'product-cockpit/latest.json': (818, '9f2536e43d47c4f7ed8beb5fe0324a822b90689fcb396af2eb7e240369722660'), 'workspace/0.2.72.bundle.gz': (3713402, 'b539b500b1631f157bb6ca5403476c763e4fcd9911594f333a7c41e3794fb79b'), 'workspace/latest.json': (741, 'aa575ac7234e4b69f93c36f8ad3760163967c3ac12f2274505dde1fda4e50053')}

def git(*args, data=None, env=None):
    result = subprocess.run(["git", *args], input=data, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, env=env, timeout=120, check=False)
    if result.returncode:
        raise RuntimeError("git " + args[0] + " failed: " + result.stderr.decode(errors="replace")[-2000:])
    return result.stdout.decode().strip()


def payloads(folder):
    def assemble(prefix):
        parts = sorted(folder.glob(prefix + "-*.b64"))
        if not 1 <= len(parts) <= 128:
            raise ValueError("Missing transfer pieces")
        blocks = []
        for index, file in enumerate(parts):
            if file.name != f"{prefix}-{index:03d}.b64":
                raise ValueError("Missing or unexpected transfer piece")
            raw = file.read_bytes().strip()
            if not raw or len(raw) > 256 * 1024:
                raise ValueError("Invalid transfer piece size")
            blocks.append(base64.b64decode(raw, validate=True))
        return b"".join(blocks)
    files = {
        "product-cockpit/1.3.0.bundle.txt": assemble("cockpit-part"),
        "product-cockpit/latest.json": (folder / "cockpit.latest.json").read_bytes(),
        "workspace/0.2.72.bundle.gz": assemble("workspace-part"),
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
            predecessors = {"product-cockpit/latest.json": "9afecb5f054c63d4755bbad6557f62fee7c2c3cf", "workspace/latest.json": "51d66e87ef624ff82f8609faa62ac71eee42a7df"}
            for name, previous in predecessors.items():
                current = git("rev-parse", parent + ":" + name)
                if current not in {previous, blobs[name]}:
                    raise RuntimeError("Another release changed the update channel; refusing to overwrite " + name)
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
                         "-m", "Publish Product Cockpit 1.3.0 and Workspace 0.2.72", env=env)
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
