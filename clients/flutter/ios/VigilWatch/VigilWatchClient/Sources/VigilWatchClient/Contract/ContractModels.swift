import Foundation

/// Codable models for the five-endpoint watch surface, hand-written against
/// the frozen `/api/v1` contract (`core/api/v1/contract.snapshot.json`) —
/// the watch is a full citizen of that contract, not a display client.
///
/// Decode tests round-trip fixture payloads derived from the snapshot, so a
/// model that drifts from the frozen key set fails CI before the store does.

// MARK: - Needs you (GET /api/v1/approvals/needs-you)

/// One "needs a human" item — the exact `NeedsYouItem` schema of the frozen
/// contract: `kind`, `source_id`, `title`, `reason`, `created_at`,
/// `reversibility`, optional `case_id`. Note the frozen shape carries no
/// confidence field; the reason text is where the server states why the item
/// waits (e.g. "Confidence below the 0.90 auto-approve line").
public struct NeedsYouItem: Codable, Equatable, Identifiable, Sendable {
    public var kind: String
    public var sourceId: String
    public var title: String
    public var reason: String
    public var createdAt: String
    public var reversibility: String
    public var caseId: String?

    public var id: String { sourceId }

    public init(
        kind: String,
        sourceId: String,
        title: String,
        reason: String,
        createdAt: String,
        reversibility: String,
        caseId: String? = nil
    ) {
        self.kind = kind
        self.sourceId = sourceId
        self.title = title
        self.reason = reason
        self.createdAt = createdAt
        self.reversibility = reversibility
        self.caseId = caseId
    }

    enum CodingKeys: String, CodingKey {
        case kind
        case sourceId = "source_id"
        case title
        case reason
        case createdAt = "created_at"
        case reversibility
        case caseId = "case_id"
    }

    /// Whether the action can be undone after approval. Only the frozen
    /// strings `reversible` / `irreversible` are defined; anything else is
    /// treated as irreversible — the safe direction (a hold-to-confirm is
    /// demanded, never a plain tap).
    public var isReversible: Bool { reversibility == "reversible" }
}

/// The `NeedsYouResponse` wrapper. `count` is required by the contract;
/// `items` carries a server-side default, so it may be absent.
public struct NeedsYouResponse: Codable, Equatable, Sendable {
    public var count: Int
    public var items: [NeedsYouItem]

    public init(count: Int, items: [NeedsYouItem] = []) {
        self.count = count
        self.items = items
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        count = try container.decode(Int.self, forKey: .count)
        items = try container.decodeIfPresent([NeedsYouItem].self, forKey: .items) ?? []
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(count, forKey: .count)
        try container.encode(items, forKey: .items)
    }

    enum CodingKeys: String, CodingKey {
        case count
        case items
    }
}

// MARK: - Approval actions (POST …/approve, POST …/reject)

/// The frozen `PendingActionResponse` — every field optional ("the key set is
/// the promise"); open-JSON fields ride in `OpenJSONValue`. This is the
/// response body of both decision endpoints (via `ApprovalActionResult`) and
/// the shape the card updates to when the server reports a decision already
/// made (409/404 → the server is the source of record).
public struct PendingActionResponse: Codable, Equatable, Sendable {
    public var actionId: String?
    public var actionType: String?
    public var approvedAt: String?
    public var approvedBy: String?
    public var confidence: Double?
    public var createdAt: String?
    public var createdBy: String?
    public var detail: String?
    public var evidence: OpenJSONValue?
    public var executedAt: String?
    public var executionResult: OpenJSONValue?
    public var idempotencyKey: String?
    public var parameters: OpenJSONValue?
    public var reason: String?
    public var rejectionReason: String?
    public var requiresApproval: Bool?
    public var reversibility: String?
    public var status: String?
    public var target: OpenJSONValue?
    public var title: String?
    public var workflowPhaseId: String?
    public var workflowRunId: String?

    public init() {}

