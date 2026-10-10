import Foundation
import WatchConnectivity

/// The phone-side half of the watch token handoff
/// (`clients/flutter/lib/watch/watch_handoff.dart` is the Dart twin).
///
/// On `mintAndSend` the bridge performs a SECOND `/api/auth/login` with the
/// watch's fixed User-Agent (`VigilWatch/1.0 (watchOS)`) — the resulting
/// token pair carries the `sfp` fingerprint the watch's requests present,
/// and is delivered over WatchConnectivity as the watch's OWN session. The
/// watch never sees the password and never shares the phone's live tokens,
/// so the single-use refresh rotation never contends between devices.
///
/// Delivery is two-channel by design: a live `sendMessage` when the watch is
/// reachable (fast), plus `updateApplicationContext` (background-reliable —
/// the watch picks the latest handoff up on next launch). A pair minted
/// before the WCSession activates is staged in the Keychain and flushed on
/// activation, so sign-in never has to wait on the watch.
final class WatchHandoffBridge: NSObject {
    /// Must match `HandoffConnector.messageKey` in the watch app.
    static let contextKey = "session_handoff"
    /// The UA the mint login presents — the tokens' sfp claim binds it, so
    /// it must equal the watch's own constant exactly.
    static let watchUserAgent = "VigilWatch/1.0 (watchOS)"
    static let channelName = "vigil/watch_handoff"

    private let keychainService = "ai.deeptempo.vigil.watch-handoff"

    private var channel: FlutterMethodChannel?
    private var session: WCSession?

    /// Registers the bridge on the Flutter messenger and activates
    /// WatchConnectivity (a staged handoff flushes on activation).
    static func register(with messenger: FlutterBinaryMessenger) {
        let bridge = WatchHandoffBridge()
        bridge.channel = FlutterMethodChannel(name: channelName, binaryMessenger: messenger)
        bridge.channel?.setMethodCallHandler { call, result in
            bridge.handle(call: call, result: result)
        }
        guard WCSession.isSupported() else { return }
        let session = WCSession.default
        session.delegate = bridge
        session.activate()
        bridge.session = session
    }

    private func handle(call: FlutterMethodCall, result: @escaping FlutterResult) {
        switch call.method {
        case "mintAndSend":
            guard let args = call.arguments as? [String: Any],
                  let serverBaseUrl = args["serverBaseUrl"] as? String,
                  let usernameOrEmail = args["usernameOrEmail"] as? String,
                  let password = args["password"] as? String
            else {
                result(FlutterError(code: "bad_arguments",
                                    message: "mintAndSend needs serverBaseUrl, usernameOrEmail, password",
                                    details: nil))
                return
            }
            let mfaCode = args["mfaCode"] as? String
            mintAndSend(
                serverBaseUrl: serverBaseUrl,
                usernameOrEmail: usernameOrEmail,
                password: password,
                mfaCode: mfaCode,
                result: result
            )
        case "revoke":
            revoke(result: result)
        default:
            result(FlutterMethodNotImplemented)
        }
    }

    // MARK: - Mint

    private func mintAndSend(
        serverBaseUrl: String,
        usernameOrEmail: String,
        password: String,
        mfaCode: String?,
        result: @escaping FlutterResult
    ) {
        guard let url = URL(string: serverBaseUrl.trimmingCharacters(in: ["/"]) + "/api/auth/login") else {
            result(FlutterError(code: "bad_arguments", message: "invalid serverBaseUrl", details: nil))
            return
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        // The sfp-bearing header: byte-identical to the watch's constant.
        request.setValue(Self.watchUserAgent, forHTTPHeaderField: "User-Agent")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        var body: [String: Any] = [
            "username_or_email": usernameOrEmail,
            "password": password,
        ]
        if let mfaCode { body["mfa_code"] = mfaCode }
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)

        let config = URLSessionConfiguration.ephemeral
        config.timeoutIntervalForRequest = 15
        let task = URLSession(configuration: config).dataTask(with: request) { [weak self] data, response, _ in
            DispatchQueue.main.async {
                self?.finishMint(
                    serverBaseUrl: serverBaseUrl,
                    data: data,
                    response: response,
                    result: result
                )
            }
        }
        task.resume()
    }

