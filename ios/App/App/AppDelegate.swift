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

    func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
        FirebaseApp.configure()
        applyBrandBackground()
        // Capacitor が window / WebView を用意した直後にも再適用
        DispatchQueue.main.async { [weak self] in
            self?.applyBrandBackground()
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.15) { [weak self] in
            self?.applyBrandBackground()
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
