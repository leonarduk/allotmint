import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useDemoReadOnly } from "../hooks/useDemoReadOnly";
import { invalidateInstrumentHistory } from "../hooks/useInstrumentHistory";
import type { InstrumentPosition } from "../types";
import { InstrumentTransactions } from "./InstrumentTransactions";
import { RecordTradeForm } from "./RecordTradeForm";
import type { TradeType } from "./transactions/transactionForm";

type Props = {
  ticker: string;
  positions: InstrumentPosition[];
  quoteCurrency?: string | null;
};

/**
 * The Research page's transactions list plus Buy / Sell entry (#9991).
 * Saving a trade drops the cached instrument history -- which carries the
 * positions table -- so both positions and transactions reload.
 */
export function InstrumentTradeSection({ ticker, positions, quoteCurrency }: Props) {
  const { t } = useTranslation();
  const { demoReadOnly, reason } = useDemoReadOnly();
  const [side, setSide] = useState<TradeType | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);
  const [savedMessage, setSavedMessage] = useState<string | null>(null);

  const open = (next: TradeType) => {
    setSavedMessage(null);
    setSide(next);
  };

  const handleSaved = (saved: TradeType) => {
    setSide(null);
    setSavedMessage(
      t("recordTrade.saved", { side: t(saved === "SELL" ? "recordTrade.sell" : "recordTrade.buy"), ticker }),
    );
    setRefreshToken((n) => n + 1);
    invalidateInstrumentHistory(ticker);
  };

  return (
    <section aria-label={t("instrumentDetail.research.transactions")}>
      <h2 style={{ marginBottom: "0.75rem" }}>{t("instrumentDetail.research.transactions")}</h2>
      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.75rem" }} title={reason()}>
        <button type="button" disabled={demoReadOnly} onClick={() => open("BUY")}>
          {t("recordTrade.buy")}
        </button>
        <button type="button" disabled={demoReadOnly} onClick={() => open("SELL")}>
          {t("recordTrade.sell")}
        </button>
      </div>
      {savedMessage && <div role="status">{savedMessage}</div>}
      {side && (
        <RecordTradeForm
          key={side}
          ticker={ticker}
          side={side}
          positions={positions}
          quoteCurrency={quoteCurrency}
          onSaved={handleSaved}
          onCancel={() => setSide(null)}
        />
      )}
      <InstrumentTransactions ticker={ticker} refreshToken={refreshToken} />
    </section>
  );
}
