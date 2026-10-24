// Copyright (c) 2026 AntonyLL. MIT License.
import Cocoa
import Carbon
import WebKit

private func isWebURL(_ url: URL) -> Bool {
    ["http", "https"].contains(url.scheme?.lowercased() ?? "") && !(url.host ?? "").isEmpty
}

private func shouldOpenDirectly(_ url: URL) -> Bool {
    let configured = UserDefaults.standard.stringArray(forKey: "directURLs") ?? []
    return configured.compactMap(URL.init(string:)).contains { candidate in
        isWebURL(candidate)
            && candidate.host?.lowercased() == url.host?.lowercased()
            && candidate.port == url.port
            && candidate.path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
                == url.path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
    }
}

final class PreviewPanel: NSPanel {
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { true }
}

final class PreviewWindowController: NSWindowController, NSWindowDelegate, WKNavigationDelegate, WKUIDelegate {
    let webView: WKWebView
    private let address = NSTextField(labelWithString: "")
    private let message = NSTextField(wrappingLabelWithString: "")
    private let back = NSButton()
    private let forward = NSButton()
    private let reload = NSButton()
    private let openButton = NSButton()
    private let spinner = NSProgressIndicator()
    private var observations: [NSKeyValueObservation] = []
    private var keyMonitor: Any?
    private var initialURL: URL
    private var transferring = false
    var onOpenInZen: ((URL, @escaping (Error?) -> Void) -> Void)?
    var onClose: (() -> Void)?

