# Native adapter and limits

The helper reads Arc's alternating Swift Codable maps for `items`, `spaces`, and `containerIDs`. It recognizes the global sidebar object by keys rather than assuming array position 1. `topAppsContainerIDs` associates Favorites with a profile. An Arc profile may have multiple Spaces.

The supported native Zen layout has `tabs`, `spaces`, `folders`, `groups` and `splitViewData` in `zen-sessions.jsonlz4`, plus a Firefox `sessionstore.jsonlz4` with one non-private window. Existing session fields, tabs, folders, closed-tab state, and Spaces are retained. The helper appends imported Spaces and merges pins before ordinary tabs. It does not write the Places SQLite database.

New tab fields include `zenSyncId`, `zenWorkspace`, `zenEssential`, `pinned`, `userContextId`, `groupId` and `_zenPinnedInitialState`. Each new entry carries the serialized system principal (`{"3":{}}`) as `triggeringPrincipal_base64`, as Zen stores for pinned tabs. New IDs are UUIDv5 values scoped to the importer. Containers get labels `Arc — <profile directory>` and IDs allocated from `lastUserContextId`; Firefox's internal identities near UINT32_MAX (such as `userContextIdInternal.webextStorageLocal`) are ignored, because IDs above 32 bits crash Zen when such a tab loads.

Pinned Arc folders follow the layout Zen's `storeDataForSessionStore` writes: a `folders` entry (with `parentId` and `prevSiblingInfo` for nesting) mirrored by a `groups` entry with the same ID, one `zenIsEmpty` `about:blank` placeholder tab listed in `emptyTabIds`, and contained tabs tagged with their innermost folder's `groupId` in sidebar order. Folders and groups are mirrored into the window state. Nesting beyond Zen's default `zen.folders.max-subfolders` (5) is refused.

The Mozilla wrapper is `mozLz40\0` followed by a little-endian decoded length and an LZ4 block. The dependency-free encoder writes valid literal-only blocks; these are larger than compressed files, and Zen can recompress them on shutdown. The decoder supports match sequences and rejects malformed offsets, truncated lengths and output over 128 MiB.

## Unsupported input

- Arc split views and folders outside pinned tabs: export hierarchy, inspect raw local source, and recreate using the UI. The adapter refuses a native plan when these or unresolved items are detected.
- More than one global Arc sidebar object: inspect the schema rather than guessing a winner.
- More than one saved Zen window: close extra windows through the UI, quit, and prepare again, or implement and test an explicit merge for that version.
- Extension URLs: install the target extension first, open its page, and derive its real target UUID. Supply exact old→new URLs through `--url-map`. Never reuse a UUID from another computer.
- Non-HTTP(S) bookmark URLs: listed in `bookmark-report.json`, retained in source snapshots, excluded from executable HTML links. Migrate intentional bookmarklets or local file links separately after review.
- Archived tabs, cookies, browser history, passwords, wallet state and extension databases: not transferred by the native helper.
- Workspace color: a base-color approximation. Noise, intensity, wallpaper, favicons, split geometry and custom icons require UI follow-up.

## Recovery

`apply` checks hashes before backup and again afterward, then writes a transaction record. Caught failures restore the four original files. For an interrupted write or a failed UI restart check, `rollback` restores the **whole** pre-apply profile. It renames the later profile to a unique sibling and never deletes it. This also reverts later extensions/bookmarks/settings, which remain recoverable from that sibling.

Keep the work directory and backup intact until the user accepts the result. Never put the full backup in Git, a public issue or a release attachment.

Schema reference: [Zen source](https://github.com/zen-browser/desktop), especially `ZenSessionManager.sys.mjs`, `ZenWorkspaces.mjs`, `ZenSessionStore.mjs` and `ZenKeyboardShortcuts.mjs` from the installed version. Source investigation does not establish that a later version behaves identically.
