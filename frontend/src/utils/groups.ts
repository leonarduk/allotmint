import type { TFunction } from "i18next";
import { ALL_PORTFOLIOS_SLUG } from "../constants/portfolios";

export const DEFAULT_GROUP_SLUG = ALL_PORTFOLIOS_SLUG;

export function isDefaultGroupSlug(slug?: string | null): boolean {
  return !slug || slug === DEFAULT_GROUP_SLUG;
}

export function normaliseGroupSlug(slug?: string | null): string {
  return !slug || slug === DEFAULT_GROUP_SLUG ? DEFAULT_GROUP_SLUG : slug;
}

export function getGroupDisplayName(
  slug: string | null | undefined,
  fallbackName: string,
  t: TFunction,
): string {
  return isDefaultGroupSlug(slug) ? t("group.atAGlance") : fallbackName;
}
