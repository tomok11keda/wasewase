#import <Capacitor/Capacitor.h>

CAP_PLUGIN(FlashDiagPlugin, "FlashDiag",
    CAP_PLUGIN_METHOD(snapshot, CAPPluginReturnPromise);
    CAP_PLUGIN_METHOD(beginTrace, CAPPluginReturnPromise);
    CAP_PLUGIN_METHOD(endTrace, CAPPluginReturnPromise);
    CAP_PLUGIN_METHOD(drainNativeEvents, CAPPluginReturnPromise);
)
