/**
 * App wiring — the one screen: scene, filters, legend, detail panel, keyboard.
 *
 * Interaction contract (spec): click selects and opens the detail panel;
 * hovering highlights the direct neighborhood and dims the rest; filters hide
 * rather than delete and un-checking restores; Esc clears selection; `/`
 * focuses search; search jumps to and selects the matching entity; the camera
 * is free-orbit with recenter-on-selection; auto-rotate defaults off and
 * honors prefers-reduced-motion.
 *
 * DOM model: the ready-state shell (grid, topbar, filter panel, stage, detail
 * skeleton) belongs to the DOCUMENT — it is rendered once per document and
 * never rebuilt on state changes, because the WebGL canvas lives inside it
 * and re-templating would orphan the scene. Selection/filter changes update
 * the panels in place; the scene rebuilds its data (same canvas) when the
 * visible set changes. All state derivation lives in the framework-free
 * modules (graph / filters / detail / store); this file is glue.
 */

import ForceGraph3D from "3d-force-graph";
import SpriteText from "three-spritetext";
import { Group, Mesh, MeshLambertMaterial, SphereGeometry, type Object3D } from "three";

import {
  NODE_KIND_COLORS,
  buildGraph,
  capVisibleSet,
  neighborhood,
  type BuiltGraph,
  type GraphNode,
} from "./graph";
import { applyFilters, findMatches } from "./filters";
import { detailViewModel } from "./detail";
import {
  countByKind,
  createStore,
  deriveAppState,
  noFilters,
  resolveSelection,
  type ExplorerStore,
  type Filters,
} from "./store";
import { loadDroppedFile, resolveSource } from "./load";
import {
  ENTITY_TYPES,
  NODE_KINDS,
  VERDICT_OUTCOMES,
  type MemoryGraphDocument,
  type MemoryLink,
  type MemoryNode,
  type NodeKind,
} from "./types";

/** Above this many visible nodes, the initial set is capped (sightings first). */
const INITIAL_VISIBLE_CAP = 1500;

/** Poll cadence for the zoom proxy (this 3d-force-graph version exposes no zoom event). */
const ZOOM_POLL_MS = 250;
/** Sighting labels appear once the camera has zoomed in to this fraction of its widest view. */
const ZOOM_LABEL_FRACTION = 0.7;

const DIM_COLOR = "#8b949e";
const LINK_COLOR = "rgba(230,237,243,0.18)";
const WEBGL_ERROR =
  "WebGL is required for the 3D view, and this browser could not create a WebGL context. " +
  "The explorer cannot render the graph without it.";

const DETAIL_EMPTY = `<p class="muted">click a node to inspect it — <kbd>Esc</kbd> clears.</p>`;

/** Render state 3d-force-graph lets us hang off node data (positions after layout). */
type SceneNode = GraphNode & {
  __mat: MeshLambertMaterial;
  x?: number;
  y?: number;
  z?: number;
};

interface SceneHandle {
  rebuild(nodes: readonly MemoryNode[], links: readonly MemoryLink[]): void;
  recenterOn(node: MemoryNode): void;
  setAutoRotate(on: boolean): void;
}

