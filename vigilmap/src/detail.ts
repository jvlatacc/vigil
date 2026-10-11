/**
 * Node → detail-panel view model, per kind, exactly the fields the spec's
 * interaction contract names. Unknown payload extras become a collapsible
 * "raw" section (or are absent) — they never crash the panel.
 */

import type { LinkRelation, MemoryGraphDocument, MemoryNode, NodeKind } from "./types";

export type Tone = "neutral" | "good" | "warn" | "bad" | "info";

export interface DetailField {
  label: string;
  value: string;
  /** Render in monospace — keys, ids, techniques, timestamps. */
  mono?: boolean;
  tone?: Tone;
}

export interface DetailViewModel {
  id: string;
  kind: NodeKind;
  title: string;
  badge?: { text: string; tone: Tone };
  fields: DetailField[];
  /** JSON of fields outside the kind's contract, for the collapsible raw section. */
  raw?: string;
}

const OUTCOME_TONES: Record<string, Tone> = {
  proven: "good",
  disproven: "bad",
  inconclusive: "warn",
  handed_off: "info",
  false_positive: "bad",
};

const KNOWN_FIELDS: Record<NodeKind, ReadonlySet<string>> = {
  entity: new Set(["id", "kind", "label", "entityType", "entityKey"]),
  sighting: new Set([
    "id",
    "kind",
    "label",
    "entityKey",
    "observedFrom",
    "observedTo",
    "sourceTier",
    "investigationId",
  ]),
  verdict: new Set([
    "id",
    "kind",
    "label",
    "outcome",
    "statement",
    "rationale",
    "investigationId",
    "concludedAt",
    "techniques",
  ]),
  gap: new Set(["id", "kind", "label", "disposition", "reason", "investigationId"]),
  hunt: new Set(["id", "kind", "label", "objective", "startedAt", "endedAt"]),
  episode: new Set(["id", "kind", "label", "summary", "occurredAt"]),
};

export function rawExtras(node: MemoryNode): string | undefined {
  const known = KNOWN_FIELDS[node.kind];
  const extras: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(node)) {
    if (!known.has(key)) extras[key] = value;
  }
  return Object.keys(extras).length ? JSON.stringify(extras, null, 2) : undefined;
}

function idsBySource(doc: MemoryGraphDocument, relation: LinkRelation): Map<string, string[]> {
  const map = new Map<string, string[]>();
  for (const link of doc.links) {
    if (link.relation !== relation) continue;
    const list = map.get(link.source) ?? [];
    list.push(link.target);
    map.set(link.source, list);
  }
  return map;
}

function idsByTarget(doc: MemoryGraphDocument, relation: LinkRelation): Map<string, string[]> {
  const map = new Map<string, string[]>();
  for (const link of doc.links) {
    if (link.relation !== relation) continue;
    const list = map.get(link.target) ?? [];
    list.push(link.source);
    map.set(link.target, list);
  }
  return map;
}

function nodeById(doc: MemoryGraphDocument): Map<string, MemoryNode> {
  return new Map(doc.nodes.map((n) => [n.id, n]));
}

/** Resolve ids to labels; a dangling id falls back to the raw id, never a crash. */
function resolveLabels(doc: MemoryGraphDocument, ids: readonly string[]): string[] {
  const byId = nodeById(doc);
  return ids.map((id) => byId.get(id)?.label ?? id);
}

/** Resolve ids to entity keys, in link order. */
function resolveEntityKeys(doc: MemoryGraphDocument, ids: readonly string[]): string[] {
  const byId = nodeById(doc);
  return ids
    .map((id) => byId.get(id))
    .filter((n): n is Extract<MemoryNode, { kind: "entity" }> => n?.kind === "entity")
    .map((n) => n.entityKey);
}

function field(label: string, value: string | undefined, mono = false): DetailField | null {
  if (value === undefined || value === "") return null;
  return { label, value, mono };
}

function windowValue(from: string | undefined, to: string | undefined): string | undefined {
  if (from && to) return `${from} → ${to}`;
  return from ?? to;
}

function joined(values: string[], none: string): string {
  return values.length ? values.join(", ") : none;
}

export function detailViewModel(node: MemoryNode, doc: MemoryGraphDocument): DetailViewModel {
  const fields: DetailField[] = [];
  let badge: DetailViewModel["badge"];
  const push = (f: DetailField | null) => {
    if (f) fields.push(f);
  };

  switch (node.kind) {
    case "entity": {
      const sightingCount = (idsByTarget(doc, "sighting-of").get(node.id) ?? []).length;
      const verdicts = resolveLabels(doc, idsByTarget(doc, "verdict-subject").get(node.id) ?? []);
      badge = { text: node.entityType, tone: "info" };
      push(field("entity key", node.entityKey, true));
      push(field("type", node.entityType));
      push(field("sightings", String(sightingCount)));
      push(field("linked verdicts", joined(verdicts, "none")));
      break;
    }
    case "sighting": {
      const entities = resolveEntityKeys(doc, idsBySource(doc, "sighting-of").get(node.id) ?? []);
      push(field("entity", joined(entities, "unlinked"), true));
      push(field("window", windowValue(node.observedFrom, node.observedTo), true));
      push(field("source tier", node.sourceTier));
      push(field("investigation", node.investigationId, true));
      break;
    }
    case "verdict": {
      const subjects = resolveEntityKeys(doc, idsBySource(doc, "verdict-subject").get(node.id) ?? []);
      const sources = (idsBySource(doc, "verdict-source").get(node.id) ?? []).length;
      const hunts = resolveLabels(doc, idsByTarget(doc, "hunt-verdict").get(node.id) ?? []);
      badge = { text: node.outcome, tone: OUTCOME_TONES[node.outcome] ?? "neutral" };
      push(field("statement", node.statement));
      if (node.confidence !== undefined) {
        push(field("confidence", node.confidence.toFixed(2)));
      }
      push(field("rationale", node.rationale));
      push(field("subjects", joined(subjects, "none"), true));
      if (node.techniques?.length) {
        push(field("techniques", node.techniques.join(", "), true));
      }
      push(field("sources", `${sources} source${sources === 1 ? "" : "s"}`));
      push(field("hunt", joined(hunts, "unlinked")));
      push(field("concluded", node.concludedAt, true));
      break;
    }
    case "gap": {
      const subjects = resolveEntityKeys(doc, idsBySource(doc, "gap-subject").get(node.id) ?? []);
      const hunts = resolveLabels(doc, idsByTarget(doc, "hunt-gap").get(node.id) ?? []);
      push(field("disposition", node.disposition));
      push(field("reason", node.reason));
      push(field("subjects", joined(subjects, "none"), true));
      push(field("hunt", joined(hunts, "unlinked")));
      break;
    }
    case "hunt": {
      const verdicts = resolveLabels(doc, idsBySource(doc, "hunt-verdict").get(node.id) ?? []);
      const gaps = resolveLabels(doc, idsBySource(doc, "hunt-gap").get(node.id) ?? []);
      push(field("objective", node.objective));
      push(field("started", node.startedAt, true));
      push(field("ended", node.endedAt, true));
      push(field("verdicts", joined(verdicts, "none")));
      push(field("gaps", joined(gaps, "none")));
      break;
    }
    case "episode": {
      const entities = resolveEntityKeys(doc, idsBySource(doc, "episode-entity").get(node.id) ?? []);
      push(field("summary", node.summary));
      push(field("occurred", node.occurredAt, true));
      push(field("entities", joined(entities, "none"), true));
      break;
    }
  }

  return { id: node.id, kind: node.kind, title: node.label, badge, fields, raw: rawExtras(node) };
}
