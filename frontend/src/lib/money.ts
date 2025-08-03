export const money = (v: number | null | undefined) =>
    `£${(v ?? 0).toLocaleString("en-GB", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    })}`;
