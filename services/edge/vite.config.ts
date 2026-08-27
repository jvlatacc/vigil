import { cloudflare } from "@cloudflare/vite-plugin";
import { flue, flueWorkerConfig } from "@flue/vite";
import { defineConfig } from "vite";

// flue() must come first, and cloudflare() must be handed Flue's customizer:
// the scan of 'use agent' modules is what produces the generated Worker entry
// and the one Durable Object binding per agent, and the customizer is how those
// reach the Cloudflare plugin's resolved worker config. Flue never reads or
// rewrites wrangler.jsonc -- the authored file, and with it the migration
// ledger, stays ours; the merged config is emitted into the build output.
//
// The target is detected from the plugin array (@cloudflare/vite-plugin present
// -> cloudflare), so it is not restated here.
export default defineConfig({
  plugins: [
    // The scan is narrowed to src/agents/ so a stray directive elsewhere cannot
    // quietly mint a Durable Object class -- every agent needs a migration tag,
    // and a class that appears without one is a deploy that fails or, worse, one
    // that succeeds against storage nobody declared.
    flue({ agents: "agents/**/*.ts" }),
    cloudflare({ config: flueWorkerConfig() }),
  ],
});