export function mountApp(root: HTMLElement): void {
  const store = createStore();

  // Read-only debug affordance for browser-side diagnosis (DevRel demos included).
  (window as unknown as { __vigilmap?: { getState: () => unknown } }).__vigilmap = {
    getState: () => store.get(),
  };

  let scene: SceneHandle | null = null;
  /** The cap applies to the initial visible set only — user filter actions are explicit. */
  let capApplied = false;
  /** Memo of the last (document, filters) pair pushed to the scene — skips churn. */
  let paintedKey = "";

  const resetForNewDocument = (): void => {
    capApplied = false;
    scene = null; // the old scene's stage is destroyed with the document shell
  };

  const applyOutcome = (outcome: Awaited<ReturnType<typeof resolveSource>>): void => {
    if (outcome.status === "loaded") {
      resetForNewDocument();
      store.set({
        document: outcome.document,
        selectedNodeId: null,
        filters: noFilters(),
        error: null,
      });
    } else {
      store.set({ error: outcome.message });
    }
  };

  // -- render loop ------------------------------------------------------------

  const render = (): void => {
    const state = store.get();
    const appState = deriveAppState(state);

    if (appState === "loading") {
      root.innerHTML = shell(`
        <main class="layout" data-state="loading">
          <section class="status-card" aria-live="polite">
            <h1>VigilMap</h1>
            <p class="status-note">loading memory…</p>
          </section>
        </main>`);
      return;
    }

    if (appState === "error") {
      root.innerHTML = shell(`
        <main class="layout" data-state="error">
          <section class="status-card" role="alert">
            <h1>Document rejected</h1>
            <p class="error-message">${escapeHtml(state.error ?? "unknown error")}</p>
            <p><button type="button" data-action="load-sample">Load the bundled sample</button></p>
            <p class="muted">You can also drop a memory document anywhere on this page.</p>
          </section>
        </main>`);
      root.querySelector("[data-action=load-sample]")?.addEventListener("click", () => {
        void resolveSource({ search: "" }).then(applyOutcome);
      });
      return;
    }

    const doc = state.document;
    if (doc === null) return; // unreachable behind deriveAppState

    if (appState === "empty") {
      root.innerHTML = shell(`
        <main class="layout" data-state="empty">
          <section class="status-card" role="status">
            <h1>VigilMap</h1>
            <p class="status-note">this memory has no rows.</p>
            <p class="muted">Drop a different document, or check the exporter's connection settings.</p>
          </section>
        </main>`);
      return;
    }

    renderReady(root, store, doc, {
      getScene: () => scene,
      setScene: (handle) => {
        scene = handle;
      },
      capApplied,
      markCapped: () => {
        capApplied = true;
      },
      paintedKey,
      markPainted: (key) => {
        paintedKey = key;
      },
    });
  };

  store.subscribe(render);

  // -- boot -------------------------------------------------------------------

  render(); // loading state
  void resolveSource().then(applyOutcome);

  // -- drag & drop: a source-resolution path through the same validator -------

  root.addEventListener("dragover", (event) => {
    event.preventDefault();
    root.classList.add("dragging");
  });
  root.addEventListener("dragleave", () => root.classList.remove("dragging"));
  root.addEventListener("drop", (event) => {
    event.preventDefault();
    root.classList.remove("dragging");
    const file = event.dataTransfer?.files?.[0];
    if (!file) return;
    void loadDroppedFile(file).then(applyOutcome);
  });

  // -- keyboard: Esc clears selection, "/" focuses search ----------------------

  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      store.set({ selectedNodeId: null });
      (document.activeElement as HTMLElement | null)?.blur();
    } else if (event.key === "/") {
      const target = event.target as HTMLElement | null;
      const typing = target !== null && /^(input|textarea|select)$/i.test(target.tagName);
      if (typing) return;
      event.preventDefault();
      root.querySelector<HTMLInputElement>("#search")?.focus();
    }
  });
}

// ---------------------------------------------------------------------------
// Ready state
// ---------------------------------------------------------------------------

