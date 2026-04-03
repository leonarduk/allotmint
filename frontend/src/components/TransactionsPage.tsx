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
import { useConfig } from '../ConfigContext';
import { useTranslation } from 'react-i18next';
import { createOwnerDisplayLookup } from '../utils/owners';
import { TransactionEditorForm } from './transactions/TransactionEditorForm';
import { TransactionsFilters } from './transactions/TransactionsFilters';
import {
  buildTransactionPayload,
  createTransactionFormValues,
  EMPTY_TRANSACTION_FORM_VALUES,
  type TransactionFormValues,
} from './transactions/transactionForm';
import { buildBulkDeletionOrder } from './transactions/transactionTable';
import { TransactionsTable } from './transactions/TransactionsTable';
import { useTransactionsTableState } from '../hooks/useTransactionsTableState';

type Props = {
  owners: OwnerSummary[];
  inputOnly?: boolean;
};

export function TransactionsPage({ owners, inputOnly = false }: Props) {
  const [owner, setOwner] = useState('');
  const [account, setAccount] = useState('');
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
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
  const { baseCurrency } = useConfig();
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
    data: transactions,
    loading,
    error,
  } = useFetch<Transaction[]>(fetchTransactions, [
    owner,
    account,
    start,
    end,
    refreshKey,
  ]);

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
  }, [owner, account, start, end, pageSize, resetToFirstPage]);

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
        err instanceof Error ? err.message : 'Failed to load manual holdings.'
      );
    }
  }, []);

  useEffect(() => {
    if (owners.length === 0) {
      return;
    }
    setManualOwner((current) => current || owners[0].owner);
  }, [owners]);

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
      setManualError('Owner, account, and ticker are required.');
      return;
    }

    const hasValueInput = manualValue.trim() !== '';
    const hasUnitsInput = manualUnits.trim() !== '';
    const hasPriceInput = manualPrice.trim() !== '';
    const value = Number(manualValue);
    const units = Number(manualUnits);
    const price = Number(manualPrice);

    if (hasValueInput && (!Number.isFinite(value) || value <= 0)) {
      setManualError('Value (GBP) must be a positive number.');
      return;
    }
    if (hasUnitsInput !== hasPriceInput) {
      setManualError('Provide both Units and Price (GBP).');
      return;
    }
    if (hasUnitsInput && (!Number.isFinite(units) || units <= 0)) {
      setManualError('Units must be a positive number.');
      return;
    }
    if (hasPriceInput && (!Number.isFinite(price) || price <= 0)) {
      setManualError('Price (GBP) must be a positive number.');
      return;
    }

    const hasValue = hasValueInput;
    const hasUnitsPrice = hasUnitsInput && hasPriceInput;
    if (hasValue === hasUnitsPrice) {
      setManualError('Provide either Value (GBP) or both Units + Price (GBP).');
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
      setManualSuccess('Holding saved.');
      setManualTicker('');
      setManualValue('');
      setManualUnits('');
      setManualPrice('');
      await fetchManualAccounts(trimmedOwner);
    } catch (err) {
      setManualError(
        err instanceof Error ? err.message : 'Failed to save holding.'
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
        !window.confirm('Delete this transaction?')
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
        setFormSuccess('Transaction deleted successfully.');
        setFilterOwnerAndAccount(transaction.owner, transaction.account ?? '');
        setRefreshKey((key) => key + 1);
      } catch (err) {
        setFormError(
          err instanceof Error ? err.message : 'Failed to delete transaction.'
        );
      }
    },
    [editingId, resetForm, setFilterOwnerAndAccount]
  );

  const validatePayload = useCallback(() => {
    if (!owner || !account) {
      setFormError('Select an owner and account in the filters before saving.');
      return null;
    }
    const result = buildTransactionPayload(formValues, owner, account);
    if (result.error) {
      setFormError(result.error);
      return null;
    }
    return result.payload;
  }, [account, formValues, owner]);

  const handleBulkDelete = useCallback(async () => {
    if (!hasSelection) {
      return;
    }
    if (
      typeof window !== 'undefined' &&
      !window.confirm(
        `Delete ${selectedCount} selected transaction${selectedCount === 1 ? '' : 's'}?`
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
        `Deleted ${selectedCount} transaction${selectedCount === 1 ? '' : 's'} successfully.`
      );
      setRefreshKey((key) => key + 1);
    } catch (err) {
      setFormError(
        err instanceof Error
          ? err.message
          : 'Failed to delete selected transactions.'
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
        `Update ${selectedCount} selected transaction${selectedCount === 1 ? '' : 's'}?`
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
        `Updated ${selectedCount} transaction${selectedCount === 1 ? '' : 's'} successfully.`
      );
      setRefreshKey((key) => key + 1);
    } catch (err) {
      setFormError(
        err instanceof Error
          ? err.message
          : 'Failed to update selected transactions.'
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
          setFormSuccess('Transaction updated successfully.');
          setEditingId(null);
        } else {
          await createTransaction(payload);
          setFormSuccess('Transaction created successfully.');
        }
        setFilterOwnerAndAccount(payload.owner, payload.account);
        resetForm();
        setRefreshKey((key) => key + 1);
      } catch (err) {
        const defaultMessage = editingId
          ? 'Failed to update transaction.'
          : 'Failed to create transaction.';
        setFormError(err instanceof Error ? err.message : defaultMessage);
      } finally {
        setSubmitting(false);
      }
    },
    [editingId, resetForm, setFilterOwnerAndAccount, validatePayload]
  );

  const manualHoldingsSection = (
    <section className="mb-6 rounded border border-slate-300 bg-slate-50 p-4">
      <h2 className="mb-2 text-lg font-semibold">Account + Holdings Input</h2>
      <p className="mb-3 text-sm text-slate-600">
        Create accounts and add holdings that persist after refresh.
      </p>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        <label className="text-sm">
          Owner
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
          Account
          <input
            className="mt-1 w-full rounded border border-slate-300 p-2"
            value={manualAccount}
            onChange={(event) => setManualAccount(event.target.value)}
            placeholder="ISA"
          />
        </label>
        <label className="text-sm">
          Ticker
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
          Value (GBP)
          <input
            className="mt-1 w-full rounded border border-slate-300 p-2"
            value={manualValue}
            onChange={(event) => setManualValue(event.target.value)}
            placeholder="1250"
          />
        </label>
        <label className="text-sm">
          Units
          <input
            className="mt-1 w-full rounded border border-slate-300 p-2"
            value={manualUnits}
            onChange={(event) => setManualUnits(event.target.value)}
            placeholder="10"
          />
        </label>
        <label className="text-sm">
          Price (GBP)
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
          disabled={manualSubmitting}
          onClick={() => void handleSaveManualHolding()}
        >
          {manualSubmitting ? 'Saving...' : 'Save holding'}
        </button>
        {manualError && <p className="text-sm text-red-700">{manualError}</p>}
        {manualSuccess && (
          <p className="text-sm text-emerald-700">{manualSuccess}</p>
        )}
      </div>
      <div className="mt-4 space-y-2">
        <h3 className="text-sm font-semibold text-slate-700">Saved accounts</h3>
        {manualAccounts.length === 0 ? (
          <p className="text-sm text-slate-500">
            No saved accounts yet for this owner.
          </p>
        ) : (
          <ul className="space-y-2">
            {manualAccounts.map((entry) => (
              <li
                key={entry.account_type}
                className="rounded border border-slate-200 p-2 text-sm"
              >
                <div className="font-medium">
                  {entry.account_type.toUpperCase()} ({entry.holding_count}{' '}
                  holdings)
                </div>
                <div className="text-slate-500">{entry.currency}</div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );

  return (
    <div>
      {manualHoldingsSection}
      {!inputOnly && (
        <>
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
              Editing existing transaction. Owner and account filters are locked
              until you save or cancel.
            </p>
          )}

          {formError && <p style={{ color: 'red' }}>{formError}</p>}
          {formSuccess && <p style={{ color: 'limegreen' }}>{formSuccess}</p>}
          {error && <p style={{ color: 'red' }}>{error.message}</p>}

          {loading ? (
            <p>{t('common.loading')}</p>
          ) : (
            <TransactionsTable
              transactions={paginatedTransactions}
              baseCurrency={baseCurrency}
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
