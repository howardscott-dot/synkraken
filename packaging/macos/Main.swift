import AppKit
import WebKit

final class AppDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKUIDelegate {
    var window: NSWindow!
    var web: WKWebView!
    var engine: Process?
    var localURL: URL?
    var buffer = Data()
    func applicationDidFinishLaunching(_ notification: Notification) {
        let menu = NSMenu()
        let item = NSMenuItem()
        menu.addItem(item)
        let appMenu = NSMenu()
        appMenu.addItem(withTitle: "Quit SynKraken", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        item.submenu = appMenu
        let editItem = NSMenuItem()
        let edit = NSMenu(title: "Edit")
        for (title, selector, key) in [("Copy", "copy:", "c"), ("Paste", "paste:", "v"), ("Cut", "cut:", "x"), ("Select All", "selectAll:", "a")] {
            edit.addItem(withTitle: title, action: Selector(selector), keyEquivalent: key)
        }
        editItem.submenu = edit
        menu.addItem(editItem)
        NSApp.mainMenu = menu
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1180, height: 800), styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.title = "SynKraken"
        window.minSize = NSSize(width: 640, height: 500)
        web = WKWebView(frame: .zero)
        web.navigationDelegate = self
        web.uiDelegate = self
        window.contentView = web
        web.loadHTMLString("<body style='background:#101415;color:#e6f7f3;font:20px -apple-system;text-align:center;padding-top:25vh'><h1>SynKraken</h1><p>A conversation is all it takes to begin.</p><p style='font-size:14px'>Opening your workspace…</p></body>", baseURL: nil)
        window.center()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        let process = Process()
        process.executableURL = Bundle.main.resourceURL!.appendingPathComponent("engine/synkraken-engine")
        var environment = ProcessInfo.processInfo.environment
        environment["PLAYWRIGHT_BROWSERS_PATH"] = Bundle.main.resourceURL!.appendingPathComponent("browsers").path
        process.environment = environment
        let output = Pipe()
        process.standardOutput = output
        let logDirectory = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("SynKraken")
        try? FileManager.default.createDirectory(at: logDirectory, withIntermediateDirectories: true)
        let log = logDirectory.appendingPathComponent("desktop.log")
        if !FileManager.default.fileExists(atPath: log.path) { FileManager.default.createFile(atPath: log.path, contents: nil) }
        if let handle = try? FileHandle(forWritingTo: log) { handle.seekToEndOfFile(); process.standardError = handle }
        output.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            if data.isEmpty { handle.readabilityHandler = nil; return }
            DispatchQueue.main.async {
                guard let self = self, self.localURL == nil else { return }
                self.buffer.append(data)
                if let line = String(data: self.buffer, encoding: .utf8)?.components(separatedBy: "\n").first,
                   self.buffer.contains(10), let url = URL(string: line), url.host == "127.0.0.1" {
                    self.localURL = url
                    self.web.load(URLRequest(url: url))
                }
            }
        }
        process.terminationHandler = { [weak self] process in
            if process.terminationStatus != 0 { DispatchQueue.main.async { self?.showError() } }
        }
        engine = process
        do { try process.run() } catch { showError() }
    }
    func showError() {
        let alert = NSAlert()
        alert.messageText = "The workspace could not open"
        alert.informativeText = "Check the desktop.log file in Library/Application Support/SynKraken. Your saved conversations have been kept."
        alert.runModal()
    }
    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = action.request.url else { decisionHandler(.cancel); return }
        if url.scheme == "about" || (url.host == "127.0.0.1" && url.port == localURL?.port) {
            decisionHandler(.allow)
        } else {
            if ["https", "http"].contains(url.scheme ?? "") { NSWorkspace.shared.open(url) }
            decisionHandler(.cancel)
        }
    }
    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration, for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let url = action.request.url, ["https", "http"].contains(url.scheme ?? "") { NSWorkspace.shared.open(url) }
        return nil
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
    func applicationWillTerminate(_ notification: Notification) { engine?.terminate() }
}
let delegate = AppDelegate()
let app = NSApplication.shared
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
