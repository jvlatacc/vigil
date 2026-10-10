/// Typed failures the chat surface shows. The console's wording lives in
/// `clients/web/src/shell/Chat.tsx`: a failure the server *sent* is shown as
/// is; a failure *reaching* it gets the "Could not reach Vigil" wrap.
library;

/// Base class so the pane can handle any turn failure in one `on<ChatFailure>`.
abstract class ChatFailure implements Exception {
  ChatFailure(this.message);
  final String message;

  @override
  String toString() => '$runtimeType: $message';
}

/// The backend was reached and refused (HTTP detail, or an `{"error": …}`
/// frame). Shown as-is — the reason is the answer.
class ChatRefusal extends ChatFailure {
  ChatRefusal(super.message);
}

/// The backend was not reached (connection error, 502/503 — the console
/// treats those two statuses as "is the backend running?").
class ChatUnreachable extends ChatFailure {
  ChatUnreachable(super.message);
}

/// The session is over (consumed jti / blacklist after rotation): sign in
/// again. Wraps `AuthRevoked` from the auth layer.
class ChatAuthRevoked extends ChatFailure {
  ChatAuthRevoked() : super('Session ended — sign in again.');
}
