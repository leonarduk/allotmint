export const money = (
    v: number | null | undefined,
    currency = "GBP",
): string => {
    if (typeof v !== "number" || !Number.isFinite(v)) return "—";
    return v.toLocaleString("en-GB", {
        style: "currency",
        currency,
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    });
};

export const percent = (
    v: number | null | undefined,
    fractionDigits = 2,
): string => {
    if (typeof v !== "number" || !Number.isFinite(v)) return "—";
    return `${v.toLocaleString("en-GB", {
        minimumFractionDigits: fractionDigits,
        maximumFractionDigits: fractionDigits,
    })}%`;
};
