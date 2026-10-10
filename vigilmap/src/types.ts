/**
 * The MemoryGraphDocument contract, schema version 1.
 *
 * One shape, two producers, one consumer: the exporter and the sample
 * generator emit it; the app validates and renders it. The closed
 * vocabularies below mirror Vigil's episodic-memory contract —
 * `core/memory/recall_contract.py` owns the outcome enum and the entity-key
 * types, and `core/memory/entity_keys.py` owns how a key is minted
 * (defang, then case-fold, except `arn`/`aws_key`). Do not add a value here
 * without adding it there.
 *
 * Node ids are stable strings; entity nodes use the entity key itself so an
 * export joins back to Vigil exactly as recall does.
 */

export type NodeKind = "entity" | "sighting" | "verdict" | "gap" | "hunt" | "episode";

/** The entity types a key may name — mirror of `recall_contract.ENTITY_KEY_TYPES`. */
export type EntityType =
  | "ip"
  | "domain"
  | "host"
  | "url"
  | "email"
  | "hash"
  | "arn"
  | "aws_key"
  | "user"
  | "process"
  | "cve";

/** Closed set of hunt outcomes — mirror of `recall_contract.VerdictOutcome`. */
export type VerdictOutcome =
  | "proven"
  | "disproven"
  | "inconclusive"
  | "handed_off"
  | "false_positive";

/** How a sighting's window was established — mirror of `recall_contract.WindowSource`. */
export type SourceTier = "observed" | "asserted";

export type LinkRelation =
  | "sighting-of" // sighting → entity
  | "verdict-subject" // verdict → entity (1–3 per ADR 0016)
  | "verdict-source" // verdict → sighting (evidence)
  | "gap-subject" // gap → entity
  | "hunt-verdict" // hunt → verdict
  | "hunt-gap" // hunt → gap
  | "episode-entity"; // episode → entity

interface NodeBase {
  id: string;
  kind: NodeKind;
  label: string;
}

export type MemoryNode = NodeBase &
  (
    | { kind: "entity"; entityType: EntityType; entityKey: string }
    | {
        kind: "sighting";
        entityKey: string;
        observedFrom?: string;
        observedTo?: string;
        sourceTier?: SourceTier;
        investigationId?: string;
      }
    | {
        kind: "verdict";
        outcome: VerdictOutcome;
        statement: string;
        rationale?: string;
        investigationId?: string;
        concludedAt?: string;
        techniques?: string[];
        /** Producer's confidence in the conclusion, 0–1, when it recorded one. */
        confidence?: number;
      }
    | { kind: "gap"; disposition?: string; reason?: string; investigationId?: string }
    | { kind: "hunt"; objective?: string; startedAt?: string; endedAt?: string }
    | { kind: "episode"; summary?: string; occurredAt?: string }
  );

export interface MemoryLink {
  /** Id of the source node (the kind named first in `relation`). */
  source: string;
  /** Id of the target node. */
  target: string;
  relation: LinkRelation;
}

export interface MemoryGraphDocument {
  schemaVersion: 1;
  /** ISO-8601 instant the document was produced. */
  generatedAt: string;
  /** Provenance: `"sample"` or an export description. */
  source: string;
  nodes: MemoryNode[];
  links: MemoryLink[];
}

// ---------------------------------------------------------------------------
// Runtime mirrors of the closed vocabularies. The types above are erased at
// runtime; the validator and (later) the legend need the value sets.
// ---------------------------------------------------------------------------

export const NODE_KINDS: readonly NodeKind[] = [
  "entity",
  "sighting",
  "verdict",
  "gap",
  "hunt",
  "episode",
] as const;

export const ENTITY_TYPES: readonly EntityType[] = [
  "ip",
  "domain",
  "host",
  "url",
  "email",
  "hash",
  "arn",
  "aws_key",
  "user",
  "process",
  "cve",
] as const;

export const VERDICT_OUTCOMES: readonly VerdictOutcome[] = [
  "proven",
  "disproven",
  "inconclusive",
  "handed_off",
  "false_positive",
] as const;

export const LINK_RELATIONS: readonly LinkRelation[] = [
  "sighting-of",
  "verdict-subject",
  "verdict-source",
  "gap-subject",
  "hunt-verdict",
  "hunt-gap",
  "episode-entity",
] as const;
