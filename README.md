# Arc → Zen · Agent Skill

Bring your Arc workflow to Zen: Spaces, containers, Favorites, pinned tabs, bookmarks, extension content, shortcuts, and an optional Little Arc style link preview.

An installable skill for **Codex, Claude Code, and Agent Skills compatible agents**, built from a real macOS migration. Includes executable helpers, verification steps, and rollback tools.

[简体中文](README.zh-CN.md) · [Skill instructions](skills/arc-to-zen/SKILL.md) · [Migration workflow](skills/arc-to-zen/references/migration-workflow.md)

## Install and ask your agent

Requires Python 3.9+ and Git. The migration helpers use the Python standard library; no `pip install` is needed.

```sh
git clone https://github.com/AntonyLL/arc-to-zen-skill.git
cd arc-to-zen-skill
python3 install.py --agent codex
```

For Claude Code:

```sh
python3 install.py --agent claude
```

For other agents, use `--agent agents` to install into `~/.agents/skills/arc-to-zen`, or `--dest /path/to/your/skills/arc-to-zen` to choose a destination. The installer stops if that directory already exists, preserving any local customization. You can also download the repository ZIP, extract it, and run the installer.

Start a new agent conversation and ask:

> Use $arc-to-zen to migrate my Arc workflow to Zen, preserving Spaces, Favorites, pinned tabs, bookmarks, extension content, and shortcuts. Inspect the current setup, migrate it, and verify persistence after restart.

Agents that use slash commands, including Claude Code, can invoke `/arc-to-zen`. You can also ask your agent to read `skills/arc-to-zen/SKILL.md` directly.

**Installing the skill copies skill files only.** Browser migration, extension installation, link-preview setup, and default-browser changes happen when you invoke the skill, according to your request.

## What's included

| Feature | Approach |
|---|---|
| Spaces, Favorites, pinned and ordinary tabs | Native session adapter adds imported content while preserving existing Zen data |
| Arc profiles → Zen containers | A fresh container per Arc profile; Spaces sharing a profile share a container |
| Bookmarks across profiles and a sidebar archive | Importable HTML preserving nested bookmarks and duplicate URLs |
| Extensions, OneTab, uBlock settings, and saved content | Agent follows official import/export flows and records compatibility gaps |
| Shortcuts, themes, and layout | Map the user's actual configuration and check for conflicts |
| Backup, verification, and rollback | File hashes, a full profile backup, atomic file replacements, and recovery commands |
| Little Arc alternative | Optional Swift/WebKit app with one reusable window and ⌘O handoff to Zen |
| Easel / FigJam | Guidance for a fixed board, system shortcut, and workspace routing |

## Compatibility

- **Native profile changes and the preview app target macOS.** Install and launch Arc and Zen once before migration. Building the optional preview also requires macOS 13+ and Xcode Command Line Tools.
- The original migration used **Arc 1.169.0 → Zen 1.23.4b**. Check the actual data format when using newer browser versions.
- The v1 native adapter handles **flat Arc sidebars and a saved Zen session with one window**. Sidebar folders and split views are exported for the agent to reconstruct in Zen; the helper stops before native writes when it detects those structures.
- Containers preserve the organization of separate accounts; websites require a fresh login. Passwords, cookies, payment information, wallet keys, and browser history are outside the default migration scope.
- The preview uses its own persistent WebKit website storage. **Open in Zen** hands off the current URL; Zen extensions, containers, and unfinished forms are not shared.

A lesson from the original migration: **check Zen's “clear cookies/site data on exit” settings before restarting** to avoid unexpectedly losing existing logins.

## Use the helpers directly

The agent can discover paths for you. For manual use, keep the working directory outside browser profiles and this repository.

```sh
python3 skills/arc-to-zen/scripts/migrate.py discover
python3 skills/arc-to-zen/scripts/migrate.py inspect \
  --arc "$HOME/Library/Application Support/Arc"

# Export bookmarks and an inventory locally, without changing browser profiles.
python3 skills/arc-to-zen/scripts/migrate.py prepare \
  --arc "$HOME/Library/Application Support/Arc" \
  --out "$HOME/Documents/Arc-to-Zen-export"
```

To stage a native migration, quit Zen, choose a fresh working directory, and add `--zen-profile '/path/to/your/Zen/profile'` to the preparation command. Review the generated `manifest.json`, then run:

```sh
python3 skills/arc-to-zen/scripts/migrate.py apply --work '/path/to/migration-work'
python3 skills/arc-to-zen/scripts/migrate.py verify --work '/path/to/migration-work'
# Quit Zen before rolling back. The complete later profile is also preserved.
python3 skills/arc-to-zen/scripts/migrate.py rollback --work '/path/to/migration-work'
```

Import bookmarks through Zen's **Import HTML** command. Import once; repeating the import creates duplicates. `verify` checks the disk snapshot, so the agent must also inspect the UI and persistence after restart.

## Validation and data

```sh
python3 -m unittest discover -s tests -v
```

Tests use temporary synthetic profiles to check parsing, exports, additive session changes, stale-plan rejection, failure recovery, and rollback. An [optional GitHub Actions template](examples/github-actions.yml) can be placed at `.github/workflows/test.yml` to run the Python tests and build the Swift app; remote CI is not enabled in this release.

Validation of the original local migration is separate from automated testing of these generalized helpers. The generalized package has not been run as a new live migration.

The repository contains reusable code, instructions, and synthetic test data. Personal bookmarks, browser profiles, login data, and board URLs are excluded. Files generated during migration remain on the user's computer.

The skill follows the [Agent Skills format](https://agentskills.io/specification). See the [native format notes](skills/arc-to-zen/references/native-format.md) for adapter details and the [optional workflows](skills/arc-to-zen/references/optional-workflows.md) for the preview app and FigJam setup. The preview is built and ad-hoc signed locally; no notarized binary is distributed.

Released under the [MIT License](LICENSE).
