import i18n from "../i18n";

export const money = (
    v: number | null | undefined,
    currency = "GBP",
    locale: string = i18n.language,
): string => {
    if (typeof v !== "number" || !Number.isFinite(v)) return "—";
    const displayCurrency = currency === "GBX" ? "GBP" : currency;
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
