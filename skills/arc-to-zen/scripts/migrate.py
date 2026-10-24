#!/usr/bin/env python3
"""Arc → Zen local migration helpers. Python 3.9+, standard library only."""
import argparse
import configparser
import copy
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit
import uuid

MAGIC = b"mozLz40\0"
MAX_SIZE = 128 * 1024 * 1024
NATIVE_FILES = ("zen-sessions.jsonlz4", "sessionstore.jsonlz4", "containers.json", "prefs.js")
NAMESPACE = uuid.UUID("c7f05006-9624-43c3-a2f2-fcbe3d3f2911")


class MigrationError(ValueError):
    pass


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    Path(path).chmod(0o600)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def decode_mozlz4(data):
    """Decode a size-prefixed raw LZ4 block in Mozilla's JSON wrapper."""
    if len(data) < 13 or data[:8] != MAGIC:
        raise MigrationError("Not a Mozilla JSON LZ4 file")
    expected = struct.unpack_from("<I", data, 8)[0]
    if expected > MAX_SIZE:
        raise MigrationError("Session exceeds the 128 MiB decoded limit")
    pos, out = 12, bytearray()

    def length(base):
        nonlocal pos
        total = base
        if base == 15:
            while True:
                if pos >= len(data):
                    raise MigrationError("Truncated LZ4 length")
                part = data[pos]
                pos += 1
                total += part
                if part != 255:
                    break
        return total

    while pos < len(data):
        token = data[pos]
        pos += 1
        count = length(token >> 4)
        if pos + count > len(data) or len(out) + count > expected:
            raise MigrationError("Invalid LZ4 literal length")
        out.extend(data[pos:pos + count])
        pos += count
        if pos == len(data):
            break
        if pos + 2 > len(data):
            raise MigrationError("Truncated LZ4 offset")
        offset = struct.unpack_from("<H", data, pos)[0]
        pos += 2
        if not offset or offset > len(out):
            raise MigrationError("Invalid LZ4 offset")
        count = length(token & 15) + 4
        if len(out) + count > expected:
            raise MigrationError("LZ4 output exceeds its declared length")
        for _ in range(count):
            out.append(out[-offset])
    if len(out) != expected:
        raise MigrationError("LZ4 output length mismatch")
    return json.loads(out)


def encode_mozlz4(value):
    # A valid all-literals LZ4 block avoids third-party runtime dependencies.
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(raw) > MAX_SIZE:
        raise MigrationError("Session exceeds the 128 MiB encoded limit")
    block = bytearray([min(len(raw), 15) << 4])
    if len(raw) >= 15:
        remaining = len(raw) - 15
        while remaining >= 255:
            block.append(255)
            remaining -= 255
        block.append(remaining)
    block.extend(raw)
    return MAGIC + struct.pack("<I", len(raw)) + block


def read_session(path):
    return decode_mozlz4(Path(path).read_bytes())


def pairs(value, label):
    if isinstance(value, dict):
        return value
    if not isinstance(value, list) or len(value) % 2:
        raise MigrationError("Unsupported Arc " + label + " map")
    result = {}
    for key, item in zip(value[::2], value[1::2]):
        if not isinstance(key, str) or key in result:
            raise MigrationError("Invalid or duplicate key in Arc " + label)
        result[key] = item
    return result


def profile_name(value):
    if "default" in value:
        return "Default"
    try:
        name = value["custom"]["_0"]["directoryBasename"]
    except (KeyError, TypeError):
        raise MigrationError("Unknown Arc profile encoding")
    if not isinstance(name, str) or not name or Path(name).name != name or name in (".", ".."):
        raise MigrationError("Invalid Arc profile directory name")
    return name


def web_url(url):
    if not isinstance(url, str):
        return False
    try:
        parsed = urlsplit(url)
        return parsed.scheme.lower() in ("http", "https") and bool(parsed.hostname)
    except ValueError:
        return False


