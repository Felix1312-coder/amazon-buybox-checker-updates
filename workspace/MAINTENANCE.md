# Workspace update maintenance

Existing channel: branch `felix-desktop-updates`, directory `workspace/`.

The installed desktop bootstrap reads `workspace/latest.json`. Routine application updates use the existing signed, encrypted version bundle; they do not require a new installer. Preserve the configured application ID, verification key, transport format and feed URL.

## Continuing maintenance in another session

1. Use the authorized GitHub connector to inspect this repository and branch. Direct shell network availability is separate from connector availability. A closed conversation does not close this repository.
2. Read the current remote manifest and verify its signature with the existing updater before choosing a strictly newer version. Never assume a local prepared release is current.
3. Recover the private application source and existing signing configuration from their authorized private project backup. Never publish plaintext application source, signing keys or transport keys to this public repository. If the private backup is unavailable, restore it before packaging; do not replace keys or weaken verification.
4. Implement and test the requested changes. Build a signed encrypted bundle with the existing packager and validate it with the installed updater implementation, including version selection. Preserve unrelated application files.
5. Publish only `workspace/<version>.bundle.gz` and `workspace/latest.json` together in one commit. The GitHub connector provides create_blob (base64 for binary), create_tree, create_commit and update_ref. Read the current branch head immediately before preparing the commit; use it as parent, preserve its base tree, and update the ref without force. If the branch moves, re-evaluate the current release before retrying.
6. Read the committed files back, verify their hashes and signatures, and test the updater against those bytes. Report remote-byte verification separately from an actual Windows restart test. Do not claim the user's installation has updated without confirmation.

Scope: maintain the Workspace channel only. Preserve other directories, team channels and existing user data. This document does not modify the active release or install an unattended publication service. Normal access controls and approvals still apply.
