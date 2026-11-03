#!/usr/bin/env node
/**
 * Build guard for build-time frontend plugins (#6836, ADR
 * docs/decisions/6836-pro-frontend-plugin-packaging.md §4.5).
 *
 * 1. The public build in frontend/dist (run `npm run build:preview` first,
 *    with ALLOTMINT_PLUGIN_ENTRIES unset) must not contain the fixture
 *    plugin's marker string.
 * 2. A second build with ALLOTMINT_PLUGIN_ENTRIES pointing at
 *    tests/frontend-plugin-fixture/index.ts, outside frontend/, must
 *    succeed and contain it, proving cross-directory resolution and dedupe.
 *
 * Usage (from frontend/): node scripts/verify-plugin-build.mjs
 */
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const MARKER = 'ALLOTMINT_PLUGIN_BUILD_FIXTURE_6836';
const frontendDir = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '..'
);
const fixtureEntry = path.resolve(
  frontendDir,
  '..',
  'tests',
  'frontend-plugin-fixture',
  'index.ts'
);
const publicDist = path.join(frontendDir, 'dist');
const viteBin = path.join(
  frontendDir,
  'node_modules',
  'vite',
  'bin',
  'vite.js'
);

function filesUnder(dir) {
  return fs
    .readdirSync(dir, { recursive: true, withFileTypes: true })
    .filter((entry) => entry.isFile())
    .map((entry) => path.join(entry.parentPath, entry.name));
}

function filesWithMarker(dir) {
  return filesUnder(dir).filter((file) =>
    fs.readFileSync(file, 'utf-8').includes(MARKER)
  );
}

function fail(message) {
  console.error(`verify-plugin-build: ${message}`);
  process.exit(1);
}

function checkPublicBuild() {
  if (!fs.existsSync(publicDist))
    fail(`${publicDist} is missing; run "npm run build:preview" first.`);
  const leaked = filesWithMarker(publicDist);
  if (leaked.length > 0)
    fail(`the public build contains plugin fixture code: ${leaked.join(', ')}`);
  console.log(
    'verify-plugin-build: public build contains no plugin fixture code'
  );
}

function checkFixtureBuild() {
  const outDir = fs.mkdtempSync(
    path.join(os.tmpdir(), 'allotmint-plugin-build-')
  );
  try {
    const result = spawnSync(
      process.execPath,
      [viteBin, 'build', '--outDir', outDir, '--emptyOutDir'],
      {
        cwd: frontendDir,
        env: { ...process.env, ALLOTMINT_PLUGIN_ENTRIES: fixtureEntry },
        stdio: 'inherit',
      }
    );
    if (result.status !== 0)
      fail(
        `the fixture plugin build failed (exit ${result.status ?? result.signal}).`
      );
    if (filesWithMarker(outDir).length === 0)
      fail('the fixture plugin build does not contain the fixture page.');
    console.log(
      'verify-plugin-build: fixture plugin from outside frontend/ is bundled'
    );
  } finally {
    fs.rmSync(outDir, { recursive: true, force: true });
  }
}

checkPublicBuild();
checkFixtureBuild();