def arc_inventory(root):
    root = Path(root).expanduser().resolve()
    sidebar = load_json(root / "StorableSidebar.json")
    # Swift Codable dictionaries may be alternating key/value lists.
    raw = sidebar.get("sidebar", {}).get("containers")
    values = list(raw.values()) if isinstance(raw, dict) else raw
    candidates = [v for v in values or [] if isinstance(v, dict) and "spaces" in v and "items" in v]
    if len(candidates) != 1:
        raise MigrationError("Expected one Arc sidebar container; inspect this schema before migrating")
    source = candidates[0]
    items = pairs(source["items"], "items")
    spaces = pairs(source["spaces"], "spaces")
    records, folders, issues, visited = [], [], [], set()

    def walk(iid, sid, profile, kind, trail=(), stack=()):
        if iid in stack:
            raise MigrationError("Cycle in Arc sidebar")
        if iid not in items:
            raise MigrationError("Arc references a missing sidebar item")
        if iid in visited:
            raise MigrationError("Arc sidebar item is referenced more than once")
        visited.add(iid)
        item = items[iid]
        data = item.get("data", {})
        if "tab" in data:
            tab = data["tab"]
            url = tab.get("savedURL") or ""
            records.append({"arc_id": iid, "space_id": sid, "profile": profile,
                            "kind": kind, "folders": list(trail), "folder_ids": list(stack),
                            "order": len(visited), "url": url,
                            "title": item.get("title") or tab.get("savedTitle") or url,
                            "muted": tab.get("savedMuteStatus") == "muted"})
            if item.get("childrenIds"):
                issues.append({"item": iid, "reason": "Tab has children; inspect Arc split/group schema"})
            return
        children = item.get("childrenIds")
        if not isinstance(children, list):
            issues.append({"item": iid, "reason": "Unsupported non-tab item"})
            return
        title = item.get("title") or "Untitled folder"
        folders.append({"arc_id": iid, "space_id": sid, "profile": profile,
                        "kind": kind, "path": list(trail) + [title],
                        "ids": list(stack) + [iid], "order": len(visited)})
        for child in children:
            walk(child, sid, profile, kind, trail + (title,), stack + (iid,))

    normalized_spaces = []
    for sid, space in spaces.items():
        profile = profile_name(space["profile"])
        normalized_spaces.append({"id": sid, "name": space.get("title") or "Arc Space", "profile": profile,
                                  "theme": space.get("customInfo", {}).get("windowTheme", {})})
        containers = pairs(space["containerIDs"], "space containers")
        for kind in ("pinned", "unpinned"):
            cid = containers.get(kind)
            if cid is None:
                continue
            if cid not in items:
                raise MigrationError("Missing Arc space root")
            visited.add(cid)
            for iid in items[cid].get("childrenIds", []):
                walk(iid, sid, profile, kind)
    top = source.get("topAppsContainerIDs", [])
    if not isinstance(top, list) or len(top) % 2:
        raise MigrationError("Unsupported Arc Favorites map")
    for p, cid in zip(top[::2], top[1::2]):
        profile = profile_name(p)
        if cid not in items:
            raise MigrationError("Missing Arc Favorites root")
        matching = [s for s in normalized_spaces if s["profile"] == profile]
        if not matching:
            if items[cid].get("childrenIds"):
                issues.append({"profile": profile, "reason": "Favorites belong to a profile with no Space"})
            continue
        visited.add(cid)
        for iid in items[cid].get("childrenIds", []):
            walk(iid, matching[0]["id"], profile, "favorite")
    for iid, item in items.items():
        if iid not in visited and "tab" in item.get("data", {}):
            issues.append({"item": iid, "reason": "Unreferenced tab; preserved in source snapshot"})
    return {"schema": 1, "spaces": normalized_spaces, "tabs": records, "folders": folders,
            "issues": issues, "counts": {"spaces": len(spaces), "tabs": len(records),
            "favorites": sum(t["kind"] == "favorite" for t in records),
            "pinned": sum(t["kind"] == "pinned" for t in records), "folders": len(folders)}}


