import { defineConfig } from "tsup";

export default defineConfig({
  entry: ["src/index.ts", "src/core.ts", "src/sdkOperations.ts"],
  format: ["esm"],
  dts: true,
  clean: true,
  target: "node18",
});