    private func finishMint(
        serverBaseUrl: String,
        data: Data?,
        response: URLResponse?,
        result: @escaping FlutterResult
    ) {
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard status == 200, let data else {
            // MFA demanded mid-mint or credentials refused — the mint fails;
            // the phone's own session is unaffected and the watch stays on
            // its pairing prompt until the next sign-in.
            result(FlutterError(
                code: status == 401 ? "mfa_required" : "mint_failed",
                message: "watch token mint returned HTTP \(status)",
                details: nil
            ))
            return
        }
        guard let payload = Self.decodeLogin(data: data, serverBaseUrl: serverBaseUrl) else {
            result(FlutterError(code: "mint_failed", message: "unparseable login response", details: nil))
            return
        }
        Self.stage(payload: payload, service: keychainService)
        result(deliver(payload: payload))
    }

    /// Codable decode of the login body (snake_case contract keys) into the
    /// camelCase wire payload the watch's `SessionHandoff(context:)` reads.
    static func decodeLogin(data: Data, serverBaseUrl: String) -> [String: Any]? {
        struct LoginBody: Decodable {
            struct User: Decodable { let username: String? }
            let access_token: String
            let refresh_token: String
            let user: User?
        }
        guard let body = try? JSONDecoder().decode(LoginBody.self, from: data) else { return nil }
        var payload: [String: Any] = [
            "serverBaseUrl": serverBaseUrl,
            "accessToken": body.access_token,
            "refreshToken": body.refresh_token,
        ]
        if let username = body.user?.username { payload["username"] = username }
        return payload
    }

    // MARK: - Delivery

    /// Sends the handoff to the watch. Returns "sent" when the live message
    /// was queued to a reachable watch, "deferred" when only the application
    /// context carries it (watch app asleep) — the context survives until
    /// the watch next launches.
    func deliver(_ payload: [String: Any]) -> String {
        guard let session, session.activationState == .activated else {
            // Not activated yet — the Keychain-staged copy flushes on
            // activation (see WCSessionDelegate below).
            return "deferred"
        }
        var context = session.receivedApplicationContext
        context[Self.contextKey] = payload
        try? session.updateApplicationContext(context)
        if session.isReachable {
            session.sendMessage([Self.contextKey: payload], replyHandler: nil, errorHandler: nil)
            return "sent"
        }
        return "deferred"
    }

    // MARK: - Revoke

    private func revoke(result: @escaping FlutterResult) {
        Self.stage(payload: nil, service: keychainService)
        guard let session, session.activationState == .activated else {
            result("deferred")
            return
        }
        var context = session.receivedApplicationContext
        // The cleared sentinel: keys present, values empty — the watch wipes
        // its stored session when `SessionHandoff.isCleared` reads true.
        context[Self.contextKey] = [
            "serverBaseUrl": "", "accessToken": "", "refreshToken": "",
        ]
        try? session.updateApplicationContext(context)
        if session.isReachable {
            session.sendMessage(context, replyHandler: nil, errorHandler: nil)
        }
        result("sent")
    }

    // MARK: - Keychain staging (deferred delivery)

    /// Stores (or clears) the staged handoff so a mint completed before the
    /// WCSession activates is not lost.
    static func stage(payload: [String: Any]?, service: String) {
        let base: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: "staged-handoff",
        ]
        SecItemDelete(base as CFDictionary)
        guard let payload else { return } // nil payload = clear
        guard let data = try? JSONSerialization.data(withJSONObject: payload) else { return }
        var add = base
        add[kSecValueData as String] = data
        SecItemAdd(add as CFDictionary, nil)
    }

    static func loadStaged(service: String) -> [String: Any]? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: "staged-handoff",
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
        var item: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess,
              let data = item as? Data
        else { return nil }
        return (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
    }
}

extension WatchHandoffBridge: WCSessionDelegate {
    func session(
        _ session: WCSession,
        activationDidCompleteWith activationState: WCSessionActivationState,
        error: Error?
    ) {
        // A mint that ran before activation (fast sign-in, slow radio) is
        // staged in the Keychain — flush it now.
        guard activationState == .activated,
              let staged = Self.loadStaged(service: keychainService)
        else { return }
        DispatchQueue.main.async { _ = self.deliver(staged) }
    }

    /// Phone-side lifecycle: re-activate on the watch's behalf.
    func sessionDidBecomeInactive(_ session: WCSession) {}

    func sessionDidDeactivate(_ session: WCSession) {
        session.activate()
    }
}