def bookmark_document(root, inventory):
    """Netscape HTML: ordinary bookmarks plus a hierarchical sidebar archive."""
    lines = ['<!DOCTYPE NETSCAPE-Bookmark-file-1>', '<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">',
             '<TITLE>Arc migration</TITLE>', '<H1>Arc migration</H1>', '<DL><p>']
    count, omitted = 0, []

    def link(title, url):
        nonlocal count
        if not web_url(url):
            omitted.append({"title": title, "url": url, "reason": "Non-HTTP(S) URL retained in local inventory"})
            return
        lines.append('<DT><A HREF="' + html.escape(url, quote=True) + '">' + html.escape(title or url) + '</A>')
        count += 1

    def folder(name, children):
        lines.extend(['<DT><H3>' + html.escape(name or "") + '</H3>', '<DL><p>'])
        children()
        lines.append('</DL><p>')

    def nodes(children):
        for node in children:
            if node.get("type") == "url":
                link(node.get("name"), node.get("url", ""))
            elif node.get("type") == "folder":
                folder(node.get("name"), lambda n=node: nodes(n.get("children", [])))
            else:
                raise MigrationError("Unknown Chromium bookmark node type")

    root = Path(root)
    profiles = sorted(p for p in root.iterdir() if p.is_dir() and (p / "Bookmarks").is_file())
    bookmark_sources = []
    for profile in profiles:
        document = load_json(profile / "Bookmarks")
        bookmark_sources.append(profile.name)
        def profile_children():
            for key, node in document["roots"].items():
                if isinstance(node, dict) and "children" in node:
                    folder(node.get("name") or key, lambda n=node: nodes(n["children"]))
        folder("Arc bookmarks — " + profile.name, profile_children)
    for space in inventory["spaces"]:
        selected = [t for t in inventory["tabs"] if t["space_id"] == space["id"]]
        selected_folders = [f for f in inventory["folders"] if f["space_id"] == space["id"]]
        def space_children():
            for kind, label in (("favorite", "Favorites"), ("pinned", "Pinned"), ("unpinned", "Open tabs")):
                def kind_children():
                    tree = {"tabs": [], "children": {}}
                    for f in selected_folders:
                        if f["kind"] == kind:
                            branch = tree
                            for fid, title in zip(f["ids"], f["path"]):
                                branch = branch["children"].setdefault(fid, {"title": title, "order": f["order"], "tabs": [], "children": {}})
                            branch["order"] = f["order"]
                    for tab in selected:
                        if tab["kind"] == kind:
                            branch = tree
                            for fid in tab["folder_ids"]:
                                branch = branch["children"][fid]
                            branch["tabs"].append(tab)
                    def emit(branch):
                        entries = [(t["order"], "tab", t) for t in branch["tabs"]]
                        entries += [(c["order"], "folder", c) for c in branch["children"].values()]
                        for _, kind, item in sorted(entries, key=lambda entry: entry[0]):
                            if kind == "tab":
                                link(item["title"], item["url"])
                            else:
                                folder(item["title"], lambda c=item: emit(c))
                    emit(tree)
                folder(label, kind_children)
        folder("Arc sidebar — " + space["name"], space_children)
    lines.append('</DL><p>')
    return "\n".join(lines) + "\n", {"exported_links": count, "bookmark_profiles": bookmark_sources, "omitted": omitted}


def require_closed():
    if sys.platform != "darwin":
        raise MigrationError("Native profile apply/rollback is supported on macOS only")
    result = subprocess.run(["ps", "-axo", "comm="], capture_output=True, text=True, check=True)
    for command in result.stdout.splitlines():
        if command.strip().lower().endswith(("/zen", "/zen-bin")):
            raise MigrationError("Quit every Zen process before changing its profile")


def checked_profile(path):
    profile = Path(path).expanduser().resolve()
    if not profile.is_dir():
        raise MigrationError("Zen profile directory does not exist")
    for name in NATIVE_FILES:
        if (profile / name).is_symlink() or not (profile / name).is_file():
            raise MigrationError("Expected a regular initialized Zen file: " + name)
    return profile