function renderReady(
  root: HTMLElement,
  store: ExplorerStore,
  doc: MemoryGraphDocument,
  ctx: {
    getScene: () => SceneHandle | null;
    setScene: (handle: SceneHandle) => void;
    capApplied: boolean;
    markCapped: () => void;
    paintedKey: string;
    markPainted: (key: string) => void;
  },
): void {
  const state = store.get();
  const filters = state.filters;
  const filtered = applyFilters(doc, filters);

  // A selected node the user cannot see is a state lie — selection clears.
  const selection = resolveSelection(state.selectedNodeId, filtered.nodes);
  if (selection !== state.selectedNodeId) {
    store.set({ selectedNodeId: selection });
    return; // the store event re-renders
  }
  const selected = selection === null ? null : doc.nodes.find((n) => n.id === selection) ?? null;

  // Initial visible-set cap for large exports — never a silent hairball.
  let visibleNodes = filtered.nodes;
  let visibleLinks = filtered.links;
  let trimmedNote = "";
  if (!ctx.capApplied && filtered.nodes.length > INITIAL_VISIBLE_CAP) {
    const capped = capVisibleSet(filtered.nodes, filtered.links, INITIAL_VISIBLE_CAP);
    visibleNodes = capped.nodes;
    visibleLinks = capped.links;
    const sightingsTrimmed =
      filtered.nodes.filter((n) => n.kind === "sighting").length -
      capped.nodes.filter((n) => n.kind === "sighting").length;
    trimmedNote =
      `showing ${capped.nodes.length} of ${filtered.nodes.length} — trimmed ${capped.trimmed}` +
      ` (${sightingsTrimmed} sightings); re-filter to load the rest`;
    ctx.markCapped();
  }

  const key = paintKey(doc, filters);
  const totalByKind = countByKind(doc);
  const visibleByKind = countByKind({ ...doc, nodes: filtered.nodes, links: filtered.links });

  // The shell belongs to the document — rebuild only on document identity;
  // the live canvas lives inside it. Panel contents update in place below.
  const docKey = `${doc.source}|${doc.generatedAt}`;
  const shellEl = root.querySelector<HTMLElement>("[data-state=ready]");
  if (shellEl === null || shellEl.dataset.doc !== docKey) {
    root.innerHTML = readyShellHtml(doc, visibleNodes.length, trimmedNote);
    wireFilters(root, store);
    wireSearch(root, store, doc, ctx.getScene);
    wireTopbar(root, store, ctx.getScene);
  }

  // Scene: create once (with data), rebuild in place when the visible set changes.
  const scene = ctx.getScene();
  if (scene === null) {
    const webglError = detectWebglError();
    if (webglError !== null) {
      store.set({ error: webglError });
      return;
    }
    const stage = root.querySelector<HTMLElement>("#stage");
    if (stage === null) return; // unreachable — the shell above defines it
    ctx.setScene(createScene(stage, store, visibleNodes, visibleLinks));
    ctx.markPainted(key);
  } else if (key !== ctx.paintedKey) {
    scene.rebuild(visibleNodes, visibleLinks);
    ctx.markPainted(key);
  }

  updateReadyPanels(root, doc, selected, visibleByKind, totalByKind, visibleNodes.length, trimmedNote);
}

/**
 * The ready-state document shell: grid, topbar, filter panel, stage, detail
 * skeleton. Rendered once per document; counts and the detail panel are
 * filled by updateReadyPanels so re-renders never touch the canvas.
 */
