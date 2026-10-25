import { useTranslation } from "react-i18next";
import { percent } from "../lib/money";
import type { PortfolioReturnBasis, PortfolioReturnBasisFields } from "../types";

type Props = {
  fields: PortfolioReturnBasisFields | null;
  className?: string;
};

/**
 * Which return basis the portfolio side of alpha is on (#10339): total return
 * (dividends reinvested), price only, or a mix -- with the share of value on
 * price and the holdings left out for want of prices. Renders nothing for an
 * older backend that sends no basis fields.
 */
export default function ReturnBasisNote({ fields, className }: Props) {
  const { t, i18n } = useTranslation();
  const basis = fields?.portfolio_return_basis;
  if (!basis) return null;

  const basisLabels: Record<PortfolioReturnBasis, string> = {
    total: t("dashboard.returnBasisTotal", "total return (dividends reinvested)"),
    price: t("dashboard.returnBasisPrice", "price only (dividends not included)"),
    mixed: t("dashboard.returnBasisMixed", "mixed: some holdings are price only"),
  };
  const shortLabels: Record<"total" | "price", string> = {
    total: t("dashboard.returnBasisTotalShort", "total return"),
    price: t("dashboard.returnBasisPriceShort", "price only"),
  };
  const mixed = basis === "mixed";
  const share = fields.portfolio_price_basis_share;
  // An all-total-return portfolio is 0% on price; saying so is just noise.
  const showShare = basis !== "total" && typeof share === "number" && Number.isFinite(share);
  const unpriced = fields.portfolio_unpriced_holdings ?? [];

  return (
    <div className={className} style={{ fontSize: "0.75rem" }}>
      <div
        data-testid="alpha-return-basis"
        data-basis={basis}
        style={mixed ? { color: "#facc15" } : undefined}
      >
        {t("dashboard.returnBasisLabel", "Return basis: {{basis}}", {
          basis: basisLabels[basis],
        })}
      </div>
      {showShare && (
        <div data-testid="alpha-price-basis-share">
          {t("dashboard.returnBasisPriceShare", "{{share}} of value on price only", {
            share: percent(share * 100, 0, i18n.language),
          })}
        </div>
      )}
      {unpriced.length > 0 && (
        <div data-testid="alpha-unpriced-holdings">
          {t("dashboard.returnBasisUnpriced", "Left out for want of prices: {{holdings}}", {
            holdings: unpriced
              .map((holding) => `${holding.ticker} (${shortLabels[holding.return_basis]})`)
              .join(", "),
          })}
        </div>
      )}
    </div>
  );
}
