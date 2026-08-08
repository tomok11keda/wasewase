import Foundation
import Capacitor
import UIKit
import WebKit

/// Observation-only plugin for TestFlight / Simulator flash diagnosis.
/// Does not change AdMob, layout, or WebView appearance.
@objc(FlashDiagPlugin)
public class FlashDiagPlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "FlashDiagPlugin"
    public let jsName = "FlashDiag"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "snapshot", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "beginTrace", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "endTrace", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "drainNativeEvents", returnType: CAPPluginReturnPromise),
    ]

    private var displayLink: CADisplayLink?
    private var samplingUntil: CFTimeInterval = 0
    private var lastSampleSignature: String = ""
    private var nativeEvents: [[String: Any]] = []
    private var activeTraceId: String?
    private var sampleCount: Int = 0
    private let maxNativeEvents = 300

    @objc func beginTrace(_ call: CAPPluginCall) {
        let traceId = call.getString("traceId") ?? UUID().uuidString
        activeTraceId = traceId
        nativeEvents.removeAll(keepingCapacity: true)
        lastSampleSignature = ""
        sampleCount = 0
        appendEvent("native_trace_begin", [
            "traceId": traceId,
            "path": call.getString("path") ?? "",
            "mode": call.getString("mode") ?? "",
        ])
        startSampling(durationMs: call.getDouble("sampleMs") ?? 500)
        call.resolve(["traceId": traceId, "sampling": true])
    }

    @objc func endTrace(_ call: CAPPluginCall) {
        stopSampling()
        appendEvent("native_trace_end", [
            "traceId": activeTraceId ?? "",
            "sampleCount": sampleCount,
        ])
        let events = nativeEvents
        activeTraceId = nil
        call.resolve([
            "events": events,
            "eventCount": events.count,
        ])
    }

    @objc func drainNativeEvents(_ call: CAPPluginCall) {
        let events = nativeEvents
        nativeEvents.removeAll(keepingCapacity: true)
        call.resolve(["events": events])
    }

    @objc func snapshot(_ call: CAPPluginCall) {
        DispatchQueue.main.async {
            let reason = call.getString("reason") ?? "snapshot"
            let payload = self.collectSnapshot(reason: reason)
            self.appendEvent("native_snapshot", payload)
            call.resolve(payload)
        }
    }

    private func startSampling(durationMs: Double) {
        stopSampling()
        samplingUntil = CACurrentMediaTime() + max(0.05, durationMs / 1000.0)
        let link = CADisplayLink(target: self, selector: #selector(onDisplayTick))
        link.add(to: .main, forMode: .common)
        displayLink = link
    }

    private func stopSampling() {
        displayLink?.invalidate()
        displayLink = nullifyDisplayLink()
    }

    private func nullifyDisplayLink() -> CADisplayLink? {
        nil
    }

    @objc private func onDisplayTick() {
        let now = CACurrentMediaTime()
        if now > samplingUntil {
            stopSampling()
            appendEvent("native_sampling_end", ["sampleCount": sampleCount])
            return
        }
        sampleCount += 1
        let snap = collectSnapshot(reason: "display_tick")
        let signature = snapshotSignature(snap)
        if signature != lastSampleSignature {
            lastSampleSignature = signature
            appendEvent("native_layout_change", snap)
        }
    }

    private func appendEvent(_ type: String, _ data: [String: Any]) {
        if nativeEvents.count >= maxNativeEvents {
            return
        }
        nativeEvents.append([
            "t": CACurrentMediaTime(),
            "wall": isoNow(),
            "type": type,
            "data": data,
            "traceId": activeTraceId ?? "",
        ])
        #if DEBUG
        NSLog("[WaseFlashDiag] %@ %@", type, String(describing: data["reason"] ?? ""))
        #endif
    }

    private func isoNow() -> String {
        ISO8601DateFormatter().string(from: Date())
    }

    private func collectSnapshot(reason: String) -> [String: Any] {
        var out: [String: Any] = [
            "reason": reason,
            "animationsEnabled": UIView.areAnimationsEnabled,
        ]

        guard let window = UIApplication.shared.connectedScenes
            .compactMap({ $0 as? UIWindowScene })
            .flatMap({ $0.windows })
            .first(where: { $0.isKeyWindow })
            ?? UIApplication.shared.windows.first
        else {
            out["error"] = "no_window"
            return out
        }

        out["window"] = describeView(window, name: "window")

        var webViewInfo: [String: Any] = [:]
        var bannerViews: [[String: Any]] = []
        var layoutDirtyHints: [String] = []

        func walk(_ view: UIView, depth: Int) {
            if depth > 24 {
                return
            }
            let className = NSStringFromClass(type(of: view))
            if view is WKWebView, let wv = view as? WKWebView {
                webViewInfo = describeWebView(wv)
            }
            let lower = className.lowercased()
            if lower.contains("banner")
                || lower.contains("gadbannerview")
                || lower.contains("gadview")
                || lower.contains("admob")
            {
                bannerViews.append(describeView(view, name: className))
            }
            if let keys = view.layer.animationKeys(), !keys.isEmpty {
                layoutDirtyHints.append("\(className)#anim:\(keys.joined(separator: ","))")
            }
            // Heuristic: non-identity transform often accompanies layout animation
            if !view.transform.isIdentity {
                layoutDirtyHints.append("\(className)#transform")
            }
            for child in view.subviews {
                walk(child, depth: depth + 1)
            }
        }

        if let root = window.rootViewController?.view {
            out["rootView"] = describeView(root, name: "rootViewController.view")
            walk(root, depth: 0)
        } else {
            walk(window, depth: 0)
        }

        out["webView"] = webViewInfo
        out["bannerViews"] = bannerViews
        out["bannerViewCount"] = bannerViews.count
        out["layoutDirtyHints"] = Array(layoutDirtyHints.prefix(20))
        out["inFlightAnimation"] = !layoutDirtyHints.filter { $0.contains("#anim:") }.isEmpty
        return out
    }

    private func describeWebView(_ webView: WKWebView) -> [String: Any] {
        var info = describeView(webView, name: "WKWebView")
        info["isOpaque"] = webView.isOpaque
        info["backgroundColor"] = colorString(webView.backgroundColor)
        info["scrollViewBackgroundColor"] = colorString(webView.scrollView.backgroundColor)
        info["scrollViewIsOpaque"] = webView.scrollView.isOpaque
        if #available(iOS 15.0, *) {
            info["underPageBackgroundColor"] = colorString(webView.underPageBackgroundColor)
        } else {
            info["underPageBackgroundColor"] = "unavailable(<iOS15)"
        }
        info["scrollViewContentOffset"] = [
            "x": webView.scrollView.contentOffset.x,
            "y": webView.scrollView.contentOffset.y,
        ]
        return info
    }

    private func describeView(_ view: UIView, name: String) -> [String: Any] {
        let frame = view.frame
        return [
            "class": name,
            "frame": [
                "x": frame.origin.x,
                "y": frame.origin.y,
                "w": frame.size.width,
                "h": frame.size.height,
            ],
            "bounds": [
                "w": view.bounds.size.width,
                "h": view.bounds.size.height,
            ],
            "alpha": view.alpha,
            "isHidden": view.isHidden,
            "isOpaque": view.isOpaque,
            "backgroundColor": colorString(view.backgroundColor),
            "transformIsIdentity": view.transform.isIdentity,
        ]
    }

    private func colorString(_ color: UIColor?) -> String {
        guard let color = color else {
            return "nil"
        }
        var r: CGFloat = 0
        var g: CGFloat = 0
        var b: CGFloat = 0
        var a: CGFloat = 0
        if color.getRed(&r, green: &g, blue: &b, alpha: &a) {
            return String(format: "rgba(%.3f,%.3f,%.3f,%.3f)", r, g, b, a)
        }
        return String(describing: color)
    }

    private func snapshotSignature(_ snap: [String: Any]) -> String {
        let banners = snap["bannerViews"] as? [[String: Any]] ?? []
        let web = snap["webView"] as? [String: Any] ?? [:]
        let bannerPart = banners.map { b -> String in
            let frame = b["frame"] as? [String: Any] ?? [:]
            return "\(b["class"] ?? "")|\(frame["x"] ?? "")|\(frame["y"] ?? "")|\(frame["w"] ?? "")|\(frame["h"] ?? "")|\(b["alpha"] ?? "")|\(b["isHidden"] ?? "")"
        }.joined(separator: ";")
        let webFrame = web["frame"] as? [String: Any] ?? [:]
        return "\(bannerPart)#\(webFrame["y"] ?? "")#\(web["isOpaque"] ?? "")#\(web["backgroundColor"] ?? "")#\(snap["inFlightAnimation"] ?? false)"
    }
}
