/**
 * `@allotmint/host`: the only module frontend plugins may import host code
 * from (#6836, ADR docs/decisions/6836-pro-frontend-plugin-packaging.md
 * §4.3). Keep it small and deliberate: every export here is public API, and
 * an incompatible change to it means bumping HOST_API_VERSION.
 */
export { HOST_API_VERSION } from './contract';
export type {
  AllotmintFrontendPlugin,
  PluginPageEntry,
  SlotName,
} from './contract';
