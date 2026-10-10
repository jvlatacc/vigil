import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif
@testable import VigilWatchClient

/// Scripted transport: records every request, answers by call index. Tests
/// assert on methods, paths, headers, and bodies — the exact wire contract
/// the `sfp` fingerprint and the five endpoints imply.
final class MockTransport: HTTPTransport, @unchecked Sendable {
    private let lock = NSLock()
    private var requests: [URLRequest] = []
    private let handler: @Sendable (_ request: URLRequest, _ index: Int) throws -> TransportResponse

    init(handler: @escaping @Sendable (_ request: URLRequest, _ index: Int) throws -> TransportResponse) {
        self.handler = handler
    }

    static let always500 = MockTransport { _, _ in
        TransportResponse(statusCode: 500, body: Data())
    }

    func send(_ request: URLRequest) async throws -> TransportResponse {
        let index = record(request)
        return try handler(request, index)
    }

    /// Locking lives in sync helpers — NSLock is deprecated from async
    /// contexts on Linux.
    private func record(_ request: URLRequest) -> Int {
        lock.lock()
        defer { lock.unlock() }
        requests.append(request)
        return requests.count - 1
    }

    // MARK: - Inspection

    var allRequests: [URLRequest] {
        lock.lock()
        defer { lock.unlock() }
        return requests
    }

    func request(_ index: Int) -> URLRequest { allRequests[index] }

    /// The User-Agent header of the request at `index` — the byte-stability
    /// proof.
    func userAgent(at index: Int) -> String? {
        allRequests[index].value(forHTTPHeaderField: "User-Agent")
    }

    func authorization(at index: Int) -> String? {
        allRequests[index].value(forHTTPHeaderField: "Authorization")
    }

    /// The JSON body of the request at `index` (assert-friendly).
    func jsonBody(at index: Int) throws -> [String: Any] {
        let data = allRequests[index].httpBody ?? Data()
        return try JSONSerialization.jsonObject(with: data) as? [String: Any] ?? [:]
    }
}