function readyShellHtml(doc: MemoryGraphDocument, showing: number, trimmedNote: string): string {
  return shell(`
    <main class="layout" data-state="ready" data-doc="${escapeHtml(`${doc.source}|${doc.generatedAt}`)}">
      <header class="topbar">
        <h1>VigilMap</h1>
        <span class="status-note">
          ${doc.nodes.length} nodes · ${doc.links.length} links
          · source: <code>${escapeHtml(doc.source)}</code>
          · showing <span data-showing>${showing}</span>
        </span>
        <span class="trim-note" data-trim-note>${escapeHtml(trimmedNote)}</span>
        <span class="topbar-actions">
          <label class="toggle" title="${prefersReducedMotion() ? "prefers-reduced-motion is set — rotation only starts on your explicit choice" : "slowly orbit the scene"}">
            <input type="checkbox" id="auto-rotate" />
            auto-rotate
          </label>
          <button type="button" data-action="recenter" disabled>recenter</button>
        </span>
      </header>
      <aside class="panel filters" aria-label="filters">
        <label class="search-row">
          <span class="muted">search entity key <kbd>/</kbd></span>
          <input id="search" type="search" placeholder="ip:10.0.0.1…" autocomplete="off" aria-describedby="search-hint" />
          <span class="muted" id="search-hint" role="status"></span>
        </label>
        <fieldset>
          <legend>kinds</legend>
          ${NODE_KINDS.map((kind) => checkboxRow(`kind-${kind}`, kind, true, kind)).join("")}
        </fieldset>
        <fieldset>
          <legend>outcomes</legend>
          ${VERDICT_OUTCOMES.map((o) => checkboxRow(`outcome-${o}`, o, true)).join("")}
        </fieldset>
        <fieldset>
          <legend>entity types</legend>
          ${ENTITY_TYPES.map((t) => checkboxRow(`etype-${t}`, t, true)).join("")}
        </fieldset>
        <fieldset>
          <legend>time window</legend>
          <label class="time-row">from <input type="datetime-local" id="time-from" aria-label="window start" /></label>
          <label class="time-row">to <input type="datetime-local" id="time-to" aria-label="window end" /></label>
          <button type="button" data-action="clear-window">clear window</button>
        </fieldset>
      </aside>
      <section class="stage-wrap" aria-label="memory graph">
        <section class="stage" id="stage"></section>
        <div class="legend" aria-hidden="true">
          ${NODE_KINDS.map(
            (kind) => `<span class="legend-item"><i style="background:${NODE_KIND_COLORS[kind]}"></i>${kind}</span>`,
          ).join("")}
        </div>
      </section>
      <aside class="panel detail" aria-label="selection details" data-panel="detail">${DETAIL_EMPTY}</aside>
    </main>`);
}

/** In-place panel refresh: counts, trim note, recenter state, detail panel. */
function updateReadyPanels(
  root: HTMLElement,
  doc: MemoryGraphDocument,
  selected: MemoryNode | null,
  visibleByKind: Record<NodeKind, number>,
  totalByKind: Record<NodeKind, number>,
  showing: number,
  trimmedNote: string,
): void {
  const setText = (selector: string, text: string): void => {
    const el = root.querySelector(selector);
    if (el !== null) el.textContent = text;
  };
  setText("[data-showing]", String(showing));
  setText("[data-trim-note]", trimmedNote);
  for (const kind of NODE_KINDS) {
    setText(`[data-count="${kind}"]`, `${visibleByKind[kind]}/${totalByKind[kind]}`);
  }
  const recenter = root.querySelector<HTMLButtonElement>("[data-action=recenter]");
  if (recenter !== null) recenter.disabled = selected === null;
  const detail = root.querySelector<HTMLElement>("[data-panel=detail]");
  if (detail !== null) {
    detail.innerHTML = selected === null ? DETAIL_EMPTY : detailHtml(selected, doc);
  }
}

// ---------------------------------------------------------------------------
// Scene construction
// ---------------------------------------------------------------------------

