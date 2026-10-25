import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("migration", ROOT / "skills/arc-to-zen/scripts/migrate.py")
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def arc_fixture(root, nested=False):
    default = {"default": {}}
    other = {"custom": {"_0": {"directoryBasename": "Profile 1"}}}
    items = {}

    def item(key, url=None, children=None, title=None):
        items[key] = {"id": key, "title": title, "childrenIds": children or [],
                      "data": {"tab": {"savedURL": url, "savedTitle": key}} if url else {"itemContainer": {}}}

    item("favorite", "https://example.com/favorite")
    item("favorites", children=["favorite"])
    item("pin", "https://example.com/a?x=1&y=2", title='A <quoted> "title"')
    item("open", "https://example.org/open")
    item("other", "https://example.net/work")
    item("p1", children=["folder"] if nested else ["pin"])
    item("u1", children=["open"])
    item("p2")
    item("u2", children=["other"])
    item("p3")
    item("u3")
    if nested:
        item("folder", children=["pin"], title="Folder <&>")
    spaces = {
        "s1": {"title": "Personal", "profile": default, "containerIDs": ["pinned", "p1", "unpinned", "u1"]},
        "s2": {"title": "Work", "profile": other, "containerIDs": ["pinned", "p2", "unpinned", "u2"]},
        "s3": {"title": "Research", "profile": default, "containerIDs": ["pinned", "p3", "unpinned", "u3"]},
    }
    source = {"items": [x for pair in items.items() for x in pair],
              "spaces": [x for pair in spaces.items() for x in pair],
              "topAppsContainerIDs": [default, "favorites"]}
    root.mkdir()
    m.save_json(root / "StorableSidebar.json", {"sidebar": {"containers": [{"global": {}}, source]}})
    (root / "Default").mkdir()
    m.save_json(root / "Default/Bookmarks", {"roots": {"bookmark_bar": {"name": "Bookmarks", "children": [
        {"type": "folder", "name": "Nested", "children": [
            {"type": "url", "name": "Duplicate 1", "url": "https://example.com/same"},
            {"type": "url", "name": "Duplicate 2", "url": "https://example.com/same"},
            {"type": "url", "name": "Bookmarklet", "url": "javascript:alert(1)"}]}]}}})
    return source


