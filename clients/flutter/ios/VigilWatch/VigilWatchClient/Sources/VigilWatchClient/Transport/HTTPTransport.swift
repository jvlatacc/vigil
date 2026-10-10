import Foundation
#if canImport(FoundationNetworking)
// Linux's Foundation puts URLSession/URLRequest in FoundationNetworking.
// The watch itself is watchOS; this guard keeps `swift build/test` green
// in the sandbox's Linux CI.
import FoundationNetworking
#endif

/// The pluggable HTTP surface of `VigilWatchAPI` — one method, request in,
/// response out. Production uses `URLSessionTransport`; tests use a mock.
public protocol HTTPTransport: Sendable {
    func send(_ request: URLRequest) async throws -> TransportResponse
}

/// The transport's response: status, body bytes, and the response headers
/// the error mapper needs (`Retry-After` on 423 lockout; MFA never applies
/// here — the watch never logs in).
public struct TransportResponse: Sendable {
    public let statusCode: Int
    public let body: Data
    public let headers: [String: String]

    public init(statusCode: Int, body: Data = Data(), headers: [String: String] = [:]) {
        self.statusCode = statusCode
        self.body = body
        self.headers = headers
    }
}

/// URLSession-backed transport. `requestTimeout` matches the console's
/// 30-second receive timeout — a wrist tap must fail fast enough to queue.
public struct URLSessionTransport: HTTPTransport, @unchecked Sendable {
    // URLSession is documented thread-safe; the unchecked box only covers
    // the Linux toolchain, which models it as a plain AnyObject.
    private let session: URLSession

    public init(requestTimeout: TimeInterval = 30) {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = requestTimeout
        self.session = URLSession(configuration: configuration)
    }

    public init(session: URLSession) {
        self.session = session
    }

    public func send(_ request: URLRequest) async throws -> TransportResponse {
        let (data, response): (Data, URLResponse)
        do {
            (data, response) = try await session.data(for: request)
        } catch {
            throw HTTPTransportError.network(String(describing: error))
        }
        guard let http = response as? HTTPURLResponse else {
            throw HTTPTransportError.network("non-HTTP response")
        }
        var headers: [String: String] = [:]
        for (key, value) in http.allHeaderFields {
            if let key = key as? String, let value = value as? String {
                headers[key.lowercased()] = value
            }
        }
        return TransportResponse(statusCode: http.statusCode, body: data, headers: headers)
    }
}

public enum HTTPTransportError: Error, Equatable {
    case network(String)
}
