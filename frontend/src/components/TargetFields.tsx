// Target-allocation table shared by the page's target editor and the
// strategy editor (#9543, #9653): one row per asset class, with Split /
// Combine for classes that have sub-classes.
import { useTranslation } from 'react-i18next';
import {
  ASSET_CLASSES,
  draftTotal,
  draftTotalOk,
  splitTotal,
  toggleSplit,
  type TargetDraft,
} from '../lib/allocationTargets';
import { SUB_ASSET_CLASSES } from '../lib/assetClass';

const pct = new Intl.NumberFormat('en-GB', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const formatCurrent = (value: number | undefined) =>
  value == null ? '—' : `${pct.format(value)}%`;

function TargetInput({
  label,
  inputLabel,
  value,
  onChange,
}: {
  label: string;
  inputLabel: string;
  value: string;
  onChange: (value: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <input
      type="number"
      step="any"
      min="0"
      max="100"
      className="w-full border p-1"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      aria-label={t('targetFields.inputFor', { inputLabel, label })}
    />
  );
}

interface RowsProps {
  assetClass: string;
  label: string;
  draft: TargetDraft;
  current: Record<string, number>;
  inputLabel: string;
  onValue: (key: string, value: string) => void;
  onToggle: (parent: string) => void;
}

/** One asset class row, plus its sub-class rows when it is split. */
function TargetRows({
  assetClass,
  label,
  draft,
  current,
  inputLabel,
  onValue,
  onToggle,
}: RowsProps) {
  const { t } = useTranslation();
  const subs = SUB_ASSET_CLASSES[assetClass];
  const isSplit = draft.split.includes(assetClass);
  return (
    <>
      <tr>
        <td className="px-2 py-1">
          {label}
          {subs && (
            <button
              type="button"
              className="ml-2 text-xs text-blue-600 underline dark:text-blue-400"
              aria-expanded={isSplit}
              aria-label={
                isSplit
                  ? t('targetFields.combineAria', { label })
                  : t('targetFields.splitAria', { label })
              }
              onClick={() => onToggle(assetClass)}
            >
              {isSplit ? t('targetFields.combine') : t('targetFields.split')}
            </button>
          )}
        </td>
        <td className="px-2 py-1 text-right">
          {formatCurrent(current[assetClass])}
        </td>
        <td className="px-2 py-1">
          {isSplit ? (
            <span className="text-sm text-slate-500 dark:text-slate-400">
              {t('targetFields.subClassSum', {
                value: pct.format(splitTotal(draft, assetClass)),
              })}
            </span>
          ) : (
            <TargetInput
              label={label}
              inputLabel={inputLabel}
              value={draft.values[assetClass] ?? ''}
              onChange={(value) => onValue(assetClass, value)}
            />
          )}
        </td>
      </tr>
      {isSplit &&
        subs.map((sub) => (
          <tr key={sub.key}>
            <td className="px-2 py-1 pl-6">{sub.label}</td>
            <td className="px-2 py-1 text-right">
              {formatCurrent(current[sub.key])}
            </td>
            <td className="px-2 py-1">
              <TargetInput
                label={sub.label}
                inputLabel={inputLabel}
                value={draft.values[sub.key] ?? ''}
                onChange={(value) => onValue(sub.key, value)}
              />
            </td>
          </tr>
        ))}
    </>
  );
}

export default function TargetFields({
  draft,
  onChange,
  current,
  inputLabel,
}: {
  draft: TargetDraft;
  onChange: (update: (draft: TargetDraft) => TargetDraft) => void;
  current: Record<string, number>;
  /** Prefix of each input's accessible name, e.g. "Target % for Equity". */
  inputLabel?: string;
}) {
  const { t } = useTranslation();
  const resolvedInputLabel = inputLabel ?? t('targetFields.targetPct');
  const total = draftTotal(draft);
  const totalOk = draftTotalOk(draft);
  return (
    <>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse">
          <thead>
            <tr>
              <th className="px-2 py-1 text-left">
                {t('targetFields.assetClass')}
              </th>
              <th className="px-2 py-1 text-right">
                {t('targetFields.currentPct')}
              </th>
              <th className="px-2 py-1 text-left">
                {t('targetFields.targetPct')}
              </th>
            </tr>
          </thead>
          <tbody>
            {ASSET_CLASSES.map(({ key, label }) => (
              <TargetRows
                key={key}
                assetClass={key}
                label={label}
                draft={draft}
                current={current}
                inputLabel={resolvedInputLabel}
                onValue={(k, value) =>
                  onChange((d) => ({
                    ...d,
                    values: { ...d.values, [k]: value },
                  }))
                }
                onToggle={(parent) => onChange((d) => toggleSplit(d, parent))}
              />
            ))}
          </tbody>
        </table>
      </div>
      <p
        className={`mt-2 text-xs ${totalOk ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}
      >
        {t('targetFields.total', { value: pct.format(total) })}{' '}
        {totalOk ? '' : t('targetFields.mustEqual100')}
      </p>
    </>
  );
}
