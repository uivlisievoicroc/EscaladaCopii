import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { join, resolve } from 'node:path';
import { computeFrontendSourceHash } from '../build/buildInfo.js';

const rootDir = resolve(fileURLToPath(new URL('..', import.meta.url)));
const distDir = join(rootDir, 'dist');
const buildInfoPath = join(distDir, 'build-info.json');

if (!existsSync(buildInfoPath)) {
  throw new Error(`Missing build metadata: ${buildInfoPath}`);
}

const buildInfo = JSON.parse(readFileSync(buildInfoPath, 'utf-8'));
const expectedSourceHash = computeFrontendSourceHash(rootDir);

if (buildInfo.sourceHash !== expectedSourceHash) {
  throw new Error(
    `Build source hash mismatch. expected=${expectedSourceHash} actual=${buildInfo.sourceHash}`,
  );
}

const assetsDir = join(distDir, 'assets');
const assetFiles = existsSync(assetsDir)
  ? readdirSync(assetsDir).filter((name) => name.endsWith('.js'))
  : [];
if (assetFiles.length === 0) {
  throw new Error(`No built JS assets found in ${assetsDir}`);
}

const markerFound = assetFiles.some((fileName) => {
  const content = readFileSync(join(assetsDir, fileName), 'utf-8');
  return content.includes(buildInfo.marker);
});

if (!markerFound) {
  throw new Error(`Build marker ${buildInfo.marker} was not found in dist JS assets`);
}

console.log(
  `Verified frontend build marker ${buildInfo.marker} for source hash ${buildInfo.sourceHash}`,
);

