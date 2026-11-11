import AppKit
import WebKit

// Thin native shell. Credentials travel over the child's private pipe and an HttpOnly cookie.
final class AppDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKScriptMessageHandler {
    private var window: NSWindow!
    private var webView: WKWebView!
    private var status: NSTextField!
    private var launcher: Process?
    private var output = Data()
    private var origin: URL?
    private var terminating = false
    private let input = Pipe()
    private var authenticating = false
    private var diagnosticURL: URL?

    private func trace(_ message: String) {
        guard let url = diagnosticURL else { return }
        let data = Data("\(Date()): \(message)\n".utf8)
        if let file = try? FileHandle(forWritingTo: url) {
            defer { try? file.close() }
            _ = try? file.seekToEnd()
            try? file.write(contentsOf: data)
        } else { try? data.write(to: url) }
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        installMenu()
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .nonPersistent()
        configuration.userContentController.add(self, name: "selectFolder")
        configuration.userContentController.add(self, name: "reauthenticate")
        configuration.userContentController.add(self, name: "saveSelection")
        if let selection = UserDefaults.standard.dictionary(forKey: "LocalDeskSelection"),
           let data = try? JSONSerialization.data(withJSONObject: selection),
           let json = String(data: data, encoding: .utf8),
           let encoded = try? JSONSerialization.data(withJSONObject: [json]),
           let array = String(data: encoded, encoding: .utf8) {
            let script = "try { if (!localStorage.getItem('localdesk.selection.v1')) localStorage.setItem('localdesk.selection.v1', \(array)[0]); } catch {}"
            configuration.userContentController.addUserScript(WKUserScript(source: script, injectionTime: .atDocumentStart, forMainFrameOnly: true))
        }
        webView = WKWebView(frame: .zero, configuration: configuration)
        webView.navigationDelegate = self
        webView.setValue(false, forKey: "drawsBackground")
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1440, height: 920),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable],
                          backing: .buffered, defer: false)
        window.title = "LocalDesk"
        window.minSize = NSSize(width: 960, height: 680)
        window.backgroundColor = NSColor(calibratedRed: 0.05, green: 0.06, blue: 0.09, alpha: 1)
        window.contentView = webView
        status = NSTextField(labelWithString: "LocalDesk 시작 중…")
        status.textColor = .white
        status.font = .systemFont(ofSize: 18)
        status.translatesAutoresizingMaskIntoConstraints = false
        webView.addSubview(status)
        NSLayoutConstraint.activate([
            status.centerXAnchor.constraint(equalTo: webView.centerXAnchor),
            status.centerYAnchor.constraint(equalTo: webView.centerYAnchor)
        ])
        window.center()
        window.makeKeyAndOrderFront(nil)
        NSApplication.shared.activate(ignoringOtherApps: true)
        do { try startLauncher() } catch { showError(error.localizedDescription) }
    }

    private func installMenu() {
        let menu = NSMenu()
        let appItem = NSMenuItem()
        let appMenu = NSMenu()
        appMenu.addItem(withTitle: "LocalDesk 종료", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appItem.submenu = appMenu
        menu.addItem(appItem)
        let edit = NSMenuItem()
        let editMenu = NSMenu(title: "편집")
        for (title, selector, key) in [("실행 취소", "undo:", "z"), ("잘라내기", "cut:", "x"),
                                       ("복사", "copy:", "c"), ("붙여넣기", "paste:", "v"),
                                       ("모두 선택", "selectAll:", "a")] {
            editMenu.addItem(withTitle: title, action: Selector(selector), keyEquivalent: key)
        }
        edit.submenu = editMenu
        menu.addItem(edit)
        NSApplication.shared.mainMenu = menu
    }

    private func startLauncher() throws {
        guard let configURL = Bundle.main.url(forResource: "local-config", withExtension: "json"),
              let config = try JSONSerialization.jsonObject(with: Data(contentsOf: configURL)) as? [String: String],
              let root = config["projectRoot"], let node = config["nodePath"] else {
            throw NSError(domain: "LocalDesk", code: 1, userInfo: [NSLocalizedDescriptionKey: "앱 실행 설정이 없습니다."])
        }
        let process = Process()
        diagnosticURL = URL(fileURLWithPath: root).appendingPathComponent(".securecode/native-startup.log")
        trace("Starting local services")
        process.executableURL = URL(fileURLWithPath: node)
        process.arguments = ["--import", "tsx", "scripts/desktop/start.ts"]
        process.currentDirectoryURL = URL(fileURLWithPath: root)
        var environment = ProcessInfo.processInfo.environment
        environment["PATH"] = config["path"]
        process.environment = environment
        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardInput = input
        process.standardError = FileHandle.nullDevice
        pipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            if data.isEmpty { handle.readabilityHandler = nil; return }
            DispatchQueue.main.async { self?.consume(data) }
        }
        process.terminationHandler = { [weak self] child in
            DispatchQueue.main.async {
                guard let self = self else { return }
                if self.terminating { NSApplication.shared.reply(toApplicationShouldTerminate: true) }
                else if child.terminationStatus != 0 { self.showError("로컬 서비스를 시작하지 못했습니다. 앱을 다시 실행해 주세요.") }
            }
        }
        launcher = process
        try process.run()
        status.stringValue = "로컬 서비스를 준비하고 있습니다…"
    }

    private func consume(_ data: Data) {
        trace("Received launcher response")
        output.append(data)
        while let newline = output.firstIndex(of: 10) {
            let line = output.prefix(upTo: newline)
            output.removeSubrange(...newline)
            guard let message = try? JSONSerialization.jsonObject(with: line) as? [String: Any] else { continue }
            if let error = message["error"] as? String { showError(error); continue }
            if let address = message["url"] as? String, let code = message["code"] as? String,
               let url = URL(string: address) { authenticate(url: url, code: code) }
        }
    }

    private func authenticate(url: URL, code: String) {
        trace("Exchanging one-time bootstrap code")
        status.stringValue = "로컬 연결을 인증하고 있습니다…"
        origin = url
        var request = URLRequest(url: url.appendingPathComponent("api/v1/auth/bootstrap"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(url.absoluteString, forHTTPHeaderField: "Origin")
        request.httpBody = try? JSONSerialization.data(withJSONObject: ["code": code])
        let session = URLSession(configuration: .ephemeral)
        session.dataTask(with: request) { [weak self] _, response, error in
            self?.trace("Bootstrap response status \((response as? HTTPURLResponse)?.statusCode ?? 0)")
            defer { session.finishTasksAndInvalidate() }
            guard error == nil, let response = response as? HTTPURLResponse, response.statusCode == 200,
                  let headers = response.allHeaderFields as? [String: String] else {
                DispatchQueue.main.async { self?.showError("로컬 앱 인증에 실패했습니다. 앱을 다시 실행해 주세요.") }
                return
            }
            let cookies = HTTPCookie.cookies(withResponseHeaderFields: headers, for: url)
            DispatchQueue.main.async {
                guard let self = self else { return }
                guard !cookies.isEmpty else { self.showError("인증 쿠키를 받지 못했습니다."); return }
                let group = DispatchGroup()
                for cookie in cookies {
                    group.enter()
                    self.webView.configuration.websiteDataStore.httpCookieStore.setCookie(cookie) { group.leave() }
                }
                group.notify(queue: .main) {
                    self.trace("Cookie installed; loading built UI")
                    self.authenticating = false
                    self.status.isHidden = true
                    self.webView.load(URLRequest(url: url))
                }
            }
        }.resume()
    }

    func userContentController(_ controller: WKUserContentController, didReceive message: WKScriptMessage) {
        guard message.frameInfo.isMainFrame,
              message.frameInfo.securityOrigin.host == "127.0.0.1",
              message.frameInfo.securityOrigin.port == origin?.port else { return }
        if message.name == "reauthenticate" {
            if !authenticating {
                authenticating = true
                input.fileHandleForWriting.write(Data("{\"reauthenticate\":true}\n".utf8))
            }
            return
        }
        if message.name == "saveSelection" {
            guard let body = message.body as? [String: String],
                  let workspace = body["workspaceId"], workspace.range(of: "^ws_[A-Za-z0-9-]{8,128}$", options: .regularExpression) != nil else { return }
            var selection = ["workspaceId": workspace]
            if let session = body["sessionId"], session.range(of: "^ses_[A-Za-z0-9-]{8,128}$", options: .regularExpression) != nil {
                selection["sessionId"] = session
            }
            UserDefaults.standard.set(selection, forKey: "LocalDeskSelection")
            return
        }
        guard message.name == "selectFolder",
              let body = message.body as? [String: String], let requestID = body["requestId"] else { return }
        let panel = NSOpenPanel()
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.allowsMultipleSelection = false
        panel.beginSheetModal(for: window) { [weak self] result in
            let detail: [String: Any] = ["requestId": requestID, "path": result == .OK ? panel.url?.path as Any : NSNull()]
            guard let data = try? JSONSerialization.data(withJSONObject: detail),
                  let json = String(data: data, encoding: .utf8) else { return }
            self?.webView.evaluateJavaScript("window.dispatchEvent(new CustomEvent('localdesk:folder-selected',{detail:\(json)}));")
        }
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = navigationAction.request.url else { decisionHandler(.cancel); return }
        if url.scheme == origin?.scheme && url.host == origin?.host && url.port == origin?.port {
            decisionHandler(.allow)
        } else {
            if navigationAction.navigationType == .linkActivated && ["https", "http"].contains(url.scheme ?? "") {
                NSWorkspace.shared.open(url)
            }
            decisionHandler(.cancel)
        }
    }

    private func showError(_ message: String) {
        trace("Startup failed")
        status.stringValue = "LocalDesk를 시작할 수 없습니다."
        status.isHidden = false
        let alert = NSAlert()
        alert.messageText = "LocalDesk 실행 오류"
        alert.informativeText = message
        alert.beginSheetModal(for: window)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        guard let launcher = launcher, launcher.isRunning else { return .terminateNow }
        terminating = true
        launcher.terminate()
        return .terminateLater
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
