export const money = (v: number | null | undefined): string => {
    if (typeof v !== "number" || !Number.isFinite(v)) return "—";
    return `£${v.toLocaleString("en-GB", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    })}`;
};