def pref(text, key, value):
    pattern = r'^user_pref\(' + re.escape(json.dumps(key)) + r', .*\);$'
    line = "user_pref(" + json.dumps(key) + ", " + json.dumps(value) + ");"
    if re.search(pattern, text, re.M):
        return re.sub(pattern, lambda _: line, text, flags=re.M)
    return text + "\n" + line + "\n"


def native_plan(inventory, profile, url_map=None):
    profile = checked_profile(profile)
    before = {name: digest(profile / name) for name in NATIVE_FILES}
    z = read_session(profile / NATIVE_FILES[0])
    session = read_session(profile / NATIVE_FILES[1])
    containers = load_json(profile / "containers.json")
    if any(not isinstance(z.get(key), list) for key in ("tabs", "spaces", "folders", "groups", "splitViewData")):
        raise MigrationError("Unsupported Zen sidebar schema")
    windows = session.get("windows", [])
    if len(windows) != 1 or windows[0].get("isPrivate"):
        raise MigrationError("Use a Zen profile saved with one non-private window")
    window = windows[0]
    if not isinstance(window.get("tabs"), list) or not window["tabs"]:
        raise MigrationError("Initialize Zen with an ordinary tab before preparing")
    if not isinstance(containers.get("identities"), list) or not isinstance(containers.get("lastUserContextId"), int):
        raise MigrationError("Unsupported Zen containers schema")
    if inventory["folders"] or inventory["issues"]:
        raise MigrationError("Native helper supports flat Arc sidebars only. Use bookmarks.html and inventory.json to recreate folders/splits in Zen; no profile was changed.")
    contexts, new_spaces, new_tabs, skipped = {}, [], [], []
    existing_contexts = [i.get("userContextId", 0) for i in containers["identities"]]
    next_context = max([containers["lastUserContextId"]] + existing_contexts)
    for space in inventory["spaces"]:
        p = space["profile"]
        if p not in contexts:
            next_context += 1
            contexts[p] = next_context
            containers["identities"].append({"userContextId": next_context, "public": True,
                "icon": "briefcase", "color": "blue", "name": "Arc — " + p})
    containers["lastUserContextId"] = next_context
    sid_map = {s["id"]: str(uuid.uuid5(NAMESPACE, "space:" + s["id"])) for s in inventory["spaces"]}
    existing_ids = {s["uuid"] for s in z["spaces"]}
    if existing_ids.intersection(sid_map.values()):
        raise MigrationError("These Arc spaces already exist in the target; refusing a duplicate import")
    position = max([s.get("position", 0) for s in z["spaces"]] + [0])
    for n, s in enumerate(inventory["spaces"], 1):
        theme = None
        color = s["theme"].get("primaryColorPalette", {}).get("midTone")
        if color and all(isinstance(color.get(k), (int, float)) for k in ("red", "green", "blue")):
            rgb = [round(max(0, min(1, color[k])) * 255) for k in ("red", "green", "blue")]
            theme = {"type": "gradient", "gradientColors": [{"c": rgb, "isCustom": False,
                      "algorithm": "floating", "isPrimary": True}], "opacity": 0.5, "texture": 0, "rotation": 0}
        new_spaces.append({"uuid": sid_map[s["id"]], "name": s["name"], "icon": None,
            "containerTabId": contexts[s["profile"]], "position": position + n * 1000,
            "theme": theme, "hasCollapsedPinnedTabs": False})
    url_map = url_map or {}
    for t in inventory["tabs"]:
        url = url_map.get(t["url"], t["url"])
        mapped_extension = t["url"] in url_map and urlsplit(url).scheme == "moz-extension" and bool(urlsplit(url).hostname)
        if not (web_url(url) or url == "about:blank" or mapped_extension):
            skipped.append({"arc_id": t["arc_id"], "url": t["url"], "reason": "Needs native extension URL mapping or manual migration"})
            continue
        entry = {"url": url, "title": t["title"]}
        pinned = t["kind"] != "unpinned"
        tab = {"entries": [entry], "index": 1, "lastAccessed": int(time.time() * 1000),
               "hidden": False, "zenWorkspace": sid_map[t["space_id"]],
               "zenSyncId": str(uuid.uuid5(NAMESPACE, "tab:" + t["arc_id"])),
               "zenEssential": t["kind"] == "favorite", "pinned": pinned,
               "zenDefaultUserContextId": "true", "zenIsEmpty": False, "zenHasStaticIcon": False,
               "userContextId": contexts[t["profile"]], "attributes": {}, "_zenIsActiveTab": False}
        if pinned:
            tab["_zenPinnedInitialState"] = {"entry": entry.copy(), "image": None}
            tab["zenStaticLabel"] = t["title"]
        if t["muted"]:
            tab["muted"] = True
        new_tabs.append(tab)
    if not new_spaces or not new_tabs:
        raise MigrationError("No supported Arc spaces/tabs to import")

    def merge_tabs(old):
        # Preserve the relative order of old tabs and keep Firefox's pinned prefix.
        return [t for t in old if t.get("pinned")] + [t for t in new_tabs if t["pinned"]] + [t for t in old if not t.get("pinned")] + [t for t in new_tabs if not t["pinned"]]

    z["tabs"] = merge_tabs(z["tabs"])
    z["spaces"].extend(new_spaces)
    z["lastCollected"] = int(time.time() * 1000)
    selected_index = window.get("selected", 1) - 1
    if not 0 <= selected_index < len(window["tabs"]):
        raise MigrationError("Invalid selected tab in Zen session")
    selected = window["tabs"][selected_index]
    window["tabs"] = merge_tabs(window["tabs"])
    window["selected"] = next(i for i, tab in enumerate(window["tabs"], 1) if tab is selected)
    window["spaces"] = copy.deepcopy(z["spaces"])
    prefs = (profile / "prefs.js").read_text(encoding="utf-8")
    for key, value in {"browser.startup.page": 3, "zen.workspaces.separate-essentials": True}.items():
        prefs = pref(prefs, key, value)
    payload = {"zen-sessions.jsonlz4": encode_mozlz4(z), "sessionstore.jsonlz4": encode_mozlz4(session),
               "containers.json": json.dumps(containers, ensure_ascii=False, indent=2).encode(), "prefs.js": prefs.encode()}
    if before != {name: digest(profile / name) for name in NATIVE_FILES}:
        raise MigrationError("Zen changed during preparation; quit Zen and prepare again")
    return payload, {"schema": 1, "profile": str(profile), "before": before,
        "after": {name: hashlib.sha256(data).hexdigest() for name, data in payload.items()},
        "spaces_added": len(new_spaces), "tabs_added": len(new_tabs), "contexts": contexts,
        "skipped": skipped, "tab_ids": [t["zenSyncId"] for t in new_tabs],
        "space_ids": [s["uuid"] for s in new_spaces],
        "preferences_changed": {"browser.startup.page": 3, "zen.workspaces.separate-essentials": True}}