    init(url: URL) {
        initialURL = url
        let configuration = WKWebViewConfiguration()
        // This app's persistent WebKit store never reads Zen cookies or extension data.
        configuration.websiteDataStore = .default()
        webView = WKWebView(frame: .zero, configuration: configuration)
        let panel = PreviewPanel(contentRect: NSRect(x: 0, y: 0, width: 900, height: 760),
                                 styleMask: [.titled, .closable, .resizable],
                                 backing: .buffered, defer: false)
        panel.title = "Link Preview"
        panel.isReleasedWhenClosed = false
        panel.isRestorable = false
        panel.isFloatingPanel = false
        panel.hidesOnDeactivate = false
        panel.becomesKeyOnlyIfNeeded = false
        panel.level = .normal
        panel.collectionBehavior = [.moveToActiveSpace, .fullScreenAuxiliary]
        panel.animationBehavior = .none
        panel.minSize = NSSize(width: 560, height: 420)
        panel.titlebarAppearsTransparent = true
        panel.backgroundColor = NSColor(name: "PreviewChrome") { appearance in
            appearance.bestMatch(from: [.aqua, .darkAqua]) == .darkAqua
                ? NSColor(calibratedRed: 0.23, green: 0.16, blue: 0.12, alpha: 1)
                : NSColor(calibratedRed: 1, green: 0.93, blue: 0.87, alpha: 1)
        }
        super.init(window: panel)
        panel.delegate = self
        buildContent()
        observeWebView()
        panel.center()
        if let screen = panel.screen ?? NSScreen.main {
            let visible = screen.visibleFrame
            let size = NSSize(width: min(900, visible.width - 48), height: min(790, visible.height - 48))
            panel.setFrame(NSRect(x: visible.midX - size.width / 2, y: visible.midY - size.height / 2,
                                  width: size.width, height: size.height), display: false)
        }
        keyMonitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] event in
            guard let self, event.window === self.window else { return event }
            let modifiers = event.modifierFlags.intersection(.deviceIndependentFlagsMask)
            if event.keyCode == 53 && modifiers.isEmpty { self.close(); return nil }
            if modifiers == .command {
                switch event.charactersIgnoringModifiers?.lowercased() {
                case "o": self.openInZen(); return nil
                case "w": self.close(); return nil
                case "r": self.webView.reload(); return nil
                default: break
                }
            }
            return event
        }
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) is not supported") }
    deinit { if let keyMonitor { NSEvent.removeMonitor(keyMonitor) } }

    private func buildContent() {
        guard let panel = window else { return }
        let root = NSView()
        panel.contentView = root
        let header = NSStackView()
        header.orientation = .horizontal
        header.spacing = 10
        header.edgeInsets = NSEdgeInsets(top: 9, left: 12, bottom: 9, right: 12)
        for (button, symbol, title, action) in [
            (back, "chevron.left", "Back", #selector(goBack)),
            (forward, "chevron.right", "Forward", #selector(goForward)),
            (reload, "arrow.clockwise", "Reload", #selector(reloadPage))
        ] {
            button.image = NSImage(systemSymbolName: symbol, accessibilityDescription: title)
            button.setAccessibilityLabel(title)
            button.toolTip = title
            button.bezelStyle = .texturedRounded
            button.target = self
            button.action = action
            button.widthAnchor.constraint(equalToConstant: 30).isActive = true
            header.addArrangedSubview(button)
        }
        address.font = .systemFont(ofSize: 12)
        address.textColor = .secondaryLabelColor
        address.isSelectable = true
        address.lineBreakMode = .byTruncatingMiddle
        address.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        address.setContentHuggingPriority(.defaultLow, for: .horizontal)
        address.setAccessibilityLabel("Current page address")
        header.addArrangedSubview(address)
        spinner.style = .spinning
        spinner.controlSize = .small
        spinner.isDisplayedWhenStopped = false
        spinner.widthAnchor.constraint(equalToConstant: 16).isActive = true
        header.addArrangedSubview(spinner)
        openButton.title = "Open in Zen"
        openButton.image = NSImage(systemSymbolName: "arrow.up.forward.app", accessibilityDescription: nil)
        openButton.imagePosition = .imageLeft
        openButton.bezelStyle = .rounded
        openButton.target = self
        openButton.action = #selector(openInZen)
        openButton.toolTip = "Open the current page in Zen (⌘O)"
        openButton.setContentCompressionResistancePriority(.required, for: .horizontal)
        header.addArrangedSubview(openButton)
        message.font = .systemFont(ofSize: 12)
        message.textColor = .secondaryLabelColor
        message.isHidden = true
        let column = NSStackView(views: [header, message, webView])
        column.orientation = .vertical
        column.alignment = .width
        column.spacing = 0
        column.translatesAutoresizingMaskIntoConstraints = false
        root.addSubview(column)
        NSLayoutConstraint.activate([
            column.leadingAnchor.constraint(equalTo: root.leadingAnchor),
            column.trailingAnchor.constraint(equalTo: root.trailingAnchor),
            column.topAnchor.constraint(equalTo: root.topAnchor),
            column.bottomAnchor.constraint(equalTo: root.bottomAnchor),
            header.heightAnchor.constraint(equalToConstant: 48),
            header.widthAnchor.constraint(equalTo: root.widthAnchor),
        ])
        webView.navigationDelegate = self
        webView.uiDelegate = self
        webView.allowsBackForwardNavigationGestures = true
        webView.underPageBackgroundColor = .windowBackgroundColor
    }

    private func observeWebView() {
        observations = [
            webView.observe(\.url, options: [.new]) { [weak self] _, _ in self?.refreshChrome() },
            webView.observe(\.title, options: [.new]) { [weak self] _, _ in self?.refreshChrome() },
            webView.observe(\.isLoading, options: [.new]) { [weak self] _, _ in self?.refreshChrome() },
            webView.observe(\.canGoBack, options: [.new]) { [weak self] _, _ in self?.refreshChrome() },
            webView.observe(\.canGoForward, options: [.new]) { [weak self] _, _ in self?.refreshChrome() },
        ]
    }

    private func refreshChrome() {
        let current = webView.url.flatMap { isWebURL($0) ? $0 : nil } ?? initialURL
        address.stringValue = current.absoluteString
        address.toolTip = current.absoluteString
        window?.title = webView.title.flatMap { $0.isEmpty ? nil : $0 } ?? (current.host ?? "Link Preview")
        back.isEnabled = webView.canGoBack && !transferring
        forward.isEnabled = webView.canGoForward && !transferring
        openButton.isEnabled = !transferring
        if webView.isLoading { spinner.startAnimation(nil) } else { spinner.stopAnimation(nil) }
    }

    func show(url: URL) {
        initialURL = url
        transferring = false
        message.isHidden = true
        address.stringValue = url.absoluteString
        window?.title = url.host ?? "Link Preview"
        webView.load(URLRequest(url: url))
        // This is the only window created for a web-link event. Zen is not launched here.
        window?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        window?.makeFirstResponder(webView)
    }

    func showMessage(_ text: String) {
        message.stringValue = "  " + text + "  "
        message.isHidden = false
    }

    @objc private func goBack() { webView.goBack() }
    @objc private func goForward() { webView.goForward() }
    @objc private func reloadPage() { webView.reload() }

    @objc func openInZen() {
        guard !transferring else { return }
        let url = webView.url.flatMap { isWebURL($0) ? $0 : nil } ?? initialURL
        transferring = true
        refreshChrome()
        onOpenInZen?(url) { [weak self] error in
            guard let self else { return }
            self.transferring = false
            if let error {
                self.showMessage("Cannot open Zen: \(error.localizedDescription)")
                self.refreshChrome()
            } else { self.close() }
        }
    }

    func windowWillClose(_ notification: Notification) {
        webView.stopLoading()
        onClose?()
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = navigationAction.request.url else { decisionHandler(.cancel); return }
        if !isWebURL(url) && url.absoluteString != "about:blank" {
            showMessage("This link requires an external app. Continue in Zen.")
            decisionHandler(.cancel)
            return
        }
        if navigationAction.shouldPerformDownload {
            showMessage("Choose Open in Zen to download this file.")
            decisionHandler(.cancel)
            return
        }
        decisionHandler(.allow)
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationResponse: WKNavigationResponse,
                 decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
        guard navigationResponse.canShowMIMEType else {
            showMessage("Open this content in Zen.")
            decisionHandler(.cancel)
            return
        }
        decisionHandler(.allow)
    }

    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for navigationAction: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let url = navigationAction.request.url, isWebURL(url) { webView.load(navigationAction.request) }
        return nil
    }

    func webView(_ webView: WKWebView, didStartProvisionalNavigation navigation: WKNavigation!) {
        message.isHidden = true
    }
    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        reportNavigationError(error)
    }
    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        reportNavigationError(error)
    }
    private func reportNavigationError(_ error: Error) {
        guard (error as NSError).code != NSURLErrorCancelled else { return }
        showMessage("Page could not load: \(error.localizedDescription) Continue in Zen.")
    }
}

