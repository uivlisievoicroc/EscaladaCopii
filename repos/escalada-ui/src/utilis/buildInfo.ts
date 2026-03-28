export const APP_BUILD_INFO = {
  marker:
    typeof __ESCALADA_BUILD_MARKER__ !== 'undefined' ? __ESCALADA_BUILD_MARKER__ : 'dev-build',
  sourceHash:
    typeof __ESCALADA_BUILD_SOURCE_HASH__ !== 'undefined'
      ? __ESCALADA_BUILD_SOURCE_HASH__
      : 'dev-source-hash',
  version:
    typeof __ESCALADA_BUILD_VERSION__ !== 'undefined' ? __ESCALADA_BUILD_VERSION__ : '0.0.0-dev',
} as const;
