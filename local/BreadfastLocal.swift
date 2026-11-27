import AppKit
import UserNotifications

final class Monitor: NSObject, NSApplicationDelegate, UNUserNotificationCenterDelegate {
    var item: NSStatusItem!
    var timer: Timer?
    var busySources = Set<String>()
    var queuedFull = Set<String>()
    var paused = false
    var lastErrors = [String:String]()
    let status = NSMenuItem(title: "Starting…", action: nil, keyEquivalent: "")
    let permission = NSMenuItem(title: "Notifications: checking…", action: nil, keyEquivalent: "")
    let pauseItem = NSMenuItem(title: "Pause monitoring", action: #selector(togglePause), keyEquivalent: "")
    let root = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/Breadfast Local", isDirectory: true)
    var center: UNUserNotificationCenter { UNUserNotificationCenter.current() }

    func applicationDidFinishLaunching(_ notification: Notification) {
        center.delegate = self
        item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        item.button?.title = "BF"
        item.button?.image = NSImage(systemSymbolName: "basket", accessibilityDescription: "Breadfast Local")
        let menu = NSMenu()
        menu.addItem(withTitle: "Breadfast · October · ≥50%", action: nil, keyEquivalent: "")
        menu.addItem(status); menu.addItem(permission)
        menu.addItem(withTitle: "All known prices: 30s · restaurants: 2m · discovery: 3m", action: nil, keyEquivalent: "")
        menu.addItem(.separator())
        for (title, action) in [("View offers & history", #selector(openOffers)), ("Scan offers now", #selector(scanOffers)), ("Full scan now", #selector(scanFull)), ("Test notification", #selector(testNotification)), ("Notification settings", #selector(openSettings))] {
            let entry = NSMenuItem(title: title, action: action, keyEquivalent: ""); entry.target = self; menu.addItem(entry)
        }
        pauseItem.target = self; menu.addItem(pauseItem)
        let quit = NSMenuItem(title: "Quit Breadfast Local", action: #selector(quitApp), keyEquivalent: "q"); quit.target = self
        menu.addItem(.separator()); menu.addItem(quit); item.menu = menu
        try? FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        center.requestAuthorization(options: [.alert, .sound]) { _, _ in self.refreshPermissions() }
        NSWorkspace.shared.notificationCenter.addObserver(self, selector: #selector(woke), name: NSWorkspace.didWakeNotification, object: nil)
        timer = Timer.scheduledTimer(withTimeInterval: 30, repeats: true) { _ in self.runScan("auto") }
        runScan("auto")
    }

    func refreshPermissions() {
        center.getNotificationSettings { settings in
            let enabled = settings.authorizationStatus == .authorized
            DispatchQueue.main.async { self.permission.title = enabled ? "Notifications: allowed" : "Notifications: allow in Settings" }
            self.writeAppStatus(["notification_authorization": settings.authorizationStatus.rawValue, "notifications_allowed": enabled])
        }
    }

    func writeAppStatus(_ value: [String: Any]) {
        if let data = try? JSONSerialization.data(withJSONObject: value, options: [.prettyPrinted]) {
            try? data.write(to: root.appendingPathComponent("app-status.json"), options: .atomic)
        }
    }

    func worker(_ arguments: [String], input: Data? = nil) throws -> [String: Any] {
        let configData = try Data(contentsOf: root.appendingPathComponent("config.json"))
        let config = try JSONSerialization.jsonObject(with: configData) as! [String: Any]
        let process = Process()
        process.executableURL = URL(fileURLWithPath: config["python"] as! String)
        let script = Bundle.main.resourceURL!.appendingPathComponent("local_worker.py").path
        process.arguments = ["-B", script, "--root", root.path] + arguments
        let pipe = Pipe(); process.standardOutput = pipe
        let log = root.appendingPathComponent("worker.log")
        if !FileManager.default.fileExists(atPath: log.path) { FileManager.default.createFile(atPath: log.path, contents: nil) }
        let err = try FileHandle(forWritingTo: log); err.seekToEndOfFile(); process.standardError = err
        let stdin = Pipe(); process.standardInput = stdin
        try process.run()
        if let data = input { stdin.fileHandleForWriting.write(data) }
        try? stdin.fileHandleForWriting.close()
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit(); try? err.close()
        if process.terminationStatus != 0 { throw NSError(domain: "Breadfast", code: Int(process.terminationStatus), userInfo: [NSLocalizedDescriptionKey: "Scanner failed; retrying next check"] ) }
        if arguments.contains("--ack") { return [:] }
        return try JSONSerialization.jsonObject(with: data) as! [String: Any]
    }

    func runScan(_ mode: String) {
        if paused { return }
        refreshPermissions()
        for source in ["grocery", "mall", "restaurants"] { runSource(source, mode: mode) }
    }

    func runSource(_ source: String, mode: String) {
        if paused { return }
        if busySources.contains(source) {
            if mode == "full" { queuedFull.insert(source) }
            return
        }
        busySources.insert(source); status.title = "Scanning \(busySources.count) sources…"; item.button?.title = "BF ↻"
        DispatchQueue.global(qos: .utility).async {
            do {
                let report = try self.worker(["--mode", mode, "--source", source])
                let errors = report["errors"] as? [String] ?? []
                let pending = report["pending"] as? [[String: Any]] ?? []
                self.deliver(pending)
                let summary = errors.isEmpty ? "\(report["offer_count"] ?? 0) offers · \(DateFormatter.localizedString(from: Date(), dateStyle: .none, timeStyle: .short))" : "Partial: " + errors.joined(separator: ", ")
                DispatchQueue.main.async {
                    self.status.title = summary; self.busySources.remove(source)
                    let error = errors.joined(separator: ", ")
                    if !error.isEmpty && error != self.lastErrors[source] { self.notify("Scan needs attention", body: summary, id: "health-" + source) }
                    self.lastErrors[source] = error
                    self.item.button?.title = self.busySources.isEmpty ? (self.lastErrors.values.contains(where: { !$0.isEmpty }) ? "BF !" : "BF") : "BF ↻"
                    if self.queuedFull.remove(source) != nil { self.runSource(source, mode: "full") }
                }
            } catch {
                DispatchQueue.main.async {
                    self.status.title = "\(source) failed — retrying"; self.item.button?.title = "BF !"; self.busySources.remove(source)
                    if self.lastErrors[source] != "scanner" { self.notify("Breadfast scan failed", body: source + " will retry. View worker.log for details.", id: "health-" + source) }
                    self.lastErrors[source] = "scanner"
                    if self.queuedFull.remove(source) != nil { self.runSource(source, mode: "full") }
                }
            }
        }
    }

    func deliver(_ events: [[String: Any]]) {
        if events.isEmpty { return }
        let ordered = events.sorted { (($0["offer"] as? [String:Any])?["discount_percent"] as? Double ?? 0) > (($1["offer"] as? [String:Any])?["discount_percent"] as? Double ?? 0) }
        let lines = ordered.prefix(3).map { event -> String in
            let offer = event["offer"] as! [String: Any]
            let names = offer["name"] as? [String: String] ?? [:]
            return "\(offer["discount_percent"] ?? 0)% · \(names["ar"] ?? names["en"] ?? "Product") · EGP \(offer["sale_price"] ?? 0)"
        }
        let ids = ordered.compactMap { $0["event_id"] as? String }
        let content = UNMutableNotificationContent()
        content.title = "\(events.count) new or improved Breadfast offers"
        content.body = lines.joined(separator: "\n") + (events.count > 3 ? "\n+\(events.count-3) more — click to view all" : "")
        content.sound = .default
        // Reusing this queue identifier after a crash replaces the same notice.
        let identifier = "offers-" + (ids.first ?? "pending")
        let semaphore = DispatchSemaphore(value: 0)
        center.getNotificationSettings { settings in
            guard settings.authorizationStatus == .authorized else { semaphore.signal(); return }
            self.center.add(UNNotificationRequest(identifier: identifier, content: content, trigger: nil)) { error in
                if error == nil, let data = try? JSONSerialization.data(withJSONObject: ids) {
                    _ = try? self.worker(["--ack"], input: data)
                }
                semaphore.signal()
            }
        }
        semaphore.wait()
    }

    func notify(_ title: String, body: String, id: String) {
        let content = UNMutableNotificationContent(); content.title = title; content.body = body; content.sound = .default
        center.add(UNNotificationRequest(identifier: id, content: content, trigger: nil)) { error in
            if let error = error { self.writeAppStatus(["notification_error": error.localizedDescription]) }
        }
    }
    @objc func testNotification() { notify("Breadfast Local is running", body: "اختبار الإشعارات — المراقبة كل 30 ثانية للعروض، والخصم من 50% وأكتر.", id: "test") }
    @objc func scanOffers() { runScan("offers") }
    @objc func scanFull() { runScan("full") }
    @objc func woke() { runScan("auto") }
    @objc func togglePause() { paused.toggle(); pauseItem.title = paused ? "Resume monitoring" : "Pause monitoring"; item.button?.title = paused ? "BF ⏸" : "BF"; if !paused { runScan("auto") } }
    @objc func openOffers() { NSWorkspace.shared.open(root.appendingPathComponent("offers.html")) }
    @objc func openSettings() { NSWorkspace.shared.open(URL(string: "x-apple.systempreferences:com.apple.Notifications-Settings.extension")!) }
    @objc func quitApp() { NSApp.terminate(nil) }
    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification, withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) { completionHandler([.banner, .list, .sound]) }
    func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse, withCompletionHandler completionHandler: @escaping () -> Void) { DispatchQueue.main.async { self.openOffers() }; completionHandler() }
}

let app = NSApplication.shared
let delegate = Monitor()
app.delegate = delegate
app.setActivationPolicy(.accessory)
app.run()