final class PreviewDelegate: NSObject, NSApplicationDelegate {
    private var preview: PreviewWindowController?
    private var zenApplication: URL {
        NSWorkspace.shared.urlForApplication(withBundleIdentifier: "app.zen-browser.zen")
            ?? URL(fileURLWithPath: "/Applications/Zen.app")
    }

    func applicationWillFinishLaunching(_ notification: Notification) {
        NSAppleEventManager.shared().setEventHandler(self,
            andSelector: #selector(receiveURL(_:withReplyEvent:)),
            forEventClass: AEEventClass(kInternetEventClass), andEventID: AEEventID(kAEGetURL))
        installMenu()
    }
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows: Bool) -> Bool {
        // URL launches can include a reopen event. Never show a launcher or spare window.
        false
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }

    @objc private func receiveURL(_ event: NSAppleEventDescriptor, withReplyEvent reply: NSAppleEventDescriptor) {
        guard let text = event.paramDescriptor(forKeyword: AEKeyword(keyDirectObject))?.stringValue,
              let url = URL(string: text) else { return }
        route(url)
    }
    func application(_ application: NSApplication, open urls: [URL]) {
        for url in urls { route(url) }
    }

    private func route(_ url: URL) {
        let localHTML = url.isFileURL && ["html", "htm", "xhtml"].contains(url.pathExtension.lowercased())
        guard isWebURL(url) || localHTML else { return }
        if shouldOpenDirectly(url) || localHTML {
            openInZen(url) { [weak self] error in
                if let error { self?.showError(error) } else { self?.preview?.close() }
            }
            return
        }
        if preview == nil {
            let controller = PreviewWindowController(url: url)
            controller.onOpenInZen = { [weak self] url, completion in self?.openInZen(url, completion: completion) }
            controller.onClose = { [weak self] in self?.preview = nil }
            preview = controller
        }
        preview?.show(url: url)
    }

    private func openInZen(_ url: URL, completion: @escaping (Error?) -> Void) {
        let configuration = NSWorkspace.OpenConfiguration()
        configuration.activates = true
        configuration.addsToRecentItems = false
        // An explicit destination avoids re-entering this default URL handler.
        NSWorkspace.shared.open([url], withApplicationAt: zenApplication, configuration: configuration) { application, error in
            DispatchQueue.main.async {
                if error == nil { application?.activate(options: []) }
                completion(error)
            }
        }
    }

    private func showError(_ error: Error) {
        if let preview { preview.showMessage("Cannot open Zen: \(error.localizedDescription)"); return }
        let alert = NSAlert()
        alert.messageText = "Cannot open Zen"
        alert.informativeText = error.localizedDescription
        alert.runModal()
    }
    @objc private func openCurrentInZen() { preview?.openInZen() }
    @objc private func closePreview() { preview?.close() }

    private func installMenu() {
        let menu = NSMenu()
        let appItem = NSMenuItem()
        let appMenu = NSMenu()
        appMenu.addItem(withTitle: "Quit Link Preview", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appItem.submenu = appMenu
        menu.addItem(appItem)
        let fileItem = NSMenuItem(title: "File", action: nil, keyEquivalent: "")
        let fileMenu = NSMenu(title: "File")
        let open = fileMenu.addItem(withTitle: "Open in Zen", action: #selector(openCurrentInZen), keyEquivalent: "o")
        open.target = self
        let close = fileMenu.addItem(withTitle: "Close Preview", action: #selector(closePreview), keyEquivalent: "w")
        close.target = self
        fileItem.submenu = fileMenu
        menu.addItem(fileItem)
        let editItem = NSMenuItem(title: "Edit", action: nil, keyEquivalent: "")
        let editMenu = NSMenu(title: "Edit")
        for (title, action, key) in [("Undo", "undo:", "z"), ("Cut", "cut:", "x"),
                                     ("Copy", "copy:", "c"), ("Paste", "paste:", "v"), ("Select All", "selectAll:", "a")] {
            editMenu.addItem(withTitle: title, action: Selector(action), keyEquivalent: key)
        }
        editItem.submenu = editMenu
        menu.addItem(editItem)
        NSApp.mainMenu = menu
    }
}

let application = NSApplication.shared
let delegate = PreviewDelegate()
application.setActivationPolicy(.accessory)
application.delegate = delegate
application.run()