function createScene(
  stage: HTMLElement,
  store: ExplorerStore,
  nodes: readonly MemoryNode[],
  links: readonly MemoryLink[],
): SceneHandle {
  const sightingLabels = new Map<string, SpriteText>();
  let handleRef: SceneHandle | null = null;
  let widestCameraDist = 1;
  let built: BuiltGraph = buildGraph(nodes, links);

  const graph = new ForceGraph3D(stage)
    .width(stage.clientWidth)
    .height(stage.clientHeight)
    .backgroundColor("rgba(0,0,0,0)")
    .nodeLabel((n: object) => String((n as GraphNode).label))
    .nodeThreeObject((n: object) => nodeObject(n as GraphNode))
    .nodeThreeObjectExtend(false)
    .linkColor(() => LINK_COLOR)
    .linkWidth(() => 1)
    .onNodeClick((n: object) => {
      const gn = n as GraphNode;
      const alreadySelected = store.get().selectedNodeId === gn.id;
      store.set({ selectedNodeId: alreadySelected ? null : gn.id });
      if (!alreadySelected) handleRef?.recenterOn(gn.node);
    })
    .onBackgroundClick(() => store.set({ selectedNodeId: null }))
    .onNodeHover((n: object | null) => {
      highlight(n === null ? null : (n as GraphNode).id);
    });

  // Keep the canvas sized to its stage cell — an unsized default spills the
  // canvas over the side panels and steals their pointer events.
  const stageResize = new ResizeObserver(() => {
    graph.width(stage.clientWidth);
    graph.height(stage.clientHeight);
  });
  stageResize.observe(stage);

  // Zoom proxy: orbiting preserves camera distance, only zooming changes it.
  // The widest distance ever seen is "fully out"; labels appear past 70% in.
  window.setInterval(() => {
    const dist = cameraDistance(graph);
    if (dist > widestCameraDist) widestCameraDist = dist;
    const zoomed = dist < widestCameraDist * ZOOM_LABEL_FRACTION;
    for (const sprite of sightingLabels.values()) {
      sprite.visible = zoomed;
    }
  }, ZOOM_POLL_MS);

  function pushData(next: BuiltGraph): void {
    built = next;
    graph.graphData({
      nodes: next.nodes as unknown as object[],
      links: next.links as unknown as object[],
    });
  }

  function radius(gn: GraphNode): number {
    return 0.9 + gn.degree * 0.35;
  }

  function nodeObject(gn: GraphNode): Object3D {
    const group = new Group();
    const material = new MeshLambertMaterial({ color: NODE_KIND_COLORS[gn.kind], transparent: true });
    const sphere = new Mesh(new SphereGeometry(radius(gn)), material);
    group.add(sphere);

    // Labels: entity values and verdict summaries always; sightings on zoom-in.
    const isSighting = gn.kind === "sighting";
    const sprite = new SpriteText(clip(gn.label, isSighting ? 18 : 40), isSighting ? 2.5 : 3.5, "#e6edf3");
    sprite.position.set(0, radius(gn) + 3, 0);
    sprite.visible = !isSighting;
    group.add(sprite);
    if (isSighting) sightingLabels.set(gn.id, sprite);

    Object.assign(gn, { __mat: material });
    return group;
  }

  /** Hover = the direct neighborhood stays vivid, the rest dims (spec). */
  function highlight(hoverId: string | null): void {
    const keep = hoverId === null ? null : neighborhood(hoverId, built.links);
    for (const node of built.nodes as SceneNode[]) {
      // three.js materializes node objects lazily after a data push — a node
      // without its material yet simply renders its kind color until the
      // next highlight pass.
      if (node.__mat === undefined) continue;
      const vivid =
        hoverId === null ||
        node.id === hoverId ||
        (keep !== null && keep.has(node.id)) ||
        store.get().selectedNodeId === node.id;
      node.__mat.color.set(vivid ? NODE_KIND_COLORS[node.kind] : DIM_COLOR);
      node.__mat.opacity = vivid ? 1 : 0.45;
    }
  }

  function recenterOn(node: MemoryNode): void {
    const datum = (built.nodes as SceneNode[]).find((n) => n.id === node.id);
    if (datum === undefined || datum.x === undefined || datum.y === undefined || datum.z === undefined) {
      return; // node not in the visible set, or layout has not placed it yet
    }
    const cam = graph.cameraPosition();
    const dx = cam.x - datum.x;
    const dy = cam.y - datum.y;
    const dz = cam.z - datum.z;
    const len = Math.max(Math.sqrt(dx * dx + dy * dy + dz * dz), 1);
    const dist = Math.max(len, 60);
    graph.cameraPosition(
      { x: datum.x + (dx / len) * dist, y: datum.y + (dy / len) * dist, z: datum.z + (dz / len) * dist },
      { x: datum.x, y: datum.y, z: datum.z },
      600,
    );
  }

  pushData(built);
  handleRef = {
    rebuild(nextNodes: readonly MemoryNode[], nextLinks: readonly MemoryLink[]): void {
      sightingLabels.clear();
      pushData(buildGraph(nextNodes, nextLinks));
      highlight(null);
    },
    recenterOn,
    setAutoRotate(on: boolean): void {
      const controls = graph.controls() as { autoRotate?: boolean; autoRotateSpeed?: number };
      controls.autoRotate = on;
      if (on && controls.autoRotateSpeed === undefined) controls.autoRotateSpeed = 0.6;
    },
  };
  store.subscribe(() => highlight(null)); // selection changed — repaint vivid/dim
  return handleRef;
}

