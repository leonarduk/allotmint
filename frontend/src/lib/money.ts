import i18n from "../i18n";

// Pence-denominated codes from known data providers (uppercased for lookup).
// "GBp" (Yahoo Finance) is handled separately because its uppercase form "GBP"
// is a legitimate currency code and must not be treated as a pence code.
const PENCE_CODES = new Set(["GBX", "GBXP", "GBPX"]);

/**
 * Map any pence-variant currency code to "GBP" for Intl.NumberFormat.
 * Also normalises all codes to uppercase so that e.g. "gbp" works identically
 * to "GBP" rather than causing a RangeError in some environments.
 *
 * Note: this does NOT divide the value by 100 — it only fixes the currency
 * tag passed to Intl.NumberFormat. Backend prices are already GBP-normalised.
 */
export const normalizeDisplayCurrency = (currency: string): string => {
    // Yahoo Finance uses exact "GBp" for pence. Its uppercase form is "GBP",
    // which is NOT in PENCE_CODES, so it requires an explicit early return.
    if (currency === "GBp") {
        return "GBP";
    }

    const upper = currency.toUpperCase();
    if (PENCE_CODES.has(upper)) {
        return "GBP";
    }

    // Normalise to uppercase so Intl.NumberFormat never receives lowercase
    // codes (e.g. "gbp" -> "GBP"). Intl accepts case-insensitive codes per
    // spec, but normalising here makes the contract explicit.
    return upper;
};

export const money = (
    v: number | null | undefined,
    currency = "GBP",
    locale: string = i18n.language,
): string => {
    if (typeof v !== "number" || !Number.isFinite(v)) return "—";
    const displayCurrency = normalizeDisplayCurrency(currency);
    return new Intl.NumberFormat(locale, {
        style: "currency",
        currency: displayCurrency,
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    }).format(v);
};

export const percent = (
    v: number | null | undefined,
    fractionDigits = 2,
    locale: string = i18n.language,
): string => {
    if (typeof v !== "number" || !Number.isFinite(v)) return "—";
    return (
        new Intl.NumberFormat(locale, {
            minimumFractionDigits: fractionDigits,
            maximumFractionDigits: fractionDigits,
        }).format(v) + "%"
    );
};

export const percentOrNa = (
    v: number | null | undefined,
    fractionDigits = 2,
    locale: string = i18n.language,
): string => {
    if (typeof v !== "number" || !Number.isFinite(v)) return "N/A";
    const absValue = Math.abs(v);
    const MAX_REASONABLE_PERCENT = 1000;

    if (absValue > MAX_REASONABLE_PERCENT) {
        console.warn("Metric value out of range:", v);
        return "N/A";
    }

    const normalizedValue = absValue > 1 ? v / 100 : v;

    return percent(normalizedValue * 100, fractionDigits, locale);
};

export const largeNumber = (
    v: number | null | undefined,
    locale: string = i18n.language,
): string => {
    if (typeof v !== "number" || !Number.isFinite(v)) return "—";
    return new Intl.NumberFormat(locale).format(v);
};
