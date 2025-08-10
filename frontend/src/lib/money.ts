import i18n from "../i18n";

export const money = (
    v: number | null | undefined,
    currency = "GBP",
    locale: string = i18n.language,
): string => {
    if (typeof v !== "number" || !Number.isFinite(v)) return "—";
    return new Intl.NumberFormat(locale, {
        style: "currency",
        currency,
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
