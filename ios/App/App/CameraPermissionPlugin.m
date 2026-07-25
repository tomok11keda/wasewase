#import <Capacitor/Capacitor.h>

CAP_PLUGIN(CameraPermissionPlugin, "CameraPermission",
    CAP_PLUGIN_METHOD(checkAuthorization, CAPPluginReturnPromise);
    CAP_PLUGIN_METHOD(requestAuthorization, CAPPluginReturnPromise);
    CAP_PLUGIN_METHOD(isCameraAvailable, CAPPluginReturnPromise);
)
