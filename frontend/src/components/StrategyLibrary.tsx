// Strategy library for the strategy page (#9653): built-in (read-only) and
// user strategies, with Apply / Duplicate / Edit / Delete. Applying a
// strategy replaces the owner's target allocation.
import { useState } from 'react';
import {
  applyStrategy,
  createStrategy,
  deleteStrategy,
  duplicateStrategy,
  updateStrategy,
} from '../api';
import type { ActiveStrategy, Strategy, StrategyList } from '../types';
import {
  draftFromTargets,
  draftTotalOk,
  targetsFromDraft,
} from '../lib/allocationTargets';
import { allocationKeyLabel } from '../lib/assetClass';
import TargetFields from './TargetFields';

const BUILTIN_READ_ONLY_TIP =
  'Built-in strategies are read-only. Duplicate it to make an editable copy.';

const pct = new Intl.NumberFormat('en-GB', { maximumFractionDigits: 2 });

const errorText = (error: unknown) =>
  error instanceof Error ? error.message : String(error);

function formatStrategyTargets(targets: Record<string, number>): string {
  return Object.entries(targets)
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
  if (!active) {
    return (
      <p className="mb-3 text-sm" aria-label="Active strategy">
        <span className="font-medium">Active strategy:</span>{' '}
        {hasTargets
          ? 'Custom (targets not from a saved strategy)'
          : 'None — apply a strategy or set targets below.'}
      </p>
    );
  }
  return (
    <div className="mb-3 text-sm" aria-label="Active strategy">
      <p>
        <span className="font-medium">Active strategy:</span> {active.name}
        {!active.exists && ' (deleted)'}
        {active.modified && <Badge tone={TONES.modified}>Modified</Badge>}
      </p>
      {active.modified && (
        <p className="text-xs text-amber-700 dark:text-amber-300">
          Your targets have been changed since this strategy was applied.
        </p>
      )}
      {active.strategy_changed && (
        <p className="text-xs text-amber-700 dark:text-amber-300">
          The strategy has been edited since it was applied; apply it again to
          use its new weights.
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
      aria-label={initial ? `Edit ${initial.name}` : 'New strategy'}
    >
      <h3 className="mb-2 font-medium">
        {initial ? `Edit ${initial.name}` : 'New strategy'}
      </h3>
      <label className="mb-2 block text-sm">
        Name
        <input
          className="mt-1 block w-full border p-1"
          value={name}
          maxLength={80}
          onChange={(e) => setName(e.target.value)}
        />
      </label>
      <label className="mb-2 block text-sm">
        Description
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
        inputLabel="Strategy %"
      />
      <div className="mt-2 flex gap-2">
        <button
          type="submit"
          disabled={saving || !name.trim() || !draftTotalOk(draft)}
          className="rounded bg-blue-500 px-4 py-1 text-white disabled:opacity-50"
        >
          {saving ? 'Saving…' : 'Save strategy'}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded bg-gray-200 px-3 py-1 text-slate-900"
        >
          Cancel
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
  return (
    <span title={strategy.builtin ? BUILTIN_READ_ONLY_TIP : undefined}>
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
  return (
    <li className="border-b py-2 last:border-b-0">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <span className="font-medium">{strategy.name}</span>
          {strategy.builtin ? (
            <Badge tone={TONES.builtin}>Built-in</Badge>
          ) : (
            <Badge tone={TONES.custom}>Custom</Badge>
          )}
          {isActive && <Badge tone={TONES.active}>Active</Badge>}
          <p className="text-xs text-slate-600 dark:text-slate-300">
            {formatStrategyTargets(strategy.targets)}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={() => actions.apply(strategy)}
            aria-label={`Apply ${strategy.name}`}
            className="rounded bg-blue-500 px-2 py-1 text-sm text-white disabled:opacity-50"
          >
            Apply
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => actions.duplicate(strategy)}
            aria-label={`Duplicate ${strategy.name}`}
            className="rounded bg-gray-200 px-2 py-1 text-sm text-slate-900 disabled:opacity-50"
          >
            Duplicate
          </button>
          <OwnedAction
            strategy={strategy}
            label="Edit"
            onClick={() => actions.edit(strategy)}
          />
          <OwnedAction
            strategy={strategy}
            label="Delete"
            onClick={() => actions.remove(strategy)}
          />
        </div>
      </div>
      {(strategy.description || strategy.source || strategy.uk_mapping) && (
        <details className="mt-1 text-xs text-slate-600 dark:text-slate-300">
          <summary className="cursor-pointer">About this strategy</summary>
          {strategy.description && (
            <p className="mt-1">{strategy.description}</p>
          )}
          {strategy.source && (
            <p className="mt-1">
              <span className="font-medium">Source:</span> {strategy.source}
            </p>
          )}
          {strategy.uk_mapping && (
            <p className="mt-1">
              <span className="font-medium">UK mapping:</span>{' '}
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
}: {
  owner: string;
  data: StrategyList;
  current: Record<string, number>;
  hasTargets: boolean;
  /** Reload strategies and the plan after anything changes. */
  onChanged: () => Promise<void>;
}) {
  const [editing, setEditing] = useState<Editing>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function run(action: () => Promise<string | void>) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const message = await action();
      await onChanged();
      if (message) setNotice(message);
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
        !window.confirm(`Replace your current targets with ${s.name}?`)
      )
        return;
      void run(async () => {
        await applyStrategy(owner, s.id);
        return `Applied ${s.name}.`;
      });
    },
    duplicate: (s) =>
      void run(async () => {
        const copy = await duplicateStrategy(owner, s.id);
        setEditing({ strategy: copy });
        return `Created ${copy.name}.`;
      }),
    edit: (s) => setEditing({ strategy: s }),
    remove: (s) => {
      if (!window.confirm(`Delete strategy ${s.name}?`)) return;
      void run(async () => {
        await deleteStrategy(owner, s.id);
        return `Deleted ${s.name}.`;
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
    <section className="mb-6" aria-label="Strategies">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-xl">Strategies</h2>
        <button
          type="button"
          onClick={() => setEditing({ strategy: null })}
          className="rounded bg-gray-200 px-3 py-1 text-sm text-slate-900"
        >
          New strategy
        </button>
      </div>
      <ActiveStrategyStatus active={data.active} hasTargets={hasTargets} />
      <p className="mb-2 text-xs text-slate-500 dark:text-slate-400">
        Applying a strategy sets your target allocation to its weights. Built-in
        strategies describe well-known published mixes; they are reference
        points, not recommendations.
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
