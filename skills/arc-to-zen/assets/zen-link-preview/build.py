#!/usr/bin/env python3
"""Build a local, ad-hoc-signed preview app. Does not install or change defaults."""
import argparse
from pathlib import Path
import plistlib
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / ".build")
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.exit(2, "Building the preview requires macOS and Xcode Command Line Tools.\n")
    root = Path(__file__).resolve().parent
    app = args.output.expanduser().resolve() / "Zen Link Preview.app"
    if app.exists():
        parser.exit(2, "Build destination exists; choose a new --output directory.\n")
    contents = app / "Contents"
    (contents / "MacOS").mkdir(parents=True)
    (contents / "Resources").mkdir()
    info = {
        "CFBundleIdentifier": "io.github.AntonyLL.ZenLinkPreview",
        "CFBundleName": "Zen Link Preview", "CFBundleDisplayName": "Zen Link Preview",
        "CFBundleExecutable": "ZenLinkPreview", "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": "1.0.0", "CFBundleVersion": "1",
        "LSMinimumSystemVersion": "13.0", "LSUIElement": True,
        "NSHighResolutionCapable": True, "NSPrincipalClass": "NSApplication",
        "CFBundleURLTypes": [{"CFBundleURLName": "Web links in Zen Preview",
            "CFBundleURLSchemes": ["http", "https"], "CFBundleTypeRole": "Viewer",
            "LSHandlerRank": "Alternate"}],
        "CFBundleDocumentTypes": [{"CFBundleTypeName": "HTML document in Zen",
            "CFBundleTypeRole": "Viewer", "LSHandlerRank": "Alternate",
            "LSItemContentTypes": ["public.html", "public.xhtml"]}],
    }
    (contents / "Info.plist").write_bytes(plistlib.dumps(info))
    subprocess.run(["xcrun", "swiftc", "-O", "-framework", "Cocoa", "-framework", "Carbon",
                    "-framework", "WebKit", str(root / "ZenLinkPreview.swift"),
                    "-o", str(contents / "MacOS/ZenLinkPreview")], check=True)
    subprocess.run(["codesign", "--force", "--sign", "-", str(app)], check=True)
    subprocess.run(["codesign", "--verify", "--strict", str(app)], check=True)
    print(app)


if __name__ == "__main__":
    main()
