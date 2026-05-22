#!/usr/bin/env node
import fs from "node:fs";

const mode = process.argv[2];
const allowed = new Set(["patch", "minor", "major"]);

if (!allowed.has(mode)) {
  console.error("Usage: node scripts/bump-version.mjs <patch|minor|major>");
  process.exit(1);
}

const manifestPath = "extension/manifest.json";
const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
const versionRaw = String(manifest.version || "").trim();
const match = /^(\d+)\.(\d+)\.(\d+)$/.exec(versionRaw);

if (!match) {
  console.error(`Error: extension/manifest.json version must be X.Y.Z, got '${versionRaw}'.`);
  process.exit(1);
}

let [major, minor, patch] = match.slice(1).map(Number);
if (mode === "patch") patch += 1;
if (mode === "minor") {
  minor += 1;
  patch = 0;
}
if (mode === "major") {
  major += 1;
  minor = 0;
  patch = 0;
}

const nextVersion = `${major}.${minor}.${patch}`;
manifest.version = nextVersion;
fs.writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");

console.log(`New version: ${nextVersion}`);
console.log(`git add extension/manifest.json && git commit -m \"chore: bump extension to v${nextVersion}\"`);
console.log(`git tag v${nextVersion}`);
console.log("git push origin main");
console.log("git push --tags");
