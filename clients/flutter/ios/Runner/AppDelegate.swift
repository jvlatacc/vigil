import Flutter
import UIKit

@main
@objc class AppDelegate: FlutterAppDelegate {
  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    GeneratedPluginRegistrant.register(with: self)
    // Watch token handoff (spec: the phone mints the watch its own pair at
    // sign-in). The bridge is inert off a paired watch — WCSession reports
    // unsupported and the channel answers with a typed outcome.
    if let controller = window?.rootViewController as? FlutterViewController {
      WatchHandoffBridge.register(with: controller.binaryMessenger)
    }
    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }
}
