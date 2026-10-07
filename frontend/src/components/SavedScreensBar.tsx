import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  deleteScreen,
  renameScreen,
  saveScreen,
  useSavedScreens,
  type SavedScreen,
} from '../lib/savedScreensStore';

interface Props {
  /** Snapshot of the form as it stands now, minus the name. */
  current: Omit<SavedScreen, 'name'>;
  onLoad: (screen: SavedScreen) => void;
}

/**
 * Pick, save, update, rename and delete named screener screens. Uses
 * window.prompt/confirm like the custom-query page's "Save query".
 */
export function SavedScreensBar({ current, onLoad }: Props) {
  const { t } = useTranslation();
  const screens = useSavedScreens();
  const [active, setActive] = useState('');
  const activeExists = screens.some((s) => s.name === active);
  const selected = activeExists ? active : '';

  function promptName(message: string, initial = ''): string | null {
    const name = window.prompt(message, initial)?.trim();
    return name ? name : null;
  }

  function handleSelect(name: string) {
    setActive(name);
    const screen = screens.find((s) => s.name === name);
    if (screen) onLoad(screen);
  }

  function handleSaveAs() {
    const name = promptName(t('screener.saved.promptSave', 'Save screen as:'));
    if (!name) return;
    const exists = screens.some(
      (s) => s.name.toLowerCase() === name.toLowerCase()
    );
    if (
      exists &&
      !window.confirm(
        t(
          'screener.saved.confirmOverwrite',
          'Replace the existing screen "{{name}}"?',
          { name }
        )
      )
    ) {
      return;
    }
    saveScreen({ ...current, name });
    setActive(name);
  }

  function handleUpdate() {
    if (!selected) return;
    saveScreen({ ...current, name: selected });
  }

  function handleRename() {
    if (!selected) return;
    const name = promptName(
      t('screener.saved.promptRename', 'Rename screen to:'),
      selected
    );
    if (!name || name === selected) return;
    if (!renameScreen(selected, name)) {
      window.alert(
        t(
          'screener.saved.nameTaken',
          'A screen called "{{name}}" already exists.',
          { name }
        )
      );
      return;
    }
    setActive(name);
  }

  function handleDelete() {
    if (!selected) return;
    if (
      !window.confirm(
        t('screener.saved.confirmDelete', 'Delete the screen "{{name}}"?', {
          name: selected,
        })
      )
    ) {
      return;
    }
    deleteScreen(selected);
    setActive('');
  }

  const label = t('screener.saved.label', 'Saved screens');
  return (
    <div
      className="mb-3 flex flex-wrap items-center gap-2"
      data-testid="saved-screens"
    >
      <label className="mr-2">
        {label}
        <select
          aria-label={label}
          value={selected}
          onChange={(e) => handleSelect(e.target.value)}
          className="ml-1 border px-2 py-1"
        >
          <option value="">
            {screens.length
              ? t('screener.saved.choose', '— choose a screen —')
              : t('screener.saved.none', '— none saved yet —')}
          </option>
          {screens.map((s) => (
            <option key={s.name} value={s.name}>
              {s.name}
            </option>
          ))}
        </select>
      </label>
      <button type="button" onClick={handleSaveAs}>
        {t('screener.saved.saveAs', 'Save as…')}
      </button>
      <button type="button" onClick={handleUpdate} disabled={!selected}>
        {t('screener.saved.update', 'Update')}
      </button>
      <button type="button" onClick={handleRename} disabled={!selected}>
        {t('screener.saved.rename', 'Rename')}
      </button>
      <button type="button" onClick={handleDelete} disabled={!selected}>
        {t('screener.saved.delete', 'Delete')}
      </button>
    </div>
  );
}

export default SavedScreensBar;
