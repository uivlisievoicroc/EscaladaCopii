import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { computeFrontendBuildInfo, writeFrontendBuildInfo } from './build/buildInfo.js';

const rootDir = fileURLToPath(new URL('.', import.meta.url));
const buildInfo = computeFrontendBuildInfo(rootDir);

const frontendBuildInfoPlugin = () => {
  let outDir = resolve(rootDir, 'dist');
  return {
    name: 'frontend-build-info',
    configResolved(config) {
      outDir = resolve(rootDir, config.build.outDir);
    },
    closeBundle() {
      writeFrontendBuildInfo(outDir, buildInfo);
    },
  };
};

// https://vite.dev/config/
export default defineConfig({
  define: {
    __ESCALADA_BUILD_MARKER__: JSON.stringify(buildInfo.marker),
    __ESCALADA_BUILD_SOURCE_HASH__: JSON.stringify(buildInfo.sourceHash),
    __ESCALADA_BUILD_VERSION__: JSON.stringify(buildInfo.version),
  },
  server: { host: true },
  plugins: [react(), frontendBuildInfoPlugin()],
});
