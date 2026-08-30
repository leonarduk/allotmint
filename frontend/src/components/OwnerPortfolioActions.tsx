import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { Account } from "../types";
import { complianceForOwner } from "../api";
import { useConfig } from "../ConfigContext";
import { downloadPortfolioCsv, printPortfolioPdf } from "../lib/portfolioExport";
import { AddAccountForm } from "./AddAccountForm";
import { AddPositionForm } from "./AddPositionForm";
import { CsvImportForm } from "./CsvImportForm";
import { ValueAtRisk } from "./ValueAtRisk";
import { useDemoReadOnly } from "../hooks/useDemoReadOnly";

const FORM_ID = "group-add-position-form";
type Props = { owner: string; asOf: string; accounts: Account[]; activeAccountType: string | null; onDateChange: (date: string | null) => void; onMutated: () => void };

export function OwnerPortfolioActions({ owner, asOf, accounts, activeAccountType, onDateChange, onMutated }: Props) {
  const { t } = useTranslation();
  const { demoReadOnly, reason } = useDemoReadOnly();
  const { familyMvpEnabled, enableAdvancedAnalytics = true, tabs, disabledTabs } = useConfig();
  const complianceEnabled = tabs["trade-compliance"] && !(disabledTabs ?? []).includes("trade-compliance");
  const [hasWarnings, setHasWarnings] = useState(false);
  const [complianceError, setComplianceError] = useState(false);
  const [showAccount, setShowAccount] = useState(false);
  const [showImport, setShowImport] = useState(false);
  const [showPosition, setShowPosition] = useState(false);
  const positionRef = useRef<HTMLDivElement>(null);
  const portfolio = { owner, as_of: asOf, accounts };
  const accountTypes = Array.from(new Set(accounts.map((account) => account.account_type)));

  const collapsePosition = useCallback(() => setShowPosition(false), []);
  useEffect(() => {
    if (!showPosition) return;
    const listener = (event: KeyboardEvent) => { if (event.key === "Escape") collapsePosition(); };
    document.addEventListener("keydown", listener);
    return () => document.removeEventListener("keydown", listener);
  }, [showPosition, collapsePosition]);
  useEffect(() => {
    setHasWarnings(false);
    setComplianceError(false);
    if (!complianceEnabled) return;
    let cancelled = false;
    complianceForOwner(owner).then((result) => { if (!cancelled) setHasWarnings(result.warnings.length > 0); }).catch(() => {
      if (!cancelled) {
        setHasWarnings(false);
        setComplianceError(true);
      }
    });
    return () => { cancelled = true; };
  }, [owner, complianceEnabled]);

  const finishMutation = () => { setShowAccount(false); setShowImport(false); collapsePosition(); onMutated(); };
  const openPosition = () => { setShowPosition(true); positionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }); };
  const buttonClass = "rounded border border-gray-700 px-3 py-1.5 text-sm text-white hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-transparent";

  return <section className="mb-6 rounded-lg border border-gray-800 bg-gray-900/70 p-4">
    {accounts.length > 0 && <div className="mb-4 flex flex-wrap items-center gap-2">
      {!familyMvpEnabled && <>
        <button type="button" onClick={() => downloadPortfolioCsv(portfolio)} aria-label="Export portfolio as CSV" className={buttonClass}>Export CSV</button>
        <button type="button" onClick={() => printPortfolioPdf(portfolio)} aria-label="Export portfolio as PDF" className={buttonClass}>Export PDF</button>
      </>}
      {!showPosition && <button type="button" onClick={openPosition} aria-expanded="false" aria-controls={FORM_ID} disabled={demoReadOnly} title={reason()} className={buttonClass}>+ {t("addPosition.title")}</button>}
      {!showImport && <button type="button" onClick={() => setShowImport(true)} disabled={demoReadOnly} title={reason()} className={buttonClass}>+ Import CSV</button>}
      {!showAccount && <button type="button" onClick={() => setShowAccount(true)} disabled={demoReadOnly} title={reason()} className={buttonClass}>Add account</button>}
    </div>}
    <div ref={positionRef}>{showPosition && <AddPositionForm owner={owner} accounts={accountTypes} defaultAccount={activeAccountType && accountTypes.includes(activeAccountType) ? activeAccountType : undefined} onAdded={finishMutation} onCollapse={collapsePosition} controlsId={FORM_ID} />}</div>
    {showImport && accounts.length > 0 && <div className="mb-6"><CsvImportForm owner={owner} accountTypes={accountTypes} onImported={finishMutation} /><button type="button" onClick={() => setShowImport(false)} className="mt-2 text-xs text-gray-400 underline">Cancel import</button></div>}
    {showAccount && <div className="mb-6"><AddAccountForm owner={owner} onCreated={finishMutation} onCancel={() => setShowAccount(false)} /></div>}
    {hasWarnings && <div className="mb-4"><Link to={`/compliance/${owner}`} className="text-blue-400 hover:text-blue-300">View compliance warnings</Link></div>}
    {complianceError && <p role="alert" className="mb-4 text-sm text-red-400">Unable to load compliance warnings.</p>}
    {enableAdvancedAnalytics && <div className="rounded-lg border border-gray-800 bg-black/30 p-4"><ValueAtRisk owner={owner} onDateChange={onDateChange} /></div>}
  </section>;
}
