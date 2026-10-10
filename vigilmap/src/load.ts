/**
 * Source resolution — three paths in, one funnel through the validator.
 *
 *   boot ├─ URL has ?data=  → fetch it, validate → OK | error state
 *        ├─ user drops a file → read it, validate → OK | error state
 *        └─ otherwise → load bundled /data/sample-memory.json
 *
 * A fetch failure and a validation failure land in the same error shape; an
 * empty-but-valid document loads fine and the app shows the empty note.
 * DOM and network are injected so the resolution logic is testable in node.
 */

import type { MemoryGraphDocument } from "./types";
import { validate } from "./validate";

/** Where the bundled sample lives, relative to the app root. */
export const SAMPLE_URL = "/data/sample-memory.json";

export type LoadOutcome =
  | { status: "loaded"; source: string; document: MemoryGraphDocument }
  | { status: "error"; source: string; message: string };

export interface ResolveDeps {
  /** Defaults to global fetch. */
  fetchImpl?: typeof fetch;
  /** Defaults to window.location.search when a window exists. */
  search?: string;
}

/** The `?data=` URL from a query string, or null when the parameter is absent. */
export function dataUrlFromSearch(search: string): string | null {
  const params = new URLSearchParams(search.startsWith("?") ? search.slice(1) : search);
  const data = params.get("data");
  return data === null || data.length === 0 ? null : data;
}

export async function resolveSource(deps: ResolveDeps = {}): Promise<LoadOutcome> {
  const fetchImpl = deps.fetchImpl ?? fetch;
  const search =
    deps.search ?? (typeof window !== "undefined" ? window.location.search : "");

  const dataParam = dataUrlFromSearch(search);
  const url = dataParam ?? SAMPLE_URL;
  const source = dataParam === null ? "bundled sample" : `?data=${dataParam}`;

  let response: Response;
  try {
    response = await fetchImpl(url);
  } catch (cause) {
    return {
      status: "error",
      source,
      message: `failed to fetch ${url}: ${describe(cause)}`,
    };
  }

  if (!response.ok) {
    return {
      status: "error",
      source,
      message: `failed to fetch ${url}: HTTP ${response.status} ${response.statusText}`,
    };
  }

  return parseAndValidate(await response.text(), source);
}

/**
 * A document dropped onto the app. `readFile` defaults to `Blob.text()`;
 * inject it where that is unavailable.
 */
export async function loadDroppedFile(
  file: File,
  readFile: (file: File) => Promise<string> = defaultReadFile,
): Promise<LoadOutcome> {
  const source = `dropped file "${file.name}"`;
  let text: string;
  try {
    text = await readFile(file);
  } catch (cause) {
    return {
      status: "error",
      source,
      message: `could not read ${file.name}: ${describe(cause)}`,
    };
  }
  return parseAndValidate(text, source);
}

function parseAndValidate(text: string, source: string): LoadOutcome {
  let candidate: unknown;
  try {
    candidate = JSON.parse(text);
  } catch (cause) {
    return {
      status: "error",
      source,
      message: `${source} is not valid JSON: ${describe(cause)}`,
    };
  }

  const result = validate(candidate);
  if (!result.ok) {
    return {
      status: "error",
      source,
      message: `document rejected: ${result.errors.join("; ")}`,
    };
  }
  return { status: "loaded", source, document: result.document };
}

async function defaultReadFile(file: File): Promise<string> {
  return file.text();
}

function describe(cause: unknown): string {
  return cause instanceof Error ? cause.message : String(cause);
}