def zen_fixture(root):
    root.mkdir()
    old_space = {"uuid": "existing-space", "name": "Existing", "containerTabId": 0, "position": 1000}
    old_tabs = [{"entries": [{"url": "https://example.com/existing-pin", "title": "Existing pin"}], "index": 1,
                 "zenSyncId": "existing-pin", "zenWorkspace": "existing-space", "pinned": True, "userContextId": 0},
                {"entries": [{"url": "https://example.com/existing", "title": "Existing"}], "index": 1,
                 "zenSyncId": "existing-tab", "zenWorkspace": "existing-space", "pinned": False, "userContextId": 0}]
    sidebar = {"tabs": old_tabs, "spaces": [old_space], "folders": [], "groups": [], "splitViewData": []}
    (root / "zen-sessions.jsonlz4").write_bytes(m.encode_mozlz4(sidebar))
    session = {"windows": [{"tabs": old_tabs, "selected": 2, "spaces": [old_space],
                             "_closedTabs": [{"state": "preserve-me"}]}], "_closedWindows": [{"test": 1}]}
    (root / "sessionstore.jsonlz4").write_bytes(m.encode_mozlz4(session))
    m.save_json(root / "containers.json", {"identities": [{"userContextId": 4, "public": True, "name": "Existing"}], "lastUserContextId": 4})
    (root / "prefs.js").write_text('user_pref("existing.setting", "keep");\n')
    (root / "extra-state.txt").write_text("original browser-managed state")


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.arc = self.root / "arc"
        self.zen = self.root / "zen"
        arc_fixture(self.arc)
        zen_fixture(self.zen)
        self.closed = mock.patch.object(m, "require_closed")
        self.closed.start()

    def tearDown(self):
        self.closed.stop()
        self.temp.cleanup()

    def plan(self):
        work = self.root / "work"
        work.mkdir()
        (work / "staged").mkdir()
        payload, manifest = m.native_plan(m.arc_inventory(self.arc), self.zen)
        for name, data in payload.items():
            (work / "staged" / name).write_bytes(data)
        m.save_json(work / "manifest.json", manifest)
        return work, manifest

    def test_discovery_counts_and_profile_sharing(self):
        inventory = m.arc_inventory(self.arc)
        self.assertEqual(inventory["counts"], {"spaces": 3, "tabs": 4, "favorites": 1, "pinned": 1, "folders": 0})
        _, manifest = m.native_plan(inventory, self.zen)
        self.assertEqual(len(manifest["contexts"]), 2)
        self.assertGreater(min(manifest["contexts"].values()), 4)

    def test_containers_skip_firefox_internal_identity_ids(self):
        containers = m.load_json(self.zen / "containers.json")
        containers["identities"] += [
            {"userContextId": 5, "public": False, "name": "userContextIdInternal.thumbnail"},
            {"userContextId": 4294967295, "public": False, "name": "userContextIdInternal.webextStorageLocal"}]
        containers["lastUserContextId"] = 5
        m.save_json(self.zen / "containers.json", containers)
        payload, manifest = m.native_plan(m.arc_inventory(self.arc), self.zen)
        self.assertEqual(sorted(manifest["contexts"].values()), [6, 7])
        self.assertEqual(json.loads(payload["containers.json"])["lastUserContextId"], 7)

    def test_every_new_entry_has_a_triggering_principal(self):
        payload, manifest = m.native_plan(m.arc_inventory(self.arc), self.zen)
        for name in ("zen-sessions.jsonlz4", "sessionstore.jsonlz4"):
            data = m.decode_mozlz4(payload[name])
            tabs = data["tabs"] if "tabs" in data else data["windows"][0]["tabs"]
            new = [t for t in tabs if t.get("zenSyncId") in manifest["tab_ids"]]
            self.assertEqual(len(new), len(manifest["tab_ids"]))
            for tab in new:
                self.assertEqual([e.get("triggeringPrincipal_base64") for e in tab["entries"]], [m.SYSTEM_PRINCIPAL])

    def test_empty_favorites_profile_without_space_is_harmless(self):
        value = m.load_json(self.arc / "StorableSidebar.json")
        source = value["sidebar"]["containers"][1]
        source["items"].extend(["unused", {"data": {"itemContainer": {}}, "childrenIds": []}])
        source["topAppsContainerIDs"].extend([{"custom": {"_0": {"directoryBasename": "Profile 9"}}}, "unused"])
        m.save_json(self.arc / "StorableSidebar.json", value)
        inventory = m.arc_inventory(self.arc)
        self.assertEqual(inventory["issues"], [])
        m.native_plan(inventory, self.zen)

    def test_html_escapes_preserves_duplicates_and_reports_bookmarklets(self):
        document, report = m.bookmark_document(self.arc, m.arc_inventory(self.arc))
        self.assertEqual(document.count('HREF="https://example.com/same"'), 2)
        self.assertIn('A &lt;quoted&gt; &quot;title&quot;', document)
        self.assertIn('x=1&amp;y=2', document)
        self.assertNotIn('HREF="javascript:', document)
        self.assertEqual(len(report["omitted"]), 1)
        self.assertEqual(report["exported_links"], 6)

    def test_native_merge_preserves_existing_state_and_selection(self):
        inventory = m.arc_inventory(self.arc)
        before = {p.name: p.read_bytes() for p in self.zen.iterdir()}
        payload, manifest = m.native_plan(inventory, self.zen)
        session = m.decode_mozlz4(payload["sessionstore.jsonlz4"])
        window = session["windows"][0]
        self.assertEqual(window["tabs"][window["selected"] - 1]["zenSyncId"], "existing-tab")
        self.assertEqual(window["_closedTabs"], [{"state": "preserve-me"}])
        self.assertEqual(session["_closedWindows"], [{"test": 1}])
        self.assertEqual(len(window["tabs"]), 6)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.zen.iterdir()})
        self.assertEqual(manifest["spaces_added"], 3)
        self.assertIn(b'existing.setting', payload["prefs.js"])

    def test_apply_verify_and_full_rollback(self):
        before = {p.name: p.read_bytes() for p in self.zen.iterdir()}
        work, _ = self.plan()
        self.assertEqual(m.apply(work)["state"], "applied")
        self.assertTrue(m.verify(work)["ok"])
        (self.zen / "extra-state.txt").write_text("later extension state")
        recovered = m.rollback(work)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.zen.iterdir()})
        self.assertEqual((Path(recovered["later_profile_preserved_at"]) / "extra-state.txt").read_text(), "later extension state")

    def test_stale_profile_and_tampered_stage_are_rejected(self):
        work, _ = self.plan()
        original = (self.zen / "prefs.js").read_bytes()
        (self.zen / "prefs.js").write_bytes(original + b"// change\n")
        with self.assertRaisesRegex(m.MigrationError, "changed since"):
            m.apply(work)
        (self.zen / "prefs.js").write_bytes(original)
        (work / "staged/prefs.js").write_text("tampered")
        with self.assertRaisesRegex(m.MigrationError, "Staged data changed"):
            m.apply(work)
        self.assertFalse((work / "backup-profile").exists())

    def test_write_failure_restores_original_files(self):
        work, _ = self.plan()
        before = {n: (self.zen / n).read_bytes() for n in m.NATIVE_FILES}
        actual_write = m.write_atomic
        calls = 0

        def fail_once(path, data):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("simulated disk failure")
            return actual_write(path, data)

        with mock.patch.object(m, "write_atomic", side_effect=fail_once):
            with self.assertRaisesRegex(OSError, "disk failure"):
                m.apply(work)
        self.assertEqual(before, {n: (self.zen / n).read_bytes() for n in m.NATIVE_FILES})

    def test_repeat_import_is_refused(self):
        work, _ = self.plan()
        m.apply(work)
        with self.assertRaisesRegex(m.MigrationError, "already exist"):
            m.native_plan(m.arc_inventory(self.arc), self.zen)
        with self.assertRaisesRegex(m.MigrationError, "transaction already"):
            m.apply(work)

    def test_changed_container_fails_verification(self):
        work, manifest = self.plan()
        m.apply(work)
        data = m.read_session(self.zen / "zen-sessions.jsonlz4")
        next(t for t in data["tabs"] if t["zenSyncId"] == manifest["tab_ids"][0])["userContextId"] = 0
        (self.zen / "zen-sessions.jsonlz4").write_bytes(m.encode_mozlz4(data))
        self.assertFalse(m.verify(work)["ok"])

    def test_folders_export_but_block_native_conversion(self):
        nested = self.root / "nested"
        arc_fixture(nested, nested=True)
        inventory = m.arc_inventory(nested)
        document, _ = m.bookmark_document(nested, inventory)
        self.assertIn('Folder &lt;&amp;&gt;', document)
        with self.assertRaisesRegex(m.MigrationError, "flat Arc sidebars"):
            m.native_plan(inventory, self.zen)

    def test_sidebar_same_named_folders_remain_distinct_and_ordered(self):
        nested = self.root / "nested"
        arc_fixture(nested, nested=True)
        value = m.load_json(nested / "StorableSidebar.json")
        source = value["sidebar"]["containers"][1]
        items = m.pairs(source["items"], "items")
        items["p1"]["childrenIds"] = ["folder", "middle", "folder2"]
        items["folder2"] = {"title": "Folder <&>", "childrenIds": [], "data": {"itemContainer": {}}}
        items["middle"] = {"title": "Between folders", "childrenIds": [], "data": {"tab": {"savedURL": "https://example.com/middle"}}}
        source["items"] = items
        m.save_json(nested / "StorableSidebar.json", value)
        document, _ = m.bookmark_document(nested, m.arc_inventory(nested))
        self.assertEqual(document.count('<H3>Folder &lt;&amp;&gt;</H3>'), 2)
        self.assertLess(document.index('<H3>Folder &lt;&amp;&gt;</H3>'), document.index('Between folders'))
        self.assertLess(document.index('Between folders'), document.rindex('<H3>Folder &lt;&amp;&gt;</H3>'))

    def test_unknown_extension_page_is_reported(self):
        inventory = m.arc_inventory(self.arc)
        inventory["tabs"][0]["url"] = "chrome-extension://example/page.html"
        _, manifest = m.native_plan(inventory, self.zen)
        self.assertEqual(len(manifest["skipped"]), 1)
        _, mapped = m.native_plan(inventory, self.zen, {"chrome-extension://example/page.html": "moz-extension://target/page.html"})
        self.assertEqual(mapped["skipped"], [])

    def test_malformed_arc_map_and_cycle_are_rejected(self):
        with self.assertRaises(m.MigrationError):
            m.pairs(["key", 1, "orphan"], "test")
        with self.assertRaises(m.MigrationError):
            m.pairs(["key", 1, "key", 2], "test")
        value = m.load_json(self.arc / "StorableSidebar.json")
        items = value["sidebar"]["containers"][1]["items"]
        items[items.index("p1") + 1]["childrenIds"] = ["p1"]
        m.save_json(self.arc / "StorableSidebar.json", value)
        with self.assertRaises(m.MigrationError):
            m.arc_inventory(self.arc)

    def test_multiple_zen_windows_are_rejected(self):
        data = m.read_session(self.zen / "sessionstore.jsonlz4")
        data["windows"].append(data["windows"][0].copy())
        (self.zen / "sessionstore.jsonlz4").write_bytes(m.encode_mozlz4(data))
        with self.assertRaisesRegex(m.MigrationError, "one non-private"):
            m.native_plan(m.arc_inventory(self.arc), self.zen)


