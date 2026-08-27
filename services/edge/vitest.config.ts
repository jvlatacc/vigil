import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["tests/**/*.test.ts"],
    // The round-trip test boots a Flue runtime, and a process holds at most one:
    // parallel files inside one worker would fight over it.
    fileParallelism: false,
  },
});