/** Camera distance to the orbit target — the zoom proxy for label visibility. */
function cameraDistance(graph: {
  cameraPosition(): { x: number; y: number; z: number };
  controls(): object;
}): number {
  const cam = graph.cameraPosition();
  const controls = graph.controls() as { target?: { x?: number; y?: number; z?: number } };
  const t = controls.target ?? {};
  const dx = cam.x - (t.x ?? 0);
  const dy = cam.y - (t.y ?? 0);
  const dz = cam.z - (t.z ?? 0);
  return Math.sqrt(dx * dx + dy * dy + dz * dz);
}

// ---------------------------------------------------------------------------
// Panel wiring
// ---------------------------------------------------------------------------

function wireFilters(root: HTMLElement, store: ExplorerStore): void {
  const bindToggle = (selector: string, apply: (filters: Filters, event: Event) => void): void => {
    root.querySelector(selector)?.addEventListener("change", (event) => {
      if (!(event.target instanceof HTMLInputElement)) return;
      const next = structuredClone(store.get().filters);
      apply(next, event);
      store.set({ filters: next });
    });
  };

  for (const kind of NODE_KINDS) {
    bindToggle(`#kind-${kind}`, (f, e) => {
      f.kinds[kind] = e.target instanceof HTMLInputElement ? e.target.checked : false;
    });
  }
  for (const o of VERDICT_OUTCOMES) {
    bindToggle(`#outcome-${o}`, (f, e) => {
      f.outcomes[o] = e.target instanceof HTMLInputElement ? e.target.checked : false;
    });
  }
  for (const t of ENTITY_TYPES) {
    bindToggle(`#etype-${t}`, (f, e) => {
      f.entityTypes[t] = e.target instanceof HTMLInputElement ? e.target.checked : false;
    });
  }

  bindToggle("#time-from", (f) => {
    const value = (root.querySelector<HTMLInputElement>("#time-from")?.value ?? "").trim();
    f.timeWindow = { ...(f.timeWindow ?? {}), from: isoOrNull(value) ?? undefined };
  });
  bindToggle("#time-to", (f) => {
    const value = (root.querySelector<HTMLInputElement>("#time-to")?.value ?? "").trim();
    f.timeWindow = { ...(f.timeWindow ?? {}), to: isoOrNull(value) ?? undefined };
  });
  root.querySelector("[data-action=clear-window]")?.addEventListener("click", () => {
    const next = structuredClone(store.get().filters);
    next.timeWindow = null;
    // The checkbox-free path: re-render the (checkbox-only) window inputs by
    // clearing their values directly — no shell rebuild, canvas untouched.
    const from = root.querySelector<HTMLInputElement>("#time-from");
    const to = root.querySelector<HTMLInputElement>("#time-to");
    if (from !== null) from.value = "";
    if (to !== null) to.value = "";
    store.set({ filters: next });
  });
}

/** datetime-local values are timezone-less; the app treats them as UTC. */
function isoOrNull(value: string): string | null {
  if (value.length === 0) return null;
  const ms = Date.parse(`${value}:00Z`);
  return Number.isNaN(ms) ? null : new Date(ms).toISOString();
}