def fresh_directory(path):
    path = Path(path).expanduser().resolve()
    path.mkdir(parents=True, mode=0o700, exist_ok=False)
    return path


def prepare(args):
    source = Path(args.arc).expanduser().resolve()
    out = Path(args.out).expanduser().resolve()
    for forbidden in [source, Path(args.zen_profile).expanduser().resolve() if args.zen_profile else source]:
        if out == forbidden or forbidden in out.parents:
            raise MigrationError("Output must be outside browser profile/source directories")
    inventory = arc_inventory(source)
    document, bookmark_report = bookmark_document(source, inventory)
    out = fresh_directory(out)
    (out / "bookmarks.html").write_text(document, encoding="utf-8")
    (out / "bookmarks.html").chmod(0o600)
    save_json(out / "inventory.json", inventory)
    save_json(out / "bookmark-report.json", bookmark_report)
    snapshot = fresh_directory(out / "source")
    shutil.copy2(source / "StorableSidebar.json", snapshot / "StorableSidebar.json")
    for p in source.iterdir():
        if p.is_dir() and (p / "Bookmarks").is_file():
            dest = fresh_directory(snapshot / p.name)
            shutil.copy2(p / "Bookmarks", dest / "Bookmarks")
    result = {"output": str(out), **inventory["counts"], "bookmark_links": bookmark_report["exported_links"]}
    if args.zen_profile:
        require_closed()
        url_map = load_json(args.url_map) if args.url_map else None
        payload, manifest = native_plan(inventory, args.zen_profile, url_map)
        staged = fresh_directory(out / "staged")
        for name, data in payload.items():
            (staged / name).write_bytes(data)
            (staged / name).chmod(0o600)
        save_json(out / "manifest.json", manifest)
        result["native"] = {k: manifest[k] for k in ("spaces_added", "tabs_added", "skipped", "preferences_changed")}
    print(json.dumps(result, ensure_ascii=False, indent=2))


