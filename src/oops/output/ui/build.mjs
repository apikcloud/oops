import * as esbuild from "esbuild";

const opts = {
  entryPoints: ["src/boot.ts"],
  bundle: true,
  format: "iife",          // no ES modules at runtime → file:// safe
  target: "es2020",
  outfile: "dist/app.bundle.js",
  minify: process.argv.includes("--minify"),
  sourcemap: process.argv.includes("--watch") ? "inline" : false,
  logLevel: "info",
};

if (process.argv.includes("--watch")) {
  const ctx = await esbuild.context(opts);
  await ctx.watch();
  console.error("esbuild: watching src/…");
} else {
  await esbuild.build(opts);
}
