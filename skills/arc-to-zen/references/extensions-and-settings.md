# Extensions, settings and shortcuts

## Extension migration

Inventory each Arc profile's extensions through `arc://extensions` and manifests. Record name, publisher, enabled state and user configuration. Match with the publisher's official Firefox listing on [Mozilla Add-ons](https://addons.mozilla.org/firefox/) or an official vendor link. Versions and availability change: verify at execution time rather than freezing old version numbers.

Installing an extension, transferring its saved content, and restoring its settings are three distinct results. Firefox extension binaries and UUIDs differ from Chromium. Do not copy Chromium extension directories into Zen or claim logins/vaults transferred.

| Type | Procedure |
|---|---|
| OneTab | Use its Import/Export text UI. Preserve blank-line group boundaries; compare exact exports. Creation dates may become import dates. |
| uBlock Origin | Use its official backup/restore format for filter choices, trusted sites, rules and switches. Check compatibility before importing. |
| Zotero, shopping or VPN extensions | Install official Firefox counterpart, preserve enabled state, review permissions; authenticate separately. Do not activate a VPN just to test installation. |
| Bitwarden | Install official counterpart and keep vault data in the vendor's normal flow. Do not export a vault for this migration. |
| MetaMask and other wallets | Extension installation is separate from wallet transfer. Never inspect or migrate recovery phrases/private keys. |
| Phew or other tab managers without Firefox support | Prefer a native URL export; convert saved titles, URLs and grouping to local bookmark HTML. Record lost automation/AI/sync behavior. |
| Gemini Voyager | Export saved conversation URLs and folders; check the current extension's import schema before restoring configuration. Old storage schemas may be incompatible. |
| Chromium-only integrations | Record the limitation and preserve the source. Propose a substitute only when useful to the user's workflow. |

The original migration used local extension storage only when native export could not recover needed saved URLs. A `.log`-only LevelDB scan is incomplete: newer values can be in `.ldb` tables, and tombstones/sequence ordering matter. For a specific authorized extension export, work on a closed copy and use a maintained reader; never sweep all extension storage or print secret-bearing fields. No raw LevelDB extractor is bundled.

## Settings

Read source values before mapping. Check search engine, download-location prompt, languages, fonts, content theme, session restore, toolbar position, sidebar width, compact-mode behavior and recently-used tab order. Do not turn one person's fonts, language list or colors into universal defaults.

Prefer Zen UI. If a targeted preference edit is necessary, back up `prefs.js`, ensure Zen is closed, preserve unrelated values, and read the value back after restart. Avoid persistent `user.js` overrides for ordinary migration settings. Zen themes may need version-specific migration flags; verify the current format instead of blindly applying a legacy flag.

## Arc-like shortcut starter map (macOS)

Use only where the user wants their Arc keys. Inspect current `zen-keyboard-shortcuts.json` and native command IDs before writing. Preserve unrelated shortcuts and review collisions with OS and extensions.

| Action | Common Arc mapping | Zen nuance |
|---|---|---|
| Pin / unpin | ⌘D | Conflicts with ordinary bookmark command |
| Sidebar show/hide | ⌘S | Conflicts with Save Page; compact mode behavior varies |
| Save Page | ⇧⌘S | May collide with Zotero |
| Next / previous Space | ⌥⌘→ / ⌥⌘← | Use current workspace commands |
| Space 1–4 | ⌃1–4 | Map only Spaces that exist |
| Next / previous tab | ⌥⌘↓ / ⌥⌘↑ | Native tab navigation, not custom script evaluation |
| Extensions | ⌘E | Native add-ons manager |
| Downloads | ⇧⌘J | Native downloads |
| Library | ⇧⌘L | May collide with Bitwarden |
| Private window | ⇧⌘N | Preserve normal privacy behavior |
| New split | ⌃⇧= | Native Zen split |
| Unsplit | ⌃⇧− | Different from closing just one Arc split pane |
| Plain-text paste | ⇧⌘V | Native paste-without-formatting command |
| Copy URL / Markdown link | ⇧⌘C / ⌥⇧⌘C | Check current Zen defaults |
| Screenshot | ⇧⌘2 | Webpage screenshot, not Arc Capture/Easel |

Zen may reserve ⌥⌘U, ⌥⌘H or ⌥⌘G for split commands that collide with source/system actions. Clear a collision only when applying the intended replacement. Arc Archive, Notes, Max, Join Meeting, Developer Mode and tab-deletion schedules have no assumed exact counterparts. Never add automatic tab deletion to mimic Arc's archive without a specific request.