def checked_manifest(work):
    manifest = load_json(work / "manifest.json")
    if manifest.get("schema") != 1 or set(manifest.get("before", {})) != set(NATIVE_FILES) or set(manifest.get("after", {})) != set(NATIVE_FILES):
        raise MigrationError("Invalid migration manifest")
    return manifest, checked_profile(manifest["profile"])


def write_atomic(path, data):
    fd, temporary = tempfile.mkstemp(prefix=".arc-to-zen-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def apply(work, accept_skipped=False):
    require_closed()
    work = Path(work).expanduser().resolve()
    manifest, profile = checked_manifest(work)
    if profile == work or profile in work.parents:
        raise MigrationError("Work directory must be outside the target profile")
    if manifest["skipped"] and not accept_skipped:
        raise MigrationError("Review manifest.skipped and migrate those items manually; use --accept-skipped only when that disposition is agreed")
    if (work / "transaction.json").exists() or (work / "backup-profile").exists():
        raise MigrationError("A transaction already exists; use a fresh preparation directory")
    for name in NATIVE_FILES:
        if digest(profile / name) != manifest["before"][name]:
            raise MigrationError("Zen changed since preparation; prepare again")
        if digest(work / "staged" / name) != manifest["after"][name]:
            raise MigrationError("Staged data changed; prepare again")
    # Full local profile backup also protects browser-managed data changed at restart.
    backup = work / "backup-profile"
    shutil.copytree(profile, backup, symlinks=True)
    backup.chmod(0o700)
    for name in NATIVE_FILES:
        if digest(backup / name) != manifest["before"][name]:
            raise MigrationError("Backup differs from the prepared source; no writes performed")
    require_closed()
    for name in NATIVE_FILES:
        if digest(profile / name) != manifest["before"][name]:
            raise MigrationError("Profile changed while backing up; no writes performed")
    save_json(work / "transaction.json", {"state": "applying", "backup": str(backup)})
    try:
        for name in NATIVE_FILES:
            write_atomic(profile / name, (work / "staged" / name).read_bytes())
        if any(digest(profile / n) != manifest["after"][n] for n in NATIVE_FILES):
            raise MigrationError("Post-write verification failed")
    except BaseException:
        for name in NATIVE_FILES:
            write_atomic(profile / name, (backup / name).read_bytes())
        save_json(work / "transaction.json", {"state": "reverted-after-error", "backup": str(backup)})
        raise
    save_json(work / "transaction.json", {"state": "applied", "backup": str(backup)})
    return {"state": "applied", "backup": str(backup), "next": "Start Zen and verify tabs, containers and bookmarks"}


def verify(work):
    work = Path(work).expanduser().resolve()
    manifest, profile = checked_manifest(work)
    z = read_session(profile / "zen-sessions.jsonlz4")
    actual = {t.get("zenSyncId"): t for t in z["tabs"]}
    staged = read_session(work / "staged" / "zen-sessions.jsonlz4")
    expected = {t["zenSyncId"]: t for t in staged["tabs"] if t.get("zenSyncId") in manifest["tab_ids"]}
    missing = [key for key in manifest["tab_ids"] if key not in actual]
    mismatched = []
    for key, expected_tab in expected.items():
        if key not in actual:
            continue
        tab = actual[key]
        index = tab.get("index", 1) - 1
        entries = tab.get("entries", [])
        current = entries[index].get("url") if 0 <= index < len(entries) else None
        if current != expected_tab["entries"][0]["url"] or any(tab.get(k) != expected_tab.get(k) for k in ("userContextId", "zenWorkspace", "pinned", "zenEssential")):
            mismatched.append(key)
    missing_spaces = sorted(set(manifest["space_ids"]) - {s["uuid"] for s in z["spaces"]})
    return {"ok": not (missing or mismatched or missing_spaces), "missing_tabs": missing,
            "changed_tabs": mismatched, "missing_spaces": missing_spaces,
            "note": "Disk snapshot only; inspect the UI and verify again after a clean shutdown. Redirected/navigated tabs require manual review."}


def rollback(work):
    require_closed()
    work = Path(work).expanduser().resolve()
    manifest, profile = checked_manifest(work)
    transaction = load_json(work / "transaction.json")
    if transaction.get("state") not in ("applying", "applied"):
        raise MigrationError("No applied/incomplete transaction to roll back")
    backup = work / "backup-profile"
    for name in NATIVE_FILES:
        if digest(backup / name) != manifest["before"][name]:
            raise MigrationError("Backup verification failed")
    # Swap whole directories: retain the entire later profile for recovery.
    recovery = profile.with_name(profile.name + ".before-rollback-" + uuid.uuid4().hex[:8])
    restore = profile.with_name(profile.name + ".restoring-" + uuid.uuid4().hex[:8])
    shutil.copytree(backup, restore, symlinks=True)
    require_closed()
    profile.rename(recovery)
    try:
        restore.rename(profile)
    except BaseException:
        recovery.rename(profile)
        raise
    save_json(work / "transaction.json", {"state": "rolled-back", "later_profile": str(recovery)})
    return {"state": "rolled-back", "later_profile_preserved_at": str(recovery)}


def discover():
    home = Path.home()
    arc = home / "Library/Application Support/Arc"
    zen = home / "Library/Application Support/zen"
    profiles = []
    config = configparser.ConfigParser()
    config.read(zen / "profiles.ini")
    for section in config.sections():
        if section.startswith("Profile") and config.has_option(section, "Path"):
            path = Path(config[section]["Path"])
            if config[section].get("IsRelative", "1") == "1":
                path = zen / path
            profiles.append({"name": config[section].get("Name"), "path": str(path), "exists": path.is_dir()})
    return {"arc": str(arc), "arc_found": (arc / "StorableSidebar.json").is_file(), "zen_profiles": profiles}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("discover", help="Find macOS Arc data and registered Zen profiles")
    inspect = commands.add_parser("inspect", help="Read Arc sidebar counts without changing profiles")
    inspect.add_argument("--arc", required=True)
    prepare_parser = commands.add_parser("prepare", help="Export HTML/inventory; optionally stage native files")
    prepare_parser.add_argument("--arc", required=True)
    prepare_parser.add_argument("--out", required=True)
    prepare_parser.add_argument("--zen-profile")
    prepare_parser.add_argument("--url-map", help="JSON object: old extension URL → verified target URL")
    for name in ("apply", "verify", "rollback"):
        command = commands.add_parser(name)
        command.add_argument("--work", required=True)
        if name == "apply":
            command.add_argument("--accept-skipped", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "discover":
            result = discover()
        elif args.command == "inspect":
            inv = arc_inventory(args.arc)
            result = {"counts": inv["counts"], "profiles": sorted({s["profile"] for s in inv["spaces"]}), "issues": inv["issues"]}
        elif args.command == "prepare":
            prepare(args)
            return
        elif args.command == "apply":
            result = apply(args.work, args.accept_skipped)
        elif args.command == "verify":
            result = verify(args.work)
        else:
            result = rollback(args.work)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.command == "verify" and not result["ok"]:
            sys.exit(1)
    except (MigrationError, OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        parser.exit(2, "Migration stopped: " + str(error) + "\n")


if __name__ == "__main__":
    main()
