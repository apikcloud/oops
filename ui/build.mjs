import * as esbuild from "esbuild";
import { cpSync, mkdirSync } from "node:fs";

const DEST = "../src/oops/output/ui";

const opts = {
    entryPoints: ["src/boot.ts"],
    bundle: true,
    format: "iife",
    target: "es2020",
    outfile: `${DEST}/dist/app.bundle.js`,
    minify: process.argv.includes("--minify"),
    sourcemap: process.argv.includes("--watch") ? "inline" : false,
    logLevel: "info",
};

function copyAssets() {
    mkdirSync(`${DEST}/css`, { recursive: true });
    cpSync("index.html", `${DEST}/index.html`);
    cpSync("css", `${DEST}/css`, { recursive: true });
}

if (process.argv.includes("--watch")) {
    const ctx = await esbuild.context(opts);
    await ctx.watch();
    copyAssets(); // initial copy; re-run build for html/css changes
    console.error("esbuild: watching src/…");
} else {
    await esbuild.build(opts);
    copyAssets();
}
