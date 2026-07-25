import Foundation
import Capacitor
import AVFoundation
import UIKit

@objc(CameraPermissionPlugin)
public class CameraPermissionPlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "CameraPermissionPlugin"
    public let jsName = "CameraPermission"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "checkAuthorization", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "requestAuthorization", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "isCameraAvailable", returnType: CAPPluginReturnPromise),
    ]

    @objc func checkAuthorization(_ call: CAPPluginCall) {
        let status = AVCaptureDevice.authorizationStatus(for: .video)
        call.resolve([
            "status": Self.stringify(status),
            "granted": status == .authorized,
            "cameraAvailable": Self.isCameraHardwareAvailable(),
        ])
    }

    @objc func requestAuthorization(_ call: CAPPluginCall) {
        let currentStatus = AVCaptureDevice.authorizationStatus(for: .video)

        if currentStatus == .authorized {
            call.resolve([
                "status": Self.stringify(currentStatus),
                "granted": true,
                "cameraAvailable": Self.isCameraHardwareAvailable(),
            ])
            return
        }

        if currentStatus == .denied || currentStatus == .restricted {
            call.resolve([
                "status": Self.stringify(currentStatus),
                "granted": false,
                "cameraAvailable": Self.isCameraHardwareAvailable(),
            ])
            return
        }

        AVCaptureDevice.requestAccess(for: .video) { granted in
            DispatchQueue.main.async {
                let status = AVCaptureDevice.authorizationStatus(for: .video)
                call.resolve([
                    "status": Self.stringify(status),
                    "granted": granted && status == .authorized,
                    "cameraAvailable": Self.isCameraHardwareAvailable(),
                ])
            }
        }
    }

    /// UIImagePickerController でカメラを開く前に必須の利用可否チェック。
    /// シミュレーターやカメラ非搭載端末では false を返し、クラッシュを防ぐ。
    @objc func isCameraAvailable(_ call: CAPPluginCall) {
        let cameraAvailable = Self.isCameraHardwareAvailable()
        let photoLibraryAvailable = UIImagePickerController.isSourceTypeAvailable(.photoLibrary)
        call.resolve([
            "available": cameraAvailable,
            "camera": cameraAvailable,
            "photoLibrary": photoLibraryAvailable,
        ])
    }

    private static func isCameraHardwareAvailable() -> Bool {
        UIImagePickerController.isSourceTypeAvailable(.camera)
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
