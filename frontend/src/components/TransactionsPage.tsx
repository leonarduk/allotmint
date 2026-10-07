import { useCallback, useEffect, useMemo, useState } from 'react';
import type { ChangeEvent, ChangeEventHandler, FormEvent } from 'react';
import type { OwnerSummary, Transaction } from '../types';
import {
  createManualHolding,
  createTransaction,
  deleteTransaction,
  getManualHoldings,
  getTransactions,
  updateTransaction,
} from '../api';
import { useFetch } from '../hooks/useFetch';
import { useReportingCurrency } from '../hooks/useReportingCurrency';
import { Trans, useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { createOwnerDisplayLookup, findOwnerForUser } from '../utils/owners';
import { useAuth } from '../AuthContext';
import { useDemoReadOnly } from '../hooks/useDemoReadOnly';
import { TransactionEditorForm } from './transactions/TransactionEditorForm';
import { TransactionsFilters } from './transactions/TransactionsFilters';
import {
  buildTransactionPayload,
  createTransactionFormValues,
  EMPTY_TRANSACTION_FORM_VALUES,
  type TransactionFormValues,
} from './transactions/transactionForm';
import {
  buildBulkDeletionOrder,
  filterAndSortTransactions,
  summariseTransactions,
  type TradeSideFilter,
} from './transactions/transactionTable';
import { TransactionsTable } from './transactions/TransactionsTable';
import { useTransactionsTableState } from '../hooks/useTransactionsTableState';
import surface from '../styles/surface.module.css';

type Props = {
  owners: OwnerSummary[];
  inputOnly?: boolean;
};

export function TransactionsPage({ owners, inputOnly = false }: Props) {
  const [owner, setOwner] = useState('');
  const [account, setAccount] = useState('');
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [side, setSide] = useState<TradeSideFilter>('');
  const [refreshKey, setRefreshKey] = useState(0);
  const [formValues, setFormValues] = useState<TransactionFormValues>(
    EMPTY_TRANSACTION_FORM_VALUES
  );
  const [submitting, setSubmitting] = useState(false);
  const [manualSubmitting, setManualSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [formSuccess, setFormSuccess] = useState<string | null>(null);
  const [manualError, setManualError] = useState<string | null>(null);
  const [manualSuccess, setManualSuccess] = useState<string | null>(null);
  const [manualAccounts, setManualAccounts] = useState<
    Array<{
      account_type: string;
      currency: string;
      holdings: Array<Record<string, unknown>>;
      holding_count: number;
    }>
  >([]);
  const [manualOwner, setManualOwner] = useState('');
  const [manualAccount, setManualAccount] = useState('');
  const [manualTicker, setManualTicker] = useState('');
  const [manualValue, setManualValue] = useState('');
  const [manualUnits, setManualUnits] = useState('');
  const [manualPrice, setManualPrice] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const { t } = useTranslation();
  const reporting = useReportingCurrency();
  const { user } = useAuth();
  const { demoReadOnly, reason } = useDemoReadOnly();
  const pageSizeOptions = [10, 20, 50, 100];
  const ownerLookup = useMemo(() => createOwnerDisplayLookup(owners), [owners]);

  const resetForm = useCallback(() => {
    setFormValues({ ...EMPTY_TRANSACTION_FORM_VALUES });
  }, []);

  const fetchTransactions = useCallback(
    () =>
      inputOnly
        ? Promise.resolve([])
        : getTransactions({
            owner: owner || undefined,
            account: account || undefined,
            start: start || undefined,
            end: end || undefined,
          }),
    [account, end, inputOnly, owner, start]
  );

  const {
    data: fetchedTransactions,
    loading,
    error,
  } = useFetch<Transaction[]>(fetchTransactions, [
    owner,
    account,
    start,
    end,
    refreshKey,
  ]);

  const transactions = useMemo(
    () =>
      fetchedTransactions
        ? filterAndSortTransactions(fetchedTransactions, side)
        : fetchedTransactions,
    [fetchedTransactions, side]
  );

  const {
    pageSize,
    setPageSize,
    resetToFirstPage,
    selectedIds,
    setSelectedIds,
    transactionById,
    paginatedTransactions,
    allPageIds,
    selectedCount,
    hasSelection,
    isAllPageSelected,
    isFirstPage,
    isLastPage,
    showingRangeLabel,
    currentPageDisplay,
    totalPagesDisplay,
    handleToggleSelect,
    handleToggleSelectAllOnPage,
    handlePreviousPage,
    handleNextPage,
  } = useTransactionsTableState(transactions ?? undefined);

  useEffect(() => {
    resetToFirstPage();
  }, [owner, account, start, end, side, pageSize, resetToFirstPage]);

  const summary = useMemo(
    () => summariseTransactions(transactions ?? []),
    [transactions]
  );

  const accountOptions = useMemo(() => {
    if (owner) {
      return owners.find((entry) => entry.owner === owner)?.accounts ?? [];
    }
    const options = new Set<string>();
    owners.forEach((entry) =>
      entry.accounts.forEach((value) => options.add(value))
    );
    return Array.from(options);
  }, [owner, owners]);

  const handleOwnerChange = useCallback<ChangeEventHandler<HTMLSelectElement>>(
    (event) => setOwner(event.target.value),
    []
  );

  const handleAccountChange = useCallback<
    ChangeEventHandler<HTMLSelectElement>
  >((event) => setAccount(event.target.value), []);

  const handleFormFieldChange = useCallback(
    <K extends keyof TransactionFormValues>(field: K) =>
      (event: ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
        const nextValue =
          field === 'ticker'
            ? event.target.value.toUpperCase()
            : event.target.value;
        setFormValues((current) => ({ ...current, [field]: nextValue }));
      },
    []
  );

  const setFilterOwnerAndAccount = useCallback(
    (nextOwner: string, nextAccount: string) => {
      setOwner(nextOwner);
      setAccount(nextAccount);
    },
    []
  );

  const handleEdit = useCallback(
    (transaction: Transaction) => {
      if (!transaction.id) {
        return;
      }
      setFilterOwnerAndAccount(transaction.owner, transaction.account ?? '');
      setEditingId(transaction.id);
      setFormValues(createTransactionFormValues(transaction));
      setFormError(null);
      setFormSuccess(null);
    },
    [setFilterOwnerAndAccount]
  );

  const fetchManualAccounts = useCallback(async (ownerValue: string) => {
    const trimmedOwner = ownerValue.trim();
    if (!trimmedOwner) {
      setManualAccounts([]);
      return;
    }
    try {
      const response = await getManualHoldings(trimmedOwner);
      setManualAccounts(response.accounts);
      setManualError(null);
    } catch (err) {
      setManualError(
        err instanceof Error ? err.message : t('transactionsPage.loadManualFailed')
      );
    }
  }, [t]);

  useEffect(() => {
    if (owners.length === 0) {
      return;
    }
    const defaultOwner =
      findOwnerForUser(owners, user)?.owner ?? owners[0].owner;
    setManualOwner((current) => current || defaultOwner);
  }, [owners, user]);

  useEffect(() => {
    void fetchManualAccounts(manualOwner);
  }, [fetchManualAccounts, manualOwner]);

  const handleSaveManualHolding = useCallback(async () => {
    const trimmedOwner = manualOwner.trim();
    const trimmedAccount = manualAccount.trim();
    const ticker = manualTicker.trim().toUpperCase();

    setManualError(null);
    setManualSuccess(null);

    if (!trimmedOwner || !trimmedAccount || !ticker) {
      setManualError(t('transactionsPage.requiredFields'));
      return;
    }

    const hasValueInput = manualValue.trim() !== '';
    const hasUnitsInput = manualUnits.trim() !== '';
    const hasPriceInput = manualPrice.trim() !== '';
    const value = Number(manualValue);
    const units = Number(manualUnits);
    const price = Number(manualPrice);

    if (hasValueInput && (!Number.isFinite(value) || value <= 0)) {
      setManualError(t('transactionsPage.valuePositive'));
      return;
    }
    if (hasUnitsInput !== hasPriceInput) {
      setManualError(t('transactionsPage.unitsAndPrice'));
      return;
    }
    if (hasUnitsInput && (!Number.isFinite(units) || units <= 0)) {
      setManualError(t('transactionsPage.unitsPositive'));
      return;
    }
    if (hasPriceInput && (!Number.isFinite(price) || price <= 0)) {
      setManualError(t('transactionsPage.pricePositive'));
      return;
    }

    const hasValue = hasValueInput;
    const hasUnitsPrice = hasUnitsInput && hasPriceInput;
    if (!hasValue && !hasUnitsPrice) {
      setManualError(t('transactionsPage.valueOrUnitsPrice'));
      return;
    }

    setManualSubmitting(true);
    try {
      await createManualHolding(
        hasValue
          ? {
              owner: trimmedOwner,
              account: trimmedAccount,
              ticker,
              value_gbp: value,
            }
          : {
              owner: trimmedOwner,
              account: trimmedAccount,
              ticker,
              units,
              price_gbp: price,
            }
      );
      setManualSuccess(t('transactionsPage.holdingSaved'));
      setManualTicker('');
      setManualValue('');
      setManualUnits('');
      setManualPrice('');
      await fetchManualAccounts(trimmedOwner);
    } catch (err) {
      setManualError(
        err instanceof Error ? err.message : t('transactionsPage.saveHoldingFailed')
      );
    } finally {
      setManualSubmitting(false);
    }
  }, [
    fetchManualAccounts,
    manualAccount,
    manualOwner,
    manualPrice,
    manualTicker,
    manualUnits,
    manualValue,
    t,
  ]);

  const handleCancelEdit = useCallback(() => {
    setEditingId(null);
    resetForm();
    setFormError(null);
    setFormSuccess(null);
  }, [resetForm]);

  const handleDelete = useCallback(
    async (transaction: Transaction) => {
      if (!transaction.id) {
        return;
      }
      if (
        typeof window !== 'undefined' &&
        !window.confirm(t('transactionsPage.confirmDelete'))
      ) {
        return;
      }
      setFormError(null);
      setFormSuccess(null);
      try {
        await deleteTransaction(transaction.id);
        if (editingId === transaction.id) {
          setEditingId(null);
          resetForm();
        }
        setFormSuccess(t('transactionsPage.deleted'));
        setFilterOwnerAndAccount(transaction.owner, transaction.account ?? '');
        setRefreshKey((key) => key + 1);
      } catch (err) {
        setFormError(
          err instanceof Error ? err.message : t('transactionsPage.deleteFailed')
        );
      }
    },
    [editingId, resetForm, setFilterOwnerAndAccount, t]
  );

  const validatePayload = useCallback(() => {
    if (!owner || !account) {
      setFormError(t('transactionsPage.selectOwnerAccount'));
      return null;
    }
    const result = buildTransactionPayload(formValues, owner, account);
    if (result.error) {
      setFormError(result.error);
      return null;
    }
    return result.payload;
  }, [account, formValues, owner, t]);

  const handleBulkDelete = useCallback(async () => {
    if (!hasSelection) {
      return;
    }
    if (
      typeof window !== 'undefined' &&
      !window.confirm(
        t('transactionsPage.confirmBulkDelete', { count: selectedCount })
      )
    ) {
      return;
    }
    setFormError(null);
    setFormSuccess(null);
    try {
      for (const id of buildBulkDeletionOrder(selectedIds)) {
        await deleteTransaction(id);
      }
      if (editingId && selectedIds.includes(editingId)) {
        setEditingId(null);
        resetForm();
      }
      const firstSelected = selectedIds[0]
        ? transactionById.get(selectedIds[0])
        : null;
      if (firstSelected) {
        setFilterOwnerAndAccount(
          firstSelected.owner,
          firstSelected.account ?? ''
        );
      }
      setSelectedIds([]);
      setFormSuccess(
        t('transactionsPage.bulkDeleted', { count: selectedCount })
      );
      setRefreshKey((key) => key + 1);
    } catch (err) {
      setFormError(
        err instanceof Error
          ? err.message
          : t('transactionsPage.bulkDeleteFailed')
      );
    }
  }, [
    editingId,
    hasSelection,
    resetForm,
    selectedCount,
    selectedIds,
    setFilterOwnerAndAccount,
    setSelectedIds,
    t,
    transactionById,
  ]);

  const handleApplyToSelected = useCallback(async () => {
    if (!hasSelection) {
      return;
    }
    const payload = validatePayload();
    if (!payload) {
      return;
    }
    if (
      typeof window !== 'undefined' &&
      !window.confirm(
        t('transactionsPage.confirmBulkUpdate', { count: selectedCount })
      )
    ) {
      return;
    }
    setFormError(null);
    setFormSuccess(null);
    setSubmitting(true);
    try {
      await Promise.all(
        selectedIds.map((id) => updateTransaction(id, payload))
      );
      if (editingId && selectedIds.includes(editingId)) {
        setEditingId(null);
      }
      setFilterOwnerAndAccount(payload.owner, payload.account);
      setSelectedIds([]);
      setFormSuccess(
        t('transactionsPage.bulkUpdated', { count: selectedCount })
      );
      setRefreshKey((key) => key + 1);
    } catch (err) {
      setFormError(
        err instanceof Error
          ? err.message
          : t('transactionsPage.bulkUpdateFailed')
      );
    } finally {
      setSubmitting(false);
    }
  }, [
    editingId,
    hasSelection,
    selectedCount,
    selectedIds,
    setFilterOwnerAndAccount,
    setSelectedIds,
    t,
    validatePayload,
  ]);

  const handleSubmit = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      setFormError(null);
      setFormSuccess(null);

      const payload = validatePayload();
      if (!payload) {
        return;
      }
      setSubmitting(true);
      try {
        if (editingId) {
          await updateTransaction(editingId, payload);
          setFormSuccess(t('transactionsPage.updated'));
          setEditingId(null);
        } else {
          await createTransaction(payload);
          setFormSuccess(t('transactionsPage.created'));
        }
        setFilterOwnerAndAccount(payload.owner, payload.account);
        resetForm();
        setRefreshKey((key) => key + 1);
      } catch (err) {
        const defaultMessage = editingId
          ? t('transactionsPage.updateFailed')
          : t('transactionsPage.createFailed');
        setFormError(err instanceof Error ? err.message : defaultMessage);
      } finally {
        setSubmitting(false);
      }
    },
    [editingId, resetForm, setFilterOwnerAndAccount, t, validatePayload]
  );

  const manualHoldingsSection = (
    <section className={`mb-6 ${surface.surfaceCard}`}>
      <h2 className={`mb-2 text-lg font-semibold ${surface.surfaceCardTitle}`}>
        {t('transactionsPage.inputTitle')}
      </h2>
      <p className={`mb-3 text-sm ${surface.surfaceMuted}`}>
        <Trans
          i18nKey="transactionsPage.inputIntro"
          components={{ txlink: <Link to="/transactions" /> }}
        />
      </p>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        <label className="text-sm">
          {t('transactionsPage.owner')}
          <input
            list="manual-owner-options"
            className="mt-1 w-full rounded border border-slate-300 p-2"
            value={manualOwner}
            onChange={(event) => setManualOwner(event.target.value)}
            placeholder="alice"
          />
          <datalist id="manual-owner-options">
            {owners.map((entry) => (
              <option key={entry.owner} value={entry.owner} />
            ))}
          </datalist>
        </label>
        <label className="text-sm">
          {t('transactionsPage.account')}
          <input
            className="mt-1 w-full rounded border border-slate-300 p-2"
            value={manualAccount}
            onChange={(event) => setManualAccount(event.target.value)}
            placeholder="ISA"
          />
        </label>
        <label className="text-sm">
          {t('transactionsPage.ticker')}
          <input
            className="mt-1 w-full rounded border border-slate-300 p-2 uppercase"
            value={manualTicker}
            onChange={(event) =>
              setManualTicker(event.target.value.toUpperCase())
            }
            placeholder="VUSA.L"
          />
        </label>
        <label className="text-sm">
          {t('transactionsPage.valueGbp')}
          <input
            className="mt-1 w-full rounded border border-slate-300 p-2"
            value={manualValue}
            onChange={(event) => setManualValue(event.target.value)}
            placeholder="1250"
          />
        </label>
        <label className="text-sm">
          {t('transactionsPage.units')}
          <input
            className="mt-1 w-full rounded border border-slate-300 p-2"
            value={manualUnits}
            onChange={(event) => setManualUnits(event.target.value)}
            placeholder="10"
          />
        </label>
        <label className="text-sm">
          {t('transactionsPage.priceGbp')}
          <input
            className="mt-1 w-full rounded border border-slate-300 p-2"
            value={manualPrice}
            onChange={(event) => setManualPrice(event.target.value)}
            placeholder="120.50"
          />
        </label>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button
          type="button"
          className="rounded bg-slate-900 px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
          disabled={manualSubmitting || demoReadOnly}
          title={reason()}
          onClick={() => void handleSaveManualHolding()}
        >
          {manualSubmitting
            ? t('transactionsPage.saving')
            : t('transactionsPage.saveHolding')}
        </button>
        {manualError && <p className="text-sm text-red-700">{manualError}</p>}
        {manualSuccess && (
          <p className="text-sm text-emerald-700">{manualSuccess}</p>
        )}
      </div>
      <div className="mt-4 space-y-2">
        <h3 className="text-sm font-semibold">{t('transactionsPage.savedAccounts')}</h3>
        {manualAccounts.length === 0 ? (
          <p className={`text-sm ${surface.surfaceMuted}`}>
            {t('transactionsPage.noSavedAccounts')}
          </p>
        ) : (
          <ul className="space-y-2">
            {manualAccounts.map((entry) => (
              <li
                key={entry.account_type}
                className="rounded border border-[var(--surface-card-border)] p-2 text-sm"
              >
                <div className="font-medium">
                  {t('transactionsPage.accountSummary', {
                    account: entry.account_type.toUpperCase(),
                    holdingCount: entry.holding_count,
                  })}
                </div>
                <div className={surface.surfaceMuted}>{entry.currency}</div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );

  return (
    <div>
      {inputOnly && manualHoldingsSection}
      {!inputOnly && (
        <>
          <p className={`mb-3 text-sm ${surface.surfaceMuted}`}>
            <Link to="/input">{t('transactionsPage.inputLink')}</Link>
          </p>
          <TransactionsFilters
            owner={owner}
            account={account}
            start={start}
            end={end}
            owners={owners}
            ownerLookup={ownerLookup}
            accountOptions={accountOptions}
            ownerLabel={t('owner.label')}
            startLabel={t('query.start')}
            endLabel={t('query.end')}
            onOwnerChange={handleOwnerChange}
            onAccountChange={handleAccountChange}
            onStartChange={(event) => setStart(event.target.value)}
            onEndChange={(event) => setEnd(event.target.value)}
            side={side}
            onSideChange={(event) =>
              setSide(event.target.value as TradeSideFilter)
            }
            ownerAccountLocked={Boolean(editingId)}
          />

          <TransactionEditorForm
            values={formValues}
            activeOwner={owner}
            activeAccount={account}
            editingId={editingId}
            hasSelection={hasSelection}
            selectedCount={selectedCount}
            submitting={submitting}
            onSubmit={handleSubmit}
            onFieldChange={handleFormFieldChange}
            onCancelEdit={handleCancelEdit}
            onApplyToSelected={handleApplyToSelected}
          />

          {editingId && (
            <p style={{ color: '#ffd24d' }}>
              {t('transactionsPage.editingNotice')}
            </p>
          )}

          {formError && <p style={{ color: 'red' }}>{formError}</p>}
          {formSuccess && <p style={{ color: 'limegreen' }}>{formSuccess}</p>}
          {error && <p style={{ color: 'red' }}>{error.message}</p>}

          {!loading && (transactions?.length ?? 0) > 0 && (
            <p data-testid="transactions-summary">
              {t('transactionsPage.realisedGainLoss')}{' '}
              <strong
                className={
                  summary.realisedGain > 0
                    ? 'text-positive'
                    : summary.realisedGain < 0
                      ? 'text-negative'
                      : 'text-gray'
                }
              >
                {reporting.format(summary.realisedGain)}
              </strong>
              {summary.sellsWithUnknownGain > 0 &&
                ` ${t('transactionsPage.excludesUnknownSales', {
                  count: summary.sellsWithUnknownGain,
                })}`}
              {' · '}
              {t('transactionsPage.income')} {reporting.format(summary.income)}
              {' · '}
              {t('transactionsPage.fees')} {reporting.format(summary.fees)}
            </p>
          )}

          {loading ? (
            <p>{t('common.loading')}</p>
          ) : (
            <TransactionsTable
              transactions={paginatedTransactions}
              format={reporting.format}
              ownerLookup={ownerLookup}
              pageSize={pageSize}
              pageSizeOptions={pageSizeOptions}
              showingRangeLabel={showingRangeLabel}
              currentPageDisplay={currentPageDisplay}
              totalPagesDisplay={totalPagesDisplay}
              isFirstPage={isFirstPage}
              isLastPage={isLastPage}
              hasSelection={hasSelection}
              selectedCount={selectedCount}
              selectedIds={selectedIds}
              isAllPageSelected={isAllPageSelected}
              allPageIds={allPageIds}
              onPageSizeChange={setPageSize}
              onBulkDelete={handleBulkDelete}
              onPreviousPage={handlePreviousPage}
              onNextPage={handleNextPage}
              onToggleSelectAllOnPage={handleToggleSelectAllOnPage}
              onToggleSelect={handleToggleSelect}
              onEdit={handleEdit}
              onDelete={handleDelete}
            />
          )}
        </>
      )}
    </div>
  );
}
