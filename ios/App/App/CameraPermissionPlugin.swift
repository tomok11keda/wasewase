import Foundation
import Capacitor
import AVFoundation

@objc(CameraPermissionPlugin)
public class CameraPermissionPlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "CameraPermissionPlugin"
    public let jsName = "CameraPermission"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "checkAuthorization", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "requestAuthorization", returnType: CAPPluginReturnPromise),
    ]

    @objc func checkAuthorization(_ call: CAPPluginCall) {
        let status = AVCaptureDevice.authorizationStatus(for: .video)
        call.resolve([
            "status": Self.stringify(status),
            "granted": status == .authorized,
        ])
    }

    @objc func requestAuthorization(_ call: CAPPluginCall) {
        let currentStatus = AVCaptureDevice.authorizationStatus(for: .video)

        if currentStatus == .authorized {
            call.resolve([
                "status": Self.stringify(currentStatus),
                "granted": true,
            ])
            return
        }

        if currentStatus == .denied || currentStatus == .restricted {
            call.resolve([
                "status": Self.stringify(currentStatus),
                "granted": false,
            ])
            return
        }

        AVCaptureDevice.requestAccess(for: .video) { granted in
            DispatchQueue.main.async {
                let status = AVCaptureDevice.authorizationStatus(for: .video)
                call.resolve([
                    "status": Self.stringify(status),
                    "granted": granted && status == .authorized,
                ])
            }
        }
    }

    private static func stringify(_ status: AVAuthorizationStatus) -> String {
        switch status {
        case .notDetermined:
            return "notDetermined"
        case .restricted:
            return "restricted"
        case .denied:
            return "denied"
        case .authorized:
            return "authorized"
        @unknown default:
            return "unknown"
        }
    }
}
