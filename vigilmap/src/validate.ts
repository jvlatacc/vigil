/**
 * Load-time validation of a candidate MemoryGraphDocument.
 *
 * A document that breaks the contract is rejected with named errors — naming
 * the offending element — never half-rendered. The rejection cases are the
 * ones the spec names: wrong schemaVersion, unknown kind / entityType /
 * outcome / relation, dangling link endpoints, duplicate node ids, and an
 * entity node whose entityKey does not start with its entityType.
 */

import type { LinkRelation, MemoryGraphDocument, NodeKind } from "./types";
import { ENTITY_TYPES, NODE_KINDS, VERDICT_OUTCOMES, LINK_RELATIONS } from "./types";
import { LINK_TABLE } from "./graph";

export interface ValidateOk {
  ok: true;
  document: MemoryGraphDocument;
}

export interface ValidateError {
  ok: false;
  /** Every named violation found — one line each, ready for the error panel. */
  errors: string[];
}

export type ValidationResult = ValidateOk | ValidateError;

export function validate(candidate: unknown): ValidationResult {
  const errors: string[] = [];

  if (typeof candidate !== "object" || candidate === null || Array.isArray(candidate)) {
    return {
      ok: false,
      errors: ["document must be a JSON object"],
    };
  }

  const doc = candidate as Record<string, unknown>;

  // schemaVersion: forward compatibility is explicit, not accidental — say
  // what was found, not just that it is wrong.
  if (typeof doc.schemaVersion !== "number") {
    errors.push(
      `schemaVersion must be the number 1, found ${JSON.stringify(doc.schemaVersion) ?? "absent"}`,
    );
  } else if (doc.schemaVersion !== 1) {
    errors.push(`unsupported schemaVersion: expected 1, found ${doc.schemaVersion}`);
  }

  if (typeof doc.generatedAt !== "string" || doc.generatedAt.length === 0) {
    errors.push("generatedAt must be a non-empty ISO-8601 string");
  }

  if (typeof doc.source !== "string" || doc.source.length === 0) {
    errors.push("source must be a non-empty provenance string");
  }

  if (!Array.isArray(doc.nodes)) {
    errors.push("nodes must be an array");
  }

  if (!Array.isArray(doc.links)) {
    errors.push("links must be an array");
  }

  const nodeIds = new Set<string>();
  const nodeKinds = new Map<string, NodeKind>();

  if (Array.isArray(doc.nodes)) {
    for (const node of doc.nodes) {
      errors.push(...validateNode(node));
      if (isNodeWithId(node)) {
        if (nodeIds.has(node.id)) {
          errors.push(`duplicate node id: "${node.id}"`);
        }
        nodeIds.add(node.id);
      }
      if (isNodeWithKnownKind(node)) {
        nodeKinds.set(node.id, node.kind);
      }
    }
  }

  if (Array.isArray(doc.links)) {
    for (const link of doc.links) {
      errors.push(...validateLink(link, nodeIds, nodeKinds));
    }
  }

  if (errors.length > 0) {
    return { ok: false, errors };
  }

  // The vocabulary and cross-reference checks above are exactly the contract;
  // a document that passes them is renderable as typed.
  return { ok: true, document: doc as unknown as MemoryGraphDocument };
}

function isNodeWithId(node: unknown): node is { id: string } {
  return typeof node === "object" && node !== null && typeof (node as { id?: unknown }).id === "string";
}

function isNodeWithKnownKind(node: unknown): node is { id: string; kind: NodeKind } {
  return (
    isNodeWithId(node) &&
    typeof (node as { kind?: unknown }).kind === "string" &&
    NODE_KINDS.includes((node as { kind?: unknown }).kind as NodeKind)
  );
}

