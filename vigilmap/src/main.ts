import { mountApp } from "./app";

const root = document.getElementById("app");
if (root === null) {
  throw new Error("#app host element missing — index.html is broken");
}
mountApp(root);
