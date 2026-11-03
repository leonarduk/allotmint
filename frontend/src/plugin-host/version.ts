/**
 * Version of the host API that frontend plugins compile against (#6836).
 *
 * Bump it whenever `@allotmint/host` (src/plugin-host/api.ts) or the plugin
 * contract (src/plugin-host/contract.ts) changes incompatibly. It lives in
 * its own dependency-free module so the Vite plugin in vite/allotmintPlugins.ts
 * can read it at build time without pulling app code into the Node config.
 */
export const HOST_API_VERSION = 1;
