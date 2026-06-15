import { useState } from "react";
import type { FormEvent } from "react";
import { createAccount } from "../api";

const ACCOUNT_TYPES = ["isa", "sipp", "brokerage", "savings"] as const;
const ACCOUNT_TYPE_PATTERN = /^[a-z0-9_-]+$/;

type Props = {
  owner: string;
  onCreated: (accountType: string) => void;
  onCancel?: () => void;
};

export function AddAccountForm({ owner, onCreated, onCancel }: Props) {
  const [accountType, setAccountType] = useState<string>(ACCOUNT_TYPES[0]);
  const [customType, setCustomType] = useState("");
  const [currency, setCurrency] = useState("GBP");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const isCustom = accountType === "other";
  const resolvedType = (isCustom ? customType : accountType).trim().toLowerCase();

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();

    if (!resolvedType) {
      setError("Please choose or enter an account type.");
      return;
    }
    if (!ACCOUNT_TYPE_PATTERN.test(resolvedType)) {
      setError("Account type may only contain lowercase letters, numbers, '-' and '_'.");
      return;
    }

    setError(null);
    setSubmitting(true);
    try {
      const result = await createAccount({
        owner,
        account_type: resolvedType,
        currency: currency.trim() || undefined,
      });
      onCreated(result.account);
    } catch (err) {
      const status = (err as { status?: number } | undefined)?.status;
      if (status === 409) {
        setError(`An account of type "${resolvedType}" already exists.`);
      } else if (status === 400) {
        setError("That account type is not valid. Please choose a different name.");
      } else {
        setError("Something went wrong creating the account. Please try again.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3 rounded-lg border border-gray-800 bg-black/20 p-4">
      {error && (
        <div role="alert" aria-live="assertive" className="text-sm text-red-500">
          {error}
        </div>
      )}
      <div>
        <label htmlFor="add-account-type" className="mb-1 block text-sm text-gray-300">
          Account type
        </label>
        <select
          id="add-account-type"
          value={accountType}
          onChange={(e) => setAccountType(e.target.value)}
          className="w-full rounded border border-gray-700 bg-gray-800 p-2 text-white"
        >
          {ACCOUNT_TYPES.map((type) => (
            <option key={type} value={type}>
              {type.toUpperCase()}
            </option>
          ))}
          <option value="other">Other…</option>
        </select>
      </div>
      {isCustom && (
        <div>
          <label htmlFor="add-account-custom-type" className="mb-1 block text-sm text-gray-300">
            Custom account type
          </label>
          <input
            id="add-account-custom-type"
            type="text"
            value={customType}
            onChange={(e) => setCustomType(e.target.value)}
            placeholder="e.g. junior-isa"
            className="w-full rounded border border-gray-700 bg-gray-800 p-2 text-white"
          />
        </div>
      )}
      <div>
        <label htmlFor="add-account-currency" className="mb-1 block text-sm text-gray-300">
          Currency (optional)
        </label>
        <input
          id="add-account-currency"
          type="text"
          value={currency}
          onChange={(e) => setCurrency(e.target.value.toUpperCase())}
          placeholder="GBP"
          maxLength={3}
          className="w-24 rounded border border-gray-700 bg-gray-800 p-2 text-white"
        />
      </div>
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={submitting}
          className="rounded bg-blue-600 px-3 py-1 text-white hover:bg-blue-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-400 disabled:opacity-60"
        >
          {submitting ? "Creating…" : "Add account"}
        </button>
        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            className="rounded border border-gray-700 px-3 py-1 text-white hover:border-gray-500 hover:bg-gray-800"
          >
            Cancel
          </button>
        )}
      </div>
    </form>
  );
}

export default AddAccountForm;
