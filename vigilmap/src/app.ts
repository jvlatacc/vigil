/**
 * App shell wiring: resolve the data source on boot, then render one of the
 * four states — loading, error, empty, ready. The 3D scene lands in the next
 * PR; "ready" is for now a quiet placeholder panel listing node counts by
 * kind, plus the drop target the source-resolution contract needs.
 */

import { loadDroppedFile, resolveSource } from "./load";
import { countByKind, createStore, deriveAppState } from "./store";
import { NODE_KINDS } from "./types";
import type { ExplorerStore } from "./store";

export function mountApp(root: HTMLElement): void {
  root.innerHTML = "";
  const store = createStore();
  render(root, store);

  // Drag-drop is a source-resolution path, not an app afterthought: a dropped
  // document goes through the same validator as everything else.
  root.addEventListener("dragover", (event) => event.preventDefault());
  root.addEventListener("drop", (event) => {
    event.preventDefault();
    const file = event.dataTransfer?.files?.[0];
    if (!file) return;
    void loadDroppedFile(file).then((outcome) => applyOutcome(store, outcome, root));
  });

  void resolveSource().then((outcome) => applyOutcome(store, outcome, root));
}

function applyOutcome(
  store: ExplorerStore,
  outcome: Awaited<ReturnType<typeof resolveSource>>,
  root: HTMLElement,
): void {
  if (outcome.status === "loaded") {
    store.set({ document: outcome.document, error: null });
  } else {
    store.set({ error: outcome.message });
  }
  render(root, store);
}

function render(root: HTMLElement, store: ExplorerStore): void {
  const state = store.get();
  const appState = deriveAppState(state);

  switch (appState) {
    case "loading":
      root.innerHTML = shell(`<p class="status-note" data-state="loading">loading memory…</p>`);
      break;
    case "error":
      root.innerHTML = shell(`
        <section class="status-card" data-state="error" role="alert" aria-live="assertive">
          <h1>Document rejected</h1>
          <p class="error-message">${escapeHtml(state.error ?? "unknown error")}</p>
          <p><button type="button" id="load-sample">Load the sample dataset</button></p>
        </section>`);
      root.querySelector("#load-sample")?.addEventListener("click", () => {
        store.set({ error: null });
        render(root, store);
        void resolveSource({ search: "" }).then((outcome) => applyOutcome(store, outcome, root));
      });
      break;
    case "empty":
      root.innerHTML = shell(`
        <section class="status-card" data-state="empty" role="status">
          <h1>VigilMap</h1>
          <p class="status-note">this memory has no rows</p>
          <p>Drop a memory document anywhere, or open one with <code>?data=&lt;url&gt;</code>.</p>
        </section>`);
      break;
    case "ready":
      renderReady(root, state);
      break;
  }
}

function renderReady(root: HTMLElement, state: ReturnType<ExplorerStore["get"]>): void {
  const document = state.document;
  if (document === null) return; // unreachable behind deriveAppState === "ready"
  const counts = countByKind(document);
  const rows = NODE_KINDS.map(
    (kind) => `<tr><th scope="row">${kind}</th><td>${counts[kind]}</td></tr>`,
  ).join("");

  root.innerHTML = shell(`
    <main class="layout" data-state="ready">
      <section class="placeholder-panel" aria-label="memory contents">
        <h1>VigilMap</h1>
        <p class="status-note">
          ${document.nodes.length} nodes · ${document.links.length} links
          · source: <code>${escapeHtml(document.source)}</code>
        </p>
        <table>
          <caption>nodes by kind</caption>
          <tbody>${rows}</tbody>
        </table>
        <p class="muted">The 3D graph, filters, and detail panel land in the next PR.
        Drop a memory document anywhere to load your own.</p>
      </section>
    </main>`);
}

/** Full-viewport chrome shared by every state; the canvas host arrives with the scene. */
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