class CodecAndInstallerTests(unittest.TestCase):
    def test_unicode_long_literal_roundtrip(self):
        for value in ({}, {"title": "测试 🎨", "data": "x" * 5000}):
            self.assertEqual(m.decode_mozlz4(m.encode_mozlz4(value)), value)

    def test_lz4_match_block(self):
        # Token 0x95 = 9 literals + 9-byte match at distance 3, then 2 literals.
        raw = b'{"a":"abcabcabcabc"}'
        block = bytes([0x95]) + b'{"a":"abc' + bytes([3, 0, 0x20]) + b'"}'
        self.assertEqual(m.decode_mozlz4(m.MAGIC + struct.pack("<I", len(raw)) + block), {"a": "abcabcabcabc"})

    def test_corrupt_and_oversize_lz4(self):
        for data in (b"invalid", m.MAGIC + struct.pack("<I", m.MAX_SIZE + 1) + b"\0",
                     m.MAGIC + struct.pack("<I", 4) + b"\0\0\0"):
            with self.assertRaises(m.MigrationError):
                m.decode_mozlz4(data)

    def test_installer_is_self_contained_and_refuses_overwrite(self):
        spec = importlib.util.spec_from_file_location("installer", ROOT / "install.py")
        installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(installer)
        with tempfile.TemporaryDirectory() as temp:
            path = installer.install(Path(temp) / "arc-to-zen")
            self.assertTrue((path / "SKILL.md").is_file())
            self.assertTrue((path / "assets/zen-link-preview/ZenLinkPreview.swift").is_file())
            with self.assertRaises(ValueError):
                installer.install(path)


if __name__ == "__main__":
    unittest.main()
