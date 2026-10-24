---
name: arc-to-zen
description: Migrate Arc Browser to Zen on macOS, including Spaces, profile/container mapping, Favorites, pinned and open tabs, bookmarks, extension data, shortcuts, appearance, and an optional Little Arc style external-link preview. Use for an Arc-to-Zen migration, migration audit, or completing a partial migration.
license: MIT
metadata:
  author: AntonyLL
  version: "1.0.0"
  requirements: "macOS; Python 3.9+; Arc and Zen; filesystem and browser UI access. Optional preview: macOS 13+ and Xcode Command Line Tools."
---

# Arc → Zen

Carry the user's browser workflow into Zen and verify it after restart. Use the user's actual Arc preferences and current Zen state. Reply in the user's language. Treat a migration as a one-time transfer; ongoing sync is a separate task.

## Start with discovery

Resolve this skill's directory as `SKILL_ROOT`; run its scripts using absolute paths. Run:

```sh
python3 "$SKILL_ROOT/scripts/migrate.py" discover
python3 "$SKILL_ROOT/scripts/migrate.py" inspect --arc "$ARC_DATA"
```

On macOS, Arc data is usually `~/Library/Application Support/Arc`. Discover Zen profiles through `profiles.ini` and identify the active one through `about:support` → Profile Folder. If multiple plausible targets remain, ask the user to choose. Record installed browser versions. The native session adapter was derived from Arc 1.169.0 / Zen 1.23.4b; inspect schemas on other versions.

For a complete migration, follow [migration-workflow.md](references/migration-workflow.md). Produce a private work directory outside both browser profiles and outside any source repository. Do not publish generated inventories, bookmarks, URL maps, backups, or browser state.

## Prepare and migrate

1. Inventory Spaces, Arc profiles, Favorites, pins, ordinary tabs, bookmarks across profiles, extensions and saved extension content. Preserve source ordering and duplicate URLs. Arc's sidebar is separate from its Chromium Bookmarks files.
2. Close Arc before taking the final source snapshot. Before the first Zen shutdown, inspect its cookie/site-data deletion-on-exit settings: a restart can erase existing logins. Change those settings only if consistent with the user's requested login persistence; otherwise explain the effect. Close Zen before native staging or writing.
3. Generate local exports. Add `--zen-profile` to stage native files for a flat Arc sidebar:

```sh
python3 "$SKILL_ROOT/scripts/migrate.py" prepare \
  --arc "$ARC_DATA" --out "$WORK" --zen-profile "$ZEN_PROFILE"
```

`prepare` never writes browser profiles. It exports `bookmarks.html`, an inventory, selected source snapshots, and, when supported, a native plan. The adapter adds Spaces and tabs to the existing single-window session. It assigns a **new container per Arc profile**; Spaces sharing a profile share that container. Existing Zen Spaces and browser data remain in the prepared session.

Native folder/split conversion is deliberately unsupported in v1. For these inputs, the HTML export retains sidebar folders and the inventory records unsupported items. Complete the structure through Zen's UI using the source snapshot; never silently flatten it. See [native-format.md](references/native-format.md). Non-web URLs need review. For installed extensions, derive their current `moz-extension://` URL from the target profile and provide a local `--url-map` JSON object, then prepare into a fresh work directory.

4. Review the manifest, intended target, skipped records and preference changes. The user's migration request authorizes routine work within that scope; do not repeatedly ask for permission. Resolve actual choices such as replacing bookmarks, changing the system browser, or adding a substitute extension. The default native helper adds data and refuses duplicates and stale plans.
5. Apply the prepared plan when its scope is settled:

```sh
python3 "$SKILL_ROOT/scripts/migrate.py" apply --work "$WORK"
```

The helper requires Zen to be closed, verifies source/staged hashes, makes a full profile backup, writes four files atomically one at a time, and checks their hashes. It reverts those files after a caught write failure. An interrupted transaction remains recoverable through `rollback`. Use `--accept-skipped` only after agreeing how those records will be handled; report them explicitly.

6. Import `bookmarks.html` through Zen's bookmark **Import HTML** command. The export includes both ordinary bookmarks and a separate sidebar archive. Do this once; HTML import adds entries and repeating it creates duplicates. Use native Restore only if the user explicitly requested replacement and has a bookmark backup.
7. Migrate extensions, settings and shortcuts using [extensions-and-settings.md](references/extensions-and-settings.md). Preserve enabled/disabled status and use official Firefox packages. Reconcile content separately from extension installation.

## Optional Arc workflows

For Easel/FigJam, Little Arc, external URLs, workspace routing or cross-device sync, read [optional-workflows.md](references/optional-workflows.md). The bundled `assets/zen-link-preview/` contains a configurable macOS WebKit preview. Use it only when the user wants this behavior. Its login storage is separate from Zen; installing the skill does not install the app or change the default browser.

## Verify and finish

Run `verify --work "$WORK"` after a clean Zen shutdown. It checks native tabs by stable ID, URL, Space, pin/Essential flags, and container. Also check the live UI: Space order, Favorites sharing, one tab per source item, hierarchy, bookmark titles/URLs/order, extension content, chosen shortcut behavior, theme, and external-link handoff if configured. Compare counts and content, not just screenshots. Record untested paths rather than marking them passed.

If rollback is needed, quit Zen and run:

```sh
python3 "$SKILL_ROOT/scripts/migrate.py" rollback --work "$WORK"
```

This restores the full pre-apply profile and retains the later profile in a sibling directory for recovery. Bookmark or extension changes made after apply will therefore also revert; retain the printed recovery path.

Give the user a concise local migration report: what transferred, what was converted, what requires login/manual completion, evidence from restart, and backup/rollback paths. Passwords, cookies, payment data, passkeys, wallet keys and authentication tokens are outside the default migration. Do not infer they transferred from a successful tab import.