/** Search is jump-to-select (spec): Enter accepts the best-ranked match. */
function wireSearch(
  root: HTMLElement,
  store: ExplorerStore,
  doc: MemoryGraphDocument,
  getScene: () => SceneHandle | null,
): void {
  const input = root.querySelector<HTMLInputElement>("#search");
  const hint = root.querySelector<HTMLElement>("#search-hint");
  if (input === null) return;

  const announce = (count: number): void => {
    if (hint !== null) {
      hint.textContent = count === 0 ? "no matches" : `${count} match${count === 1 ? "" : "es"}`;
    }
  };

  input.addEventListener("input", () => {
    const q = input.value.trim();
    if (q.length === 0) {
      announce(0);
      if (hint !== null) hint.textContent = "";
      return;
    }
    announce(findMatches(doc, q).length);
  });
  input.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    const matches = findMatches(doc, input.value);
    announce(matches.length);
    const first = matches[0];
    if (first === undefined) return;
    store.set({ selectedNodeId: first.id });
    getScene()?.recenterOn(first);
  });
}

function wireTopbar(root: HTMLElement, store: ExplorerStore, getScene: () => SceneHandle | null): void {
  root.querySelector<HTMLInputElement>("#auto-rotate")?.addEventListener("change", (event) => {
    if (!(event.target instanceof HTMLInputElement)) return;
    getScene()?.setAutoRotate(event.target.checked);
  });
  root.querySelector("[data-action=recenter]")?.addEventListener("click", () => {
    const id = store.get().selectedNodeId;
    if (id === null) return;
    const node = store.get().document?.nodes.find((n) => n.id === id);
    if (node !== undefined) getScene()?.recenterOn(node);
  });
}

// ---------------------------------------------------------------------------
// Detail panel
// ---------------------------------------------------------------------------

function detailHtml(node: MemoryNode, doc: MemoryGraphDocument): string {
  const vm = detailViewModel(node, doc);
  const badgeTone = vm.badge?.tone ?? "neutral";
  return `
    <h2>${escapeHtml(vm.title)}</h2>
    ${vm.badge !== undefined ? `<span class="badge badge-${badgeTone}">${escapeHtml(vm.badge.text)}</span>` : ""}
    <dl>
      ${vm.fields
        .map(
          (f) =>
            `<div class="field"><dt>${escapeHtml(f.label)}</dt><dd class="${f.mono === true ? "mono" : ""}">${escapeHtml(f.value ?? "")}</dd></div>`,
        )
        .join("")}
    </dl>
    ${vm.raw !== undefined ? `<details class="raw"><summary>raw node</summary><pre>${escapeHtml(vm.raw)}</pre></details>` : ""}`;
}

// ---------------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------------

/** A filter checkbox row; kinds carry a visible/total count span (data-count). */
function checkboxRow(id: string, label: string, checked: boolean, countKind?: NodeKind): string {
  const count = countKind === undefined ? "" : ` <span class="count" data-count="${countKind}"></span>`;
  return `<label class="check"><input type="checkbox" id="${id}" ${checked ? "checked" : ""} /> ${escapeHtml(label)}${count}</label>`;
}

function shell(inner: string): string {
  return `<div class="vigilmap-shell">${inner}</div>`;
}

function escapeHtml(text: string): string {
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function clip(text: string, max: number): string {
  return text.length <= max ? text : `${text.slice(0, max - 1)}…`;
}

function prefersReducedMotion(): boolean {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function paintKey(doc: MemoryGraphDocument, filters: Filters): string {
  return `${doc.source}:${doc.nodes.length}:${JSON.stringify(filters)}`;
}

function detectWebglError(): string | null {
  try {
    const canvas = document.createElement("canvas");
    const gl = canvas.getContext("webgl2") ?? canvas.getContext("webgl");
    return gl === null ? WEBGL_ERROR : null;
  } catch {
    return WEBGL_ERROR;
  }
}