function validateNode(node: unknown): string[] {
  const errors: string[] = [];

  if (typeof node !== "object" || node === null) {
    return ["node must be a JSON object"];
  }

  const n = node as Record<string, unknown>;
  const id = typeof n.id === "string" ? n.id : JSON.stringify(n.id ?? null);
  const where = `node "${id}"`;

  if (typeof n.id !== "string" || n.id.length === 0) {
    errors.push(`node id must be a non-empty string`);
  }

  if (typeof n.label !== "string" || n.label.length === 0) {
    errors.push(`${where}: label must be a non-empty string`);
  }

  if (typeof n.kind !== "string" || !isNodeKind(n.kind)) {
    errors.push(
      `${where}: unknown kind ${JSON.stringify(n.kind ?? null)} — expected one of ${NODE_KINDS.join(", ")}`,
    );
    return errors; // kind-specific checks below assume a known kind
  }

  switch (n.kind) {
    case "entity": {
      if (typeof n.entityType !== "string" || !isEntityType(n.entityType)) {
        errors.push(
          `${where}: unknown entityType ${JSON.stringify(n.entityType ?? null)} — expected one of ${ENTITY_TYPES.join(", ")}`,
        );
      } else if (typeof n.entityKey !== "string" || n.entityKey.length === 0) {
        errors.push(`${where}: entityKey must be a non-empty string`);
      } else if (!n.entityKey.startsWith(`${n.entityType}:`)) {
        // Cheap catch for a mis-minted key: keys are `type:value` (defanged,
        // case-folded except arn/aws_key), so the prefix is derivable.
        errors.push(
          `${where}: entityKey "${n.entityKey}" does not start with its entityType "${n.entityType}:" — key was not minted by the entity-key rule`,
        );
      }
      break;
    }
    case "sighting": {
      if (typeof n.entityKey !== "string" || n.entityKey.length === 0) {
        errors.push(`${where}: entityKey must be a non-empty string`);
      }
      if (n.sourceTier !== undefined && n.sourceTier !== "observed" && n.sourceTier !== "asserted") {
        errors.push(`${where}: unknown sourceTier ${JSON.stringify(n.sourceTier)} — expected "observed" or "asserted"`);
      }
      break;
    }
    case "verdict": {
      if (typeof n.outcome !== "string" || !isVerdictOutcome(n.outcome)) {
        errors.push(
          `${where}: unknown outcome ${JSON.stringify(n.outcome ?? null)} — expected one of ${VERDICT_OUTCOMES.join(", ")}`,
        );
      }
      if (typeof n.statement !== "string" || n.statement.length === 0) {
        errors.push(`${where}: statement must be a non-empty string`);
      }
      if (n.confidence !== undefined && (typeof n.confidence !== "number" || n.confidence < 0 || n.confidence > 1)) {
        errors.push(`${where}: confidence must be a number between 0 and 1`);
      }
      if (n.techniques !== undefined) {
        if (!Array.isArray(n.techniques) || n.techniques.some((t) => typeof t !== "string")) {
          errors.push(`${where}: techniques must be an array of strings`);
        }
      }
      break;
    }
    default:
      // gap / hunt / episode carry no required payload beyond the base fields.
      break;
  }

  return errors;
}

function validateLink(
  link: unknown,
  nodeIds: Set<string>,
  nodeKinds: Map<string, NodeKind>,
): string[] {
  if (typeof link !== "object" || link === null) {
    return ["link must be a JSON object"];
  }

  const l = link as Record<string, unknown>;
  const errors: string[] = [];

  const relation: LinkRelation | null =
    typeof l.relation === "string" && isLinkRelation(l.relation) ? (l.relation as LinkRelation) : null;
  if (relation === null) {
    errors.push(
      `link: unknown relation ${JSON.stringify(l.relation ?? null)} — expected one of ${LINK_RELATIONS.join(", ")}`,
    );
  }

  if (typeof l.source !== "string" || l.source.length === 0) {
    errors.push(`link: source must be a non-empty node id`);
  } else if (!nodeIds.has(l.source)) {
    errors.push(`dangling link: source "${l.source}" matches no node id`);
  }

  if (typeof l.target !== "string" || l.target.length === 0) {
    errors.push(`link: target must be a non-empty node id`);
  } else if (!nodeIds.has(l.target)) {
    errors.push(`dangling link: target "${l.target}" matches no node id`);
  }

  // The relation table (spec "Which links are legal"): a known relation between
  // known-kind endpoints must match the source→target kind pair, or a producer
  // bug is surfacing as such.
  if (relation !== null && typeof l.source === "string" && typeof l.target === "string") {
    const table = LINK_TABLE[relation];
    const sourceKind = nodeKinds.get(l.source);
    const targetKind = nodeKinds.get(l.target);
    if (sourceKind !== undefined && targetKind !== undefined) {
      if (sourceKind !== table.source || targetKind !== table.target) {
        errors.push(
          `link ${l.source}→${l.target}: relation ${l.relation} requires ` +
            `${table.source}→${table.target}, found ${sourceKind}→${targetKind}`,
        );
      }
    }
  }

  return errors;
}

function isNodeKind(value: string): boolean {
  return NODE_KINDS.includes(value as (typeof NODE_KINDS)[number]);
}

function isEntityType(value: string): boolean {
  return ENTITY_TYPES.includes(value as (typeof ENTITY_TYPES)[number]);
}

function isVerdictOutcome(value: string): boolean {
  return VERDICT_OUTCOMES.includes(value as (typeof VERDICT_OUTCOMES)[number]);
}

function isLinkRelation(value: string): boolean {
  return LINK_RELATIONS.includes(value as (typeof LINK_RELATIONS)[number]);
}
