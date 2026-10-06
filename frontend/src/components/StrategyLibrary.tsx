// Strategy library for the strategy page (#9653): built-in (read-only) and
// user strategies, with Apply / Duplicate / Edit / Delete. Applying a
// strategy replaces the owner's target allocation.
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  applyStrategy,
  createStrategy,
  deleteStrategy,
  duplicateStrategy,
  updateStrategy,
} from '../api';
import type { ActiveStrategy, Strategy, StrategyList } from '../types';
import {
  ASSET_CLASSES,
  draftFromTargets,
  draftTotalOk,
  targetsFromDraft,
} from '../lib/allocationTargets';
import { SUB_ASSET_CLASSES, allocationKeyLabel } from '../lib/assetClass';
import TargetFields from './TargetFields';

const pct = new Intl.NumberFormat('en-GB', { maximumFractionDigits: 2 });

const errorText = (error: unknown) =>
  error instanceof Error ? error.message : String(error);

/** Every class and sub-class key in display order (stored targets are key-sorted). */
const KEY_ORDER = ASSET_CLASSES.flatMap(({ key }) => [
  key,
  ...(SUB_ASSET_CLASSES[key] ?? []).map((sub) => sub.key),
]);
const keyRank = (key: string) => {
  const rank = KEY_ORDER.indexOf(key);
  return rank < 0 ? KEY_ORDER.length : rank;
};

function formatStrategyTargets(targets: Record<string, number>): string {
  return Object.entries(targets)
    .sort(([a], [b]) => keyRank(a) - keyRank(b))
    .map(([key, value]) => `${allocationKeyLabel(key)} ${pct.format(value)}%`)
    .join(' · ');
}

function Badge({ children, tone }: { children: string; tone: string }) {
  return (
    <span className={`ml-2 rounded px-1.5 py-0.5 text-xs ${tone}`}>
      {children}
    </span>
  );
}

const TONES = {
  builtin: 'bg-slate-200 text-slate-800 dark:bg-slate-700 dark:text-slate-100',
  custom: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-100',
  active: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-100',
  modified: 'bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-100',
};

/** Which strategy the targets came from, and whether they changed since. */
function ActiveStrategyStatus({
  active,
  hasTargets,
}: {
  active: ActiveStrategy | null;
  hasTargets: boolean;
}) {
  const { t } = useTranslation();
  if (!active) {
    return (
      <p
        className="mb-3 text-sm"
        aria-label={t('strategyLibrary.active.label')}
      >
        <span className="font-medium">
          {t('strategyLibrary.active.prefix')}
        </span>{' '}
        {hasTargets
          ? t('strategyLibrary.active.custom')
          : t('strategyLibrary.active.none')}
      </p>
    );
  }
  return (
    <div
      className="mb-3 text-sm"
      aria-label={t('strategyLibrary.active.label')}
    >
      <p>
        <span className="font-medium">
          {t('strategyLibrary.active.prefix')}
        </span>{' '}
        {active.name}
        {!active.exists && ` ${t('strategyLibrary.active.deleted')}`}
        {active.modified && (
          <Badge tone={TONES.modified}>
            {t('strategyLibrary.active.modified')}
          </Badge>
        )}
      </p>
      {active.modified && (
        <p className="text-xs text-amber-700 dark:text-amber-300">
          {t('strategyLibrary.active.modifiedHelp')}
        </p>
      )}
      {active.strategy_changed && (
        <p className="text-xs text-amber-700 dark:text-amber-300">
          {t('strategyLibrary.active.changedHelp')}
        </p>
      )}
    </div>
  );
}

