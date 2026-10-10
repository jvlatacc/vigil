import Foundation

/// The watch's fixed User-Agent: `VigilWatch/1.0 (watchOS)`.
///
/// Vigil tokens carry an `sfp` claim — `sha256(User-Agent)[:16]`, verified on
/// every request (`core/auth/auth_service.py`). A client that varies its
/// User-Agent between token issuance and later calls gets 401 "Session
/// fingerprint mismatch", so this exact byte string rides on every request
/// the watch makes: refresh included.
///
/// The paired iPhone mints the watch's token pair by signing in AGAIN with
/// this same User-Agent (a second login, never the phone's live tokens), so
/// the pair is born bound to this string and the watch satisfies `sfp` on its
/// own session. The watch never sees the password.
public let vigilWatchUserAgent = "VigilWatch/1.0 (watchOS)"
