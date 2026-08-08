import UIKit
import Capacitor
import FirebaseCore
import WebKit

@UIApplicationMain
class AppDelegate: UIResponder, UIApplicationDelegate {

    var window: UIWindow?

    /// 早稲田エンジ #891E2B — LaunchScreen / WebView の隙間で白が出ないようにする
    private let brandBurgundy = UIColor(
        red: 137.0 / 255.0,
        green: 30.0 / 255.0,
        blue: 43.0 / 255.0,
        alpha: 1.0
    )

    /// Temporary: boot URL diagnostic overlay (native UIView — no React dependency).
    private weak var bootUrlDiagView: UIView?
    private weak var bootUrlDiagTextView: UITextView?

    func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
        FirebaseApp.configure()
        applyBrandBackground()
        // Capacitor が window / WebView を用意した直後にも再適用
        DispatchQueue.main.async { [weak self] in
            self?.applyBrandBackground()
            self?.refreshBootUrlDiag(reason: "launch-async")
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.15) { [weak self] in
            self?.applyBrandBackground()
        }
        // Temporary: capture initial WKWebView URL after load has had time to settle
        for delay in [0.5, 1.5, 3.0, 5.0] as [Double] {
            DispatchQueue.main.asyncAfter(deadline: .now() + delay) { [weak self] in
                self?.refreshBootUrlDiag(reason: "launch+\(delay)s")
            }
        }
        // Cold start via wasewase://spa-diag/...
        if let url = launchOptions?[.url] as? URL {
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.6) { [weak self] in
                _ = self?.handleSpaDiagDeepLink(url)
            }
        }
        return true
    }

    private func applyBrandBackground() {
        window?.backgroundColor = brandBurgundy
        window?.rootViewController?.view.backgroundColor = brandBurgundy

        guard let bridge = window?.rootViewController as? CAPBridgeViewController else {
            return
        }
        bridge.view.backgroundColor = brandBurgundy
        if let webView = bridge.webView {
            webView.isOpaque = false
            webView.backgroundColor = brandBurgundy
            webView.scrollView.backgroundColor = brandBurgundy
            webView.scrollView.contentInsetAdjustmentBehavior = .never
            // fixed ヘッダーとラバーバンドの描画ずれを防ぐ
            webView.scrollView.bounces = false
            webView.scrollView.alwaysBounceVertical = false
            webView.scrollView.alwaysBounceHorizontal = false
        }
    }

    func application(_ application: UIApplication, didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        NotificationCenter.default.post(name: .capacitorDidRegisterForRemoteNotifications, object: deviceToken)
    }

    func application(_ application: UIApplication, didFailToRegisterForRemoteNotificationsWithError error: Error) {
        NotificationCenter.default.post(name: .capacitorDidFailToRegisterForRemoteNotifications, object: error)
    }

    func applicationWillResignActive(_ application: UIApplication) {
        // Sent when the application is about to move from active to inactive state. This can occur for certain types of temporary interruptions (such as an incoming phone call or SMS message) or when the user quits the application and it begins the transition to the background state.
        // Use this method to pause ongoing tasks, disable timers, and invalidate graphics rendering callbacks. Games should use this method to pause the game.
    }

    func applicationDidEnterBackground(_ application: UIApplication) {
        // Use this method to release shared resources, save user data, invalidate timers, and store enough application state information to restore your application to its current state in case it is terminated later.
        // If your application supports background execution, this method is called instead of applicationWillTerminate: when the user quits.
    }

    func applicationWillEnterForeground(_ application: UIApplication) {
        // Called as part of the transition from the background to the active state; here you can undo many of the changes made on entering the background.
    }

    func applicationDidBecomeActive(_ application: UIApplication) {
        applyBrandBackground()
        refreshBootUrlDiag(reason: "become-active")
    }

    func applicationWillTerminate(_ application: UIApplication) {
        // Called when the application is about to terminate. Save data if appropriate. See also applicationDidEnterBackground:.
    }

    func application(_ app: UIApplication, open url: URL, options: [UIApplication.OpenURLOptionsKey: Any] = [:]) -> Bool {
        // TestFlight 診断専用: wasewase://spa-diag/no_banner 等
        if handleSpaDiagDeepLink(url) {
            return true
        }
        return ApplicationDelegateProxy.shared.application(app, open: url, options: options)
    }

    func application(_ application: UIApplication, continue userActivity: NSUserActivity, restorationHandler: @escaping ([UIUserActivityRestoring]?) -> Void) -> Bool {
        // Called when the app was launched with an activity, including Universal Links.
        // Use this method to restore the user activity and continue it.
        return ApplicationDelegateProxy.shared.application(application, continue: userActivity, restorationHandler: restorationHandler)
    }

    // MARK: - Temporary boot URL diagnostic (native only)

    /// Shows WKWebView.url + page facts on a native overlay.
    /// Does not depend on React / Capacitor JS / AdMob / KeepAlive.
    private func refreshBootUrlDiag(reason: String) {
        guard let hostView = window?.rootViewController?.view else {
            NSLog("[WaseBootUrlDiag] no host view (%@)", reason)
            return
        }

        let bridge = window?.rootViewController as? CAPBridgeViewController
        let webView = bridge?.webView
        let nativeUrl = webView?.url?.absoluteString ?? "(nil — WebView not ready)"
        NSLog("[WaseBootUrlDiag] %@ WKWebView.url=%@", reason, nativeUrl)

        ensureBootUrlDiagOverlay(on: hostView)
        updateBootUrlDiagText(
            nativeUrl: nativeUrl,
            locationHref: "(reading…)",
            title: "(reading…)",
            hasRoot: "(reading…)",
            hasMainJs: "(reading…)",
            reason: reason
        )

        guard let webView = webView else {
            return
        }

        // Read DOM facts from the currently loaded document (works without React).
        let js = """
        (function(){
          var href = '';
          var title = '';
          var hasRoot = false;
          var hasMain = false;
          try { href = String(location.href || ''); } catch (e) { href = '(error)'; }
          try { title = String(document.title || ''); } catch (e) { title = '(error)'; }
          try { hasRoot = !!document.getElementById('root'); } catch (e) {}
          try {
            var nodes = document.querySelectorAll('script[src]');
            for (var i = 0; i < nodes.length; i++) {
              var src = String(nodes[i].getAttribute('src') || '');
              if (src.indexOf('/static/frontend/assets/main.js') !== -1) { hasMain = true; break; }
              if (src.indexOf('frontend/assets/main.js') !== -1) { hasMain = true; break; }
            }
          } catch (e) {}
          return JSON.stringify({
            href: href,
            title: title,
            hasRoot: hasRoot,
            hasMain: hasMain
          });
        })();
        """

        webView.evaluateJavaScript(js) { [weak self] result, error in
            var href = "(evaluate failed)"
            var title = "(evaluate failed)"
            var hasRoot = "(evaluate failed)"
            var hasMain = "(evaluate failed)"

            if let error = error {
                NSLog("[WaseBootUrlDiag] evaluateJS error: %@", String(describing: error))
                href = "(JS error: \(error.localizedDescription))"
            } else if let raw = result as? String,
                      let data = raw.data(using: .utf8),
                      let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                href = String(describing: obj["href"] ?? "")
                title = String(describing: obj["title"] ?? "")
                if let b = obj["hasRoot"] as? Bool {
                    hasRoot = b ? "YES" : "NO"
                } else {
                    hasRoot = String(describing: obj["hasRoot"] ?? "")
                }
                if let b = obj["hasMain"] as? Bool {
                    hasMain = b ? "YES" : "NO"
                } else {
                    hasMain = String(describing: obj["hasMain"] ?? "")
                }
            }

            DispatchQueue.main.async {
                self?.updateBootUrlDiagText(
                    nativeUrl: nativeUrl,
                    locationHref: href,
                    title: title,
                    hasRoot: hasRoot,
                    hasMainJs: hasMain,
                    reason: reason
                )
            }
        }
    }

    private func ensureBootUrlDiagOverlay(on hostView: UIView) {
        if bootUrlDiagView != nil {
            hostView.bringSubviewToFront(bootUrlDiagView!)
            return
        }

        let panel = UIView()
        panel.translatesAutoresizingMaskIntoConstraints = false
        panel.backgroundColor = UIColor(red: 0.05, green: 0.08, blue: 0.12, alpha: 0.96)
        panel.layer.borderColor = UIColor.cyan.cgColor
        panel.layer.borderWidth = 3
        panel.layer.cornerRadius = 12
        panel.clipsToBounds = true

        let title = UILabel()
        title.translatesAutoresizingMaskIntoConstraints = false
        title.text = "WASE BOOT URL DEBUG"
        title.textColor = .cyan
        title.font = .boldSystemFont(ofSize: 18)
        title.numberOfLines = 1

        let text = UITextView()
        text.translatesAutoresizingMaskIntoConstraints = false
        text.backgroundColor = .clear
        text.textColor = .white
        text.font = .monospacedSystemFont(ofSize: 13, weight: .regular)
        text.isEditable = false
        text.isScrollEnabled = true
        text.textContainerInset = UIEdgeInsets(top: 4, left: 4, bottom: 4, right: 4)

        let close = UIButton(type: .system)
        close.translatesAutoresizingMaskIntoConstraints = false
        close.setTitle("Close", for: .normal)
        close.setTitleColor(.white, for: .normal)
        close.titleLabel?.font = .boldSystemFont(ofSize: 14)
        close.backgroundColor = UIColor(white: 0.25, alpha: 1)
        close.layer.cornerRadius = 8
        close.contentEdgeInsets = UIEdgeInsets(top: 6, left: 12, bottom: 6, right: 12)
        close.addTarget(self, action: #selector(dismissBootUrlDiag), for: .touchUpInside)

        panel.addSubview(title)
        panel.addSubview(close)
        panel.addSubview(text)
        hostView.addSubview(panel)

        let guide = hostView.safeAreaLayoutGuide
        NSLayoutConstraint.activate([
            panel.leadingAnchor.constraint(equalTo: hostView.leadingAnchor, constant: 8),
            panel.trailingAnchor.constraint(equalTo: hostView.trailingAnchor, constant: -8),
            panel.topAnchor.constraint(equalTo: guide.topAnchor, constant: 8),
            panel.heightAnchor.constraint(lessThanOrEqualTo: hostView.heightAnchor, multiplier: 0.55),
            panel.heightAnchor.constraint(greaterThanOrEqualToConstant: 220),

            title.leadingAnchor.constraint(equalTo: panel.leadingAnchor, constant: 12),
            title.topAnchor.constraint(equalTo: panel.topAnchor, constant: 10),
            title.trailingAnchor.constraint(lessThanOrEqualTo: close.leadingAnchor, constant: -8),

            close.trailingAnchor.constraint(equalTo: panel.trailingAnchor, constant: -10),
            close.centerYAnchor.constraint(equalTo: title.centerYAnchor),

            text.leadingAnchor.constraint(equalTo: panel.leadingAnchor, constant: 8),
            text.trailingAnchor.constraint(equalTo: panel.trailingAnchor, constant: -8),
            text.topAnchor.constraint(equalTo: title.bottomAnchor, constant: 8),
            text.bottomAnchor.constraint(equalTo: panel.bottomAnchor, constant: -8),
        ])

        bootUrlDiagView = panel
        bootUrlDiagTextView = text
        hostView.bringSubviewToFront(panel)
    }

    private func updateBootUrlDiagText(
        nativeUrl: String,
        locationHref: String,
        title: String,
        hasRoot: String,
        hasMainJs: String,
        reason: String
    ) {
        let body = """
        WKWebView.url:
        \(nativeUrl)

        window.location.href:
        \(locationHref)

        document.title:
        \(title)

        #root exists:
        \(hasRoot)

        React main.js loaded:
        \(hasMainJs)

        expected server.url:
        https://wasewase.onrender.com/app/

        refresh: \(reason)
        """
        bootUrlDiagTextView?.text = body
        if let panel = bootUrlDiagView, let host = panel.superview {
            host.bringSubviewToFront(panel)
        }
    }

    @objc private func dismissBootUrlDiag() {
        bootUrlDiagView?.removeFromSuperview()
        bootUrlDiagView = nil
        bootUrlDiagTextView = nil
    }

    /// wasewase://spa-diag/<mode> → WKWebView で /app/?spa_flash_diag=&spa_nav_diag= を開く
    @discardableResult
    private func handleSpaDiagDeepLink(_ url: URL) -> Bool {
        guard url.scheme?.lowercased() == "wasewase" else {
            return false
        }
        let host = (url.host ?? "").lowercased()
        guard host == "spa-diag" else {
            return false
        }

        var mode = url.path
            .trimmingCharacters(in: CharacterSet(charactersIn: "/"))
            .lowercased()
        if mode.isEmpty {
            let items = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems
            mode = (items?.first(where: { $0.name == "mode" })?.value ?? "normal").lowercased()
        }

        let allowed: Set<String> = [
            "normal", "no_banner", "off", "no_bridge",
            "no_analytics", "no_keepalive", "no_transition", "clear",
        ]
        if !allowed.contains(mode) {
            mode = "normal"
        }

        let flashOn = !(mode == "normal" || mode == "clear")
        let navValue = (mode == "normal") ? "clear" : mode

        // Prefer current WebView origin (remote server or local)
        var components = URLComponents()
        if let bridge = window?.rootViewController as? CAPBridgeViewController,
           let current = bridge.webView?.url {
            components.scheme = current.scheme
            components.host = current.host
            components.port = current.port
        } else {
            components.scheme = "https"
            components.host = "wasewase.onrender.com"
        }
        components.path = "/app/"
        components.queryItems = [
            URLQueryItem(name: "spa_flash_diag", value: flashOn ? "1" : "0"),
            URLQueryItem(name: "spa_nav_diag", value: navValue),
        ]
        guard let target = components.url else {
            return true
        }

        DispatchQueue.main.async { [weak self] in
            self?.navigateWebView(to: target, mode: mode, flashOn: flashOn)
        }
        return true
    }

    private func navigateWebView(to target: URL, mode: String, flashOn: Bool) {
        guard let bridge = window?.rootViewController as? CAPBridgeViewController,
              let webView = bridge.webView else {
            return
        }

        // localStorage を先に合わせてから遷移（既存 JS 診断機構と整合）
        let navLiteral = (mode == "normal" || mode == "clear") ? "" : mode
        let flashJs = flashOn ? "localStorage.setItem('wase_flash_diag','1');" : "localStorage.removeItem('wase_flash_diag');"
        let navJs: String
        if navLiteral.isEmpty {
            navJs = "localStorage.removeItem('wase_spa_nav_diag');"
        } else {
            navJs = "localStorage.setItem('wase_spa_nav_diag','\(navLiteral)');"
        }
        let js = """
        (function(){
          try { \(flashJs) \(navJs) } catch (e) {}
          location.href = \(jsonString(target.absoluteString));
        })();
        """
        webView.evaluateJavaScript(js, completionHandler: nil)
    }

    private func jsonString(_ value: String) -> String {
        let data = try? JSONSerialization.data(withJSONObject: value, options: [])
        if let data = data, let s = String(data: data, encoding: .utf8) {
            return s
        }
        return "\"\(value)\""
    }

}
