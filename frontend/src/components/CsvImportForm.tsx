import { useId, useState, type ChangeEvent, type FormEvent } from "react";
import { importHoldingsCsv } from "../api";

/** Provider keys supported by `backend/importers`, excluding the `test` stub. */
const PROVIDERS = [
  { value: "degiro", label: "DEGIRO" },
  { value: "hargreaves", label: "Hargreaves Lansdown" },
];

type Props = {
  owner: string;
  accountTypes: string[];
  onImported?: () => void;
};

type Status =
  | { kind: "idle" }
  | { kind: "submitting" }
  | { kind: "success"; path: string }
  | { kind: "error"; message: string };

const extractErrorMessage = (err: unknown): string => {
  if (err instanceof Error) return err.message;
  return "Failed to import file. Please try again.";
};

/** Form for uploading a CSV of holdings/transactions to `POST /holdings/import`. */
export function CsvImportForm({ owner, accountTypes, onImported }: Props) {
  const [account, setAccount] = useState(accountTypes[0] ?? "");
  const [provider, setProvider] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [status, setStatus] = useState<Status>({ kind: "idle" });
  const formId = useId();

  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    setFile(e.target.files?.[0] ?? null);
  };

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!account || !provider || !file) return;

    setStatus({ kind: "submitting" });
    try {
      const result = await importHoldingsCsv(owner, account, provider, file);
      setStatus({ kind: "success", path: result.path });
      setFile(null);
      onImported?.();
    } catch (err) {
      setStatus({ kind: "error", message: extractErrorMessage(err) });
    }
  };

  const submitting = status.kind === "submitting";
  const canSubmit = Boolean(account && provider && file) && !submitting;

  return (
    <div className="rounded-lg border border-gray-800 bg-black/20 p-3">
      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
        Import CSV
      </p>
      <form onSubmit={handleSubmit} className="flex flex-wrap items-end gap-2">
        <div>
          <label
            htmlFor={`${formId}-account`}
            className="block text-xs text-gray-400"
          >
            Account
          </label>
          <select
            id={`${formId}-account`}
            value={account}
            onChange={(e) => setAccount(e.target.value)}
            className="rounded border border-gray-700 bg-gray-800 p-1 text-white"
          >
            {accountTypes.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label
            htmlFor={`${formId}-provider`}
            className="block text-xs text-gray-400"
          >
            Provider
          </label>
          <select
            id={`${formId}-provider`}
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
            className="rounded border border-gray-700 bg-gray-800 p-1 text-white"
          >
            <option value="">Select provider…</option>
            {PROVIDERS.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor={`${formId}-file`} className="block text-xs text-gray-400">
            CSV file
          </label>
          <input
            id={`${formId}-file`}
            type="file"
            accept=".csv,text/csv"
            onChange={handleFileChange}
            className="text-white"
          />
        </div>
        <button
          type="submit"
          disabled={!canSubmit}
          className="rounded border border-gray-700 px-3 py-1 text-white hover:border-gray-500 hover:bg-gray-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-400 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {submitting ? "Importing…" : "Import"}
        </button>
      </form>
      {status.kind === "success" && (
        <p role="status" className="mt-2 text-sm text-green-400">
          Imported successfully. Saved to {status.path}.
        </p>
      )}
      {status.kind === "error" && (
        <p role="alert" className="mt-2 text-sm text-red-500">
          {status.message}
        </p>
      )}
    </div>
  );
}

export default CsvImportForm;