function StrategyEditor({
  initial,
  current,
  onSave,
  onCancel,
}: {
  initial: Strategy | null;
  current: Record<string, number>;
  onSave: (input: {
    name: string;
    description: string;
    targets: Record<string, number>;
  }) => Promise<void>;
  onCancel: () => void;
}) {
  const { t } = useTranslation();
  const [name, setName] = useState(initial?.name ?? '');
  const [description, setDescription] = useState(initial?.description ?? '');
  const [draft, setDraft] = useState(() =>
    draftFromTargets(initial?.targets ?? {})
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await onSave({
        name: name.trim(),
        description: description.trim(),
        targets: targetsFromDraft(draft),
      });
    } catch (err) {
      setError(errorText(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="mb-4 rounded border p-3"
      aria-label={
        initial
          ? t('strategyLibrary.editor.edit', { name: initial.name })
          : t('strategyLibrary.new')
      }
    >
      <h3 className="mb-2 font-medium">
        {initial
          ? t('strategyLibrary.editor.edit', { name: initial.name })
          : t('strategyLibrary.new')}
      </h3>
      <label className="mb-2 block text-sm">
        {t('strategyLibrary.editor.name')}
        <input
          className="mt-1 block w-full border p-1"
          value={name}
          maxLength={80}
          onChange={(e) => setName(e.target.value)}
        />
      </label>
      <label className="mb-2 block text-sm">
        {t('strategyLibrary.editor.description')}
        <textarea
          className="mt-1 block w-full border p-1"
          value={description}
          maxLength={1000}
          onChange={(e) => setDescription(e.target.value)}
        />
      </label>
      <TargetFields
        draft={draft}
        onChange={setDraft}
        current={current}
        inputLabel={t('strategyLibrary.editor.inputLabel')}
      />
      <div className="mt-2 flex gap-2">
        <button
          type="submit"
          disabled={saving || !name.trim() || !draftTotalOk(draft)}
          className="rounded bg-blue-500 px-4 py-1 text-white disabled:opacity-50"
        >
          {saving
            ? t('strategyLibrary.editor.saving')
            : t('strategyLibrary.editor.save')}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded bg-gray-200 px-3 py-1 text-slate-900"
        >
          {t('strategyLibrary.editor.cancel')}
        </button>
      </div>
      {error && (
        <p className="mt-2 break-words text-sm text-red-600">{error}</p>
      )}
    </form>
  );
}

/** Edit/Delete for a user strategy; disabled with a tooltip for a built-in. */
function OwnedAction({
  strategy,
  label,
  onClick,
}: {
  strategy: Strategy;
  label: string;
  onClick: () => void;
}) {
  const { t } = useTranslation();
  return (
    <span
      title={
        strategy.builtin ? t('strategyLibrary.builtinReadOnlyTip') : undefined
      }
    >
      <button
        type="button"
        disabled={strategy.builtin}
        onClick={onClick}
        aria-label={`${label} ${strategy.name}`}
        className="rounded bg-gray-200 px-2 py-1 text-sm text-slate-900 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {label}
      </button>
    </span>
  );
}

interface RowActions {
  apply: (s: Strategy) => void;
  duplicate: (s: Strategy) => void;
  edit: (s: Strategy) => void;
  remove: (s: Strategy) => void;
}

function StrategyRow({
  strategy,
  isActive,
  busy,
  actions,
}: {
  strategy: Strategy;
  isActive: boolean;
  busy: boolean;
  actions: RowActions;
}) {
  const { t } = useTranslation();
  return (
    <li className="border-b py-2 last:border-b-0">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <span className="font-medium">{strategy.name}</span>
          {strategy.builtin ? (
            <Badge tone={TONES.builtin}>
              {t('strategyLibrary.row.builtin')}
            </Badge>
          ) : (
            <Badge tone={TONES.custom}>{t('strategyLibrary.row.custom')}</Badge>
          )}
          {isActive && (
            <Badge tone={TONES.active}>{t('strategyLibrary.row.active')}</Badge>
          )}
          <p className="text-xs text-slate-600 dark:text-slate-300">
            {formatStrategyTargets(strategy.targets)}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={() => actions.apply(strategy)}
            aria-label={t('strategyLibrary.row.applyAria', {
              name: strategy.name,
            })}
            className="rounded bg-blue-500 px-2 py-1 text-sm text-white disabled:opacity-50"
          >
            {t('strategyLibrary.row.apply')}
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => actions.duplicate(strategy)}
            aria-label={t('strategyLibrary.row.duplicateAria', {
              name: strategy.name,
            })}
            className="rounded bg-gray-200 px-2 py-1 text-sm text-slate-900 disabled:opacity-50"
          >
            {t('strategyLibrary.row.duplicate')}
          </button>
          <OwnedAction
            strategy={strategy}
            label={t('strategyLibrary.row.edit')}
            onClick={() => actions.edit(strategy)}
          />
          <OwnedAction
            strategy={strategy}
            label={t('strategyLibrary.row.delete')}
            onClick={() => actions.remove(strategy)}
          />
        </div>
      </div>
      {(strategy.description || strategy.source || strategy.uk_mapping) && (
        <details className="mt-1 text-xs text-slate-600 dark:text-slate-300">
          <summary className="cursor-pointer">
            {t('strategyLibrary.row.about')}
          </summary>
          {strategy.description && (
            <p className="mt-1">{strategy.description}</p>
          )}
          {strategy.source && (
            <p className="mt-1">
              <span className="font-medium">
                {t('strategyLibrary.row.source')}
              </span>{' '}
              {strategy.source}
            </p>
          )}
          {strategy.uk_mapping && (
            <p className="mt-1">
              <span className="font-medium">
                {t('strategyLibrary.row.ukMapping')}
              </span>{' '}
              {strategy.uk_mapping}
            </p>
          )}
        </details>
      )}
    </li>
  );
}

type Editing = { strategy: Strategy | null } | null;

export default function StrategyLibrary({
  owner,
  data,
  current,
  hasTargets,
  onChanged,
  onApplied,
}: {
  owner: string;
  data: StrategyList;
  current: Record<string, number>;
  hasTargets: boolean;
  /** Reload strategies and the plan after anything changes. */
  onChanged: () => Promise<void>;
  /** Called after a strategy is applied and the page has reloaded. */
  onApplied?: (strategy: Strategy) => void;
}) {
  const { t } = useTranslation();
  const [editing, setEditing] = useState<Editing>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function run(action: () => Promise<string | void>, after?: () => void) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const message = await action();
      await onChanged();
      if (message) setNotice(message);
      after?.();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  const replacesCustomTargets =
    hasTargets && (data.active == null || data.active.modified);

  const actions: RowActions = {
    apply: (s) => {
      if (
        replacesCustomTargets &&
        !window.confirm(t('strategyLibrary.confirmReplace', { name: s.name }))
      )
        return;
      void run(
        async () => {
          await applyStrategy(owner, s.id);
          return t('strategyLibrary.applied', { name: s.name });
        },
        () => onApplied?.(s)
      );
    },
    duplicate: (s) =>
      void run(async () => {
        const copy = await duplicateStrategy(owner, s.id);
        setEditing({ strategy: copy });
        return t('strategyLibrary.created', { name: copy.name });
      }),
    edit: (s) => setEditing({ strategy: s }),
    remove: (s) => {
      if (!window.confirm(t('strategyLibrary.confirmDelete', { name: s.name })))
        return;
      void run(async () => {
        await deleteStrategy(owner, s.id);
        return t('strategyLibrary.deleted', { name: s.name });
      });
    },
  };

  async function save(input: {
    name: string;
    description: string;
    targets: Record<string, number>;
  }) {
    const target = editing?.strategy;
    if (target) await updateStrategy(owner, target.id, input);
    else await createStrategy(owner, input);
    setEditing(null);
    await onChanged();
  }

  return (
    <section className="mb-6" aria-label={t('strategyLibrary.title')}>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-xl">{t('strategyLibrary.title')}</h2>
        <button
          type="button"
          onClick={() => setEditing({ strategy: null })}
          className="rounded bg-gray-200 px-3 py-1 text-sm text-slate-900"
        >
          {t('strategyLibrary.new')}
        </button>
      </div>
      <ActiveStrategyStatus active={data.active} hasTargets={hasTargets} />
      <p className="mb-2 text-xs text-slate-500 dark:text-slate-400">
        {t('strategyLibrary.help')}
      </p>
      {editing && (
        <StrategyEditor
          key={editing.strategy?.id ?? 'new'}
          initial={editing.strategy}
          current={current}
          onSave={save}
          onCancel={() => setEditing(null)}
        />
      )}
      {notice && (
        <p
          className="mb-2 text-sm text-green-700 dark:text-green-400"
          role="status"
        >
          {notice}
        </p>
      )}
      {error && (
        <p className="mb-2 break-words text-sm text-red-600">{error}</p>
      )}
      <ul>
        {data.strategies.map((s) => (
          <StrategyRow
            key={s.id}
            strategy={s}
            isActive={data.active?.id === s.id}
            busy={busy}
            actions={actions}
          />
        ))}
      </ul>
    </section>
  );
}
