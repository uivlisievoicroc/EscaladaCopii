import { createHash } from 'node:crypto';
import { mkdirSync, readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { join, relative, resolve } from 'node:path';

const HASH_TARGETS = ['package.json', 'src', 'vite.config.ts'];
const SOURCE_EXTENSIONS = new Set([
  '.css',
  '.d.ts',
  '.html',
  '.js',
  '.json',
  '.jsx',
  '.ts',
  '.tsx',
]);

const shouldHashFile = (filePath) => {
  for (const extension of SOURCE_EXTENSIONS) {
    if (filePath.endsWith(extension)) {
      return true;
    }
  }
  return false;
};

const collectFiles = (rootDir, targetPath, acc) => {
  if (!statSync(targetPath).isDirectory()) {
    if (shouldHashFile(targetPath)) {
      acc.push(relative(rootDir, targetPath));
    }
    return;
  }

  const entries = readdirSync(targetPath, { withFileTypes: true }).sort((a, b) =>
    a.name.localeCompare(b.name),
  );
  for (const entry of entries) {
    if (entry.name === '.DS_Store') continue;
    collectFiles(rootDir, join(targetPath, entry.name), acc);
  }
};

export const computeFrontendSourceHash = (rootDir) => {
  const resolvedRoot = resolve(rootDir);
  const files = [];
  for (const target of HASH_TARGETS) {
    const targetPath = join(resolvedRoot, target);
    collectFiles(resolvedRoot, targetPath, files);
  }

  const hash = createHash('sha1');
  for (const relativePath of files.sort()) {
    hash.update(relativePath);
    hash.update('\n');
    hash.update(readFileSync(join(resolvedRoot, relativePath)));
    hash.update('\n');
  }
  return hash.digest('hex');
};

export const computeFrontendBuildInfo = (rootDir) => {
  const resolvedRoot = resolve(rootDir);
  const packageJson = JSON.parse(readFileSync(join(resolvedRoot, 'package.json'), 'utf-8'));
  const sourceHash = computeFrontendSourceHash(resolvedRoot);
  return {
    version: String(packageJson.version || '0.0.0'),
    sourceHash,
    marker: `${String(packageJson.version || '0.0.0')}-${sourceHash.slice(0, 12)}`,
    builtAt: new Date().toISOString(),
  };
};

export const writeFrontendBuildInfo = (outDir, buildInfo) => {
  mkdirSync(outDir, { recursive: true });
  writeFileSync(
    join(outDir, 'build-info.json'),
    `${JSON.stringify(buildInfo, null, 2)}\n`,
    'utf-8',
  );
};

