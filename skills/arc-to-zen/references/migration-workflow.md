# Migration workflow

## Working directory and source capture

Keep generated material under a dated, private directory such as `~/Documents/Arc-to-Zen-YYYYMMDD-HHMMSS`. It contains browsing data. The public skill directory should contain code and instructions only.

Identify the active Arc profile directories from Spaces' `profile` fields and the browser UI. Read `StorableSidebar.json` for the sidebar and `<profile>/Bookmarks` for Chromium bookmarks; they are different collections. Inventory all profiles, including those with bookmarks/extensions but no visible Space. The script's HTML exporter searches all immediate profile directories with a Bookmarks file.

For live sources, close Arc before final capture. Copy only files needed for the task. Use extension-native exports for extension content. Never recursively dump extension storage to discover what it contains: it can include auth tokens or wallet material. The provided `prepare` snapshots only the sidebar and Bookmarks files. Its full Zen backup happens immediately before apply and stays local.

Before closing Zen for the first time, check Settings → Privacy & Security → history/cookies cleanup on exit. The source migration exposed an existing target preference that erased logins during restart. Turning the preference off afterward cannot restore already-deleted cookies. Preserve user-selected privacy behavior unless they ask to change it.

## Mapping

| Arc | Zen | Decision |
|---|---|---|
| Space | Workspace/Space | Keep names and order; duplicate names remain distinct |
| Profile | Container | One shared container for Spaces using the same Arc profile |
| Favorites | Essentials | Profile-scoped, shared between corresponding Spaces |
| Pinned tabs | Pinned tabs | Preserve label, URL, and mute state |
| Ordinary tabs | Ordinary tabs | Preserve source order |
| Folders / split views | Native folders / splits | Inspect current schema or recreate in UI; v1 helper exports hierarchy only |
| Chromium bookmarks | Zen bookmark HTML import | Additive by default; retain duplicates and nested folders |
| Custom Space color | Zen gradient color | Approximation; inspect appearance in UI |
| Arc profile login | Re-login in matching container | Containers do not copy Chromium authentication |

Containers separate website sessions. Extensions, history, and many preferences remain global within a Zen profile. Do not promise full Arc Profile equivalence. Official description: [Zen Workspaces](https://docs.zen-browser.app/user-manual/workspaces).

## Native path

Use `prepare --zen-profile` with an initialized profile saved with one non-private window. Close all Zen processes first. Both `zen-sessions.jsonlz4` and `sessionstore.jsonlz4` must exist; launch Zen once and quit normally if necessary. Do not invent an empty template from an old schema.

Review `manifest.json`: target path, added Space/tab counts, new container assignments, skipped URLs, and the two session-restoration/Essentials preferences. Import IDs are deterministic so a second import of the same Arc Spaces is refused. No update/synchronization semantics are implied.

`apply` checks the target has not changed since preparation. When stale, make a fresh preparation; do not edit expected hashes to force it through. A full backup and `transaction.json` are written before the profile changes. Four file replacements are individually atomic, not a single filesystem transaction. Leave Zen closed throughout; if power loss interrupts the sequence, run rollback before launching it.

## Completion checks

- Compare source and target Space and tab counts by category. Explain exclusions individually.
- Verify URLs, names, order, pin/Essential flags, containers, and shared Favorites. A title or URL alone is not a unique tab identifier.
- For bookmarks, compare a fresh target export with source entries, accounting separately for the sidebar archive and extension-content bookmarks. Empty titles may be represented differently by Firefox.
- For OneTab, compare export text before/after including group separators. Group dates may change.
- Check all extensions for installed/enabled/disabled state; test content and preferences separately.
- Test representative non-destructive shortcuts. Do not clear tabs merely to test a shortcut.
- Restart once and check persistence. If native data has drifted after navigation or redirects, inspect the changed entries; do not call it data loss without evidence.
- For optional preview, check reuse, navigation, handoff, Esc/⌘W, and default URL handling. Test Zen cold start separately if authorized; do not infer it from a test with Zen running.

Use four honest status values in the report: verified, converted, pending, unavailable. Preserve backup locations and exact untested behavior. The original strategy was exercised on macOS with Arc 1.169.0 and Zen 1.23.4b; the generalized helpers need validation against each target version.
