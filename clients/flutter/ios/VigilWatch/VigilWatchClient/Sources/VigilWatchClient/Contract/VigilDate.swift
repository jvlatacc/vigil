import Foundation

/// Lenient parsing of the timestamp strings the frozen contract carries in
/// `created_at` (and `PendingActionResponse`'s date fields). The server
/// serializes pydantic datetimes as ISO-8601, but with or without fractional
/// seconds and with or without an offset — naive UTC datetimes included.
public enum VigilDate {
    /// Tries, in order: fractional seconds + offset, plain + offset, then
    /// naive UTC datetimes (no offset). `Z` is handled natively by the
    /// ISO8601 parser.
    public static func parse(_ raw: String) -> Date? {
        let trimmed = raw.trimmingCharacters(in: .whitespaces)
        for parser in Self.parsers where !trimmed.isEmpty {
            if let date = parser(trimmed) {
                return date
            }
        }
        return nil
    }

    // Linux corelibs-foundation's ISO8601DateFormatter has no
    // `formatString` — use `formatOptions` plus a DateFormatter for the
    // offset-less forms the server emits for naive datetimes.
    private static let parsers: [(String) -> Date?] = {
        let withOffset = ISO8601DateFormatter()
        withOffset.formatOptions = [.withInternetDateTime]
        let withFractionAndOffset = ISO8601DateFormatter()
        withFractionAndOffset.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let naive = DateFormatter()
        naive.locale = Locale(identifier: "en_US_POSIX")
        naive.timeZone = TimeZone(identifier: "UTC")
        naive.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
        let naiveFraction = DateFormatter()
        naiveFraction.locale = Locale(identifier: "en_US_POSIX")
        naiveFraction.timeZone = TimeZone(identifier: "UTC")
        naiveFraction.dateFormat = "yyyy-MM-dd'T'HH:mm:ss.SSSSSS"
        return [
            withOffset.date(from:),
            withFractionAndOffset.date(from:),
            naiveFraction.date(from:),
            naive.date(from:),
        ]
    }()
}

public extension NeedsYouItem {
    /// The parsed `created_at`, for age labels ("Checked 4 min ago") and
    /// oldest-first ordering. Nil when the string does not parse — the raw
    /// value is still displayed verbatim in that case.
    var createdAtDate: Date? { VigilDate.parse(createdAt) }
}

public extension PendingActionResponse {
    var approvedAtDate: Date? { approvedAt.flatMap(VigilDate.parse) }
}