    enum CodingKeys: String, CodingKey {
        case actionId = "action_id"
        case actionType = "action_type"
        case approvedAt = "approved_at"
        case approvedBy = "approved_by"
        case confidence
        case createdAt = "created_at"
        case createdBy = "created_by"
        case detail = "description"
        case evidence
        case executedAt = "executed_at"
        case executionResult = "execution_result"
        case idempotencyKey = "idempotency_key"
        case parameters
        case reason
        case rejectionReason = "rejection_reason"
        case requiresApproval = "requires_approval"
        case reversibility
        case status
        case target
        case title
        case workflowPhaseId = "workflow_phase_id"
        case workflowRunId = "workflow_run_id"
    }

    public var isReversible: Bool { reversibility == "reversible" }
}

/// The `ApprovalActionResult` both decision endpoints answer with: the
/// updated action plus the workflow resume result (nil for rejections and
/// actions outside a run).
public struct ApprovalActionResult: Codable, Equatable, Sendable {
    public var action: PendingActionResponse
    public var resumeResult: OpenJSONValue?

    public init(action: PendingActionResponse, resumeResult: OpenJSONValue? = nil) {
        self.action = action
        self.resumeResult = resumeResult
    }

    enum CodingKeys: String, CodingKey {
        case action
        case resumeResult = "resume_result"
    }
}

// MARK: - Request bodies

/// `ApproveRequest` — the frozen body of `POST /api/v1/approvals/{id}/approve`.
/// The server records the signed-in user; the field is kept for the contract.
public struct ApproveRequest: Codable, Equatable, Sendable {
    public var approvedBy: String?

    public init(approvedBy: String? = nil) {
        self.approvedBy = approvedBy
    }

    enum CodingKeys: String, CodingKey {
        case approvedBy = "approved_by"
    }
}

/// `RejectRequest` — the frozen body of `POST /api/v1/approvals/{id}/reject`.
/// `reason` is mandatory: the watch never sends a reject without one.
public struct RejectRequest: Codable, Equatable, Sendable {
    public var reason: String
    public var rejectedBy: String?

    public init(reason: String, rejectedBy: String? = nil) {
        self.reason = reason
        self.rejectedBy = rejectedBy
    }

    enum CodingKeys: String, CodingKey {
        case reason
        case rejectedBy = "rejected_by"
    }
}

// MARK: - Auth refresh (POST /api/auth/refresh)

/// The body `/api/auth/refresh` expects. The endpoint sits outside the frozen
/// snapshot (console surface, stable in practice) — the same accepted
/// exception the phone's hand-written `AuthApi` makes.
public struct RefreshRequestBody: Codable, Equatable, Sendable {
    public var refreshToken: String

    public init(refreshToken: String) {
        self.refreshToken = refreshToken
    }

    enum CodingKeys: String, CodingKey {
        case refreshToken = "refresh_token"
    }
}

/// The token-issuing responses of `/api/auth/login` and `/api/auth/refresh`:
/// `{access_token, refresh_token, user, token_type}`. Only the token fields
/// are consumed; the user dict is tolerated and ignored.
public struct AuthTokenResponseBody: Codable, Equatable, Sendable {
    public var accessToken: String
    public var refreshToken: String

    public init(accessToken: String, refreshToken: String) {
        self.accessToken = accessToken
        self.refreshToken = refreshToken
    }

    // Explicit Codable: synthesis is refused while CodingKeys carries wire
    // keys (`user`, `token_type`) that map to no stored property. Extra
    // keys in a response body are ignored by JSONDecoder — covered by the
    // fixture decode test.
    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        guard let access = try container.decodeIfPresent(String.self, forKey: .accessToken),
              !access.isEmpty
        else {
            throw DecodingError.keyNotFound(
                CodingKeys.accessToken,
                .init(codingPath: decoder.codingPath, debugDescription: "missing access_token")
            )
        }
        guard let refresh = try container.decodeIfPresent(String.self, forKey: .refreshToken),
              !refresh.isEmpty
        else {
            throw DecodingError.keyNotFound(
                CodingKeys.refreshToken,
                .init(codingPath: decoder.codingPath, debugDescription: "missing refresh_token")
            )
        }
        accessToken = access
        refreshToken = refresh
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(accessToken, forKey: .accessToken)
        try container.encode(refreshToken, forKey: .refreshToken)
    }

    enum CodingKeys: String, CodingKey {
        case accessToken = "access_token"
        case refreshToken = "refresh_token"
    }
}
