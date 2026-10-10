// Typed auth failures the UI must branch on.
//
// Mirrors the backend's observable auth behavior (services/api/routers/auth.py):
// 401 with `X-MFA-Required: true` when TOTP is pending, 423 with `Retry-After`
// on account lockout, plain 401 on bad credentials, and 401 from
// /api/auth/refresh when the refresh token is revoked or its single-use jti
// was already consumed.
import 'package:dio/dio.dart';

/// Base class of every typed auth failure.
sealed class VigilAuthException implements Exception {
  VigilAuthException(this.message, {this.statusCode});

  final String message;
  final int? statusCode;

  @override
  String toString() => '$runtimeType: $message';
}

/// 401 without the MFA header — wrong username/email or password.
class InvalidCredentials extends VigilAuthException {
  InvalidCredentials({super.statusCode})
      : super('Invalid username/email or password');
}

/// 401 with `X-MFA-Required: true` — retry login once with [MfaRequired].
class MfaRequired extends VigilAuthException {
  MfaRequired() : super('MFA code required', statusCode: 401);
}

/// 423 — repeated failed logins; wait [retryAfter] before retrying.
class AccountLocked extends VigilAuthException {
  AccountLocked({required this.retryAfter})
      : super('Account locked due to repeated failed login attempts',
            statusCode: 423);

  /// Server-supplied `Retry-After`, in seconds. Null when the header is absent.
  final Duration? retryAfter;
}

/// A refresh attempt was refused — consumed single-use jti, blacklisted token,
/// invalid token, or lockout. The session is over: sign-in required.
class AuthRevoked extends VigilAuthException {
  AuthRevoked({required String reason, super.statusCode})
      : super('Session revoked: $reason');

  /// True when a [DioException] wraps an [AuthRevoked] — i.e. the 401 was
  /// escalated to sign-in-required rather than being a stale-data failure.
  static bool revoked(DioException error) => error.error is AuthRevoked;
}

/// Any other auth-endpoint failure (5xx, malformed response, unexpected
/// status). Carries the status so the UI can show a generic retryable error.
class UnexpectedAuthResponse extends VigilAuthException {
  UnexpectedAuthResponse(super.message, {super.statusCode});
}
