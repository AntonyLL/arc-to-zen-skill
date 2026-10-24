# Optional Arc workflows

## Little Arc style external-link preview

Zen Glance handles previews within Zen. An external App's HTTP(S) link requires a system URL handler for the standalone-window workflow.

The bundled Swift app opens external web links directly in one reusable native WebKit window. It avoids creating an ordinary Zen window first. ⌘O or **Open in Zen** hands the current URL to Zen explicitly and closes the preview; Esc/⌘W closes it; ⌘R refreshes. External-app schemes and downloads are left for Zen. A new external link replaces the current preview.

The preview uses its own persistent WebKit cookies/cache. It does not share Zen logins, extensions or containers. Handoff transfers a URL, not page state or unfinished forms. Explain this when selecting the workflow. The source strategy verified the predecessor app with Zen running; Zen cold-start behavior needs its own test on the recipient's machine.

Build locally with Xcode Command Line Tools installed:

```sh
python3 "$SKILL_ROOT/assets/zen-link-preview/build.py" --output "$WORK/preview-build"
```

The output is ad-hoc signed for local use, not Apple notarized. The builder does not change browser defaults or overwrite installed applications. Install the resulting app under `~/Applications` if requested. LaunchServices normally discovers an installed/opened app; use macOS Settings → Desktop & Dock → Default web browser to choose **Zen Link Preview** when the user requests preview as the default entry point. Record the previous default for rollback. Do not disable Gatekeeper to distribute a build; source builds are the supported package.

Configure URLs that should go directly to Zen, such as a personal board, with the app's preference domain:

```sh
defaults write io.github.AntonyLL.ZenLinkPreview directURLs -array 'https://example.com/your-board'
```

This matches normalized host and exact path (ignoring a trailing slash, query and fragment); it does not match all subdomains. Replace the example with a URL supplied/selected by the user. Quit and reopen the preview after a configuration change. Defaults are an empty bypass list and Zen's registered application location. The public source contains no personal board IDs.

Rollback: restore the recorded default browser in System Settings, quit the preview, and move its app to Trash if requested. Its website data is separate; don't erase it without a request.

## Easel → fixed FigJam board

Use an existing user-selected board, or create one when the user requests it. Keep access restricted as chosen by the user. Bookmark/pin the fixed URL; an Arc-style ⌃⇧E system Shortcut can open that URL if requested.

Bind a fixed board to the intended Zen Space/container using a narrow Space Routing rule. Test from another Space; opening the right URL in the wrong container can display a login page. Derive the current Space UUID and container ID locally; do not copy IDs from the original migration. Route the board directly to Zen when its Zen login matters. Opening a URL may create another tab; do not claim it focuses an existing one unless tested.

## Browser-native popup extension alternative

A signed official popup extension can preserve the origin tab's Firefox container, but extension commands may omit `cookieStoreId`. Verify the actual source and popup IDs. A default browser relay that creates a normal window and then converts it to a popup can visibly flash. Use the native preview if the user prioritizes immediate single-window behavior and accepts separate login state.

Do not leave an old “auto-convert every single-tab window” rule enabled when it interferes with normal Zen handoff. Check conflicts between Zen's ⌘O and preview/extension commands in their respective contexts.

## Cross-device continuity

Inspect the current Zen/Mozilla account's enabled sync categories. Extensions and some Zen Space/theme fields may sync, while individual extension settings depend on each extension. Zen Mods/CSS need their own export/import or a deliberate file copy. Avoid describing sync as verified until a second device has been checked. Authentication, OS Shortcuts, a locally built preview app and macOS default-browser selection are separate per-device setup.
