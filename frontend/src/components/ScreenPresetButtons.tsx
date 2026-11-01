import { useTranslation } from 'react-i18next';
import { SCREEN_PRESETS, type ScreenPreset } from '../lib/screenerPresets';

interface Props {
  /** Id of the preset the form currently matches, if any. */
  activeId?: string;
  onPick: (preset: ScreenPreset) => void;
}

/**
 * One-click starting points above the screener form. Picking a preset only
 * fills the form; nothing runs until the user clicks Run.
 */
export function ScreenPresetButtons({ activeId, onPick }: Props) {
  const { t } = useTranslation();
  const label = t('screener.presets.label', 'Presets');
  const active = SCREEN_PRESETS.find((p) => p.id === activeId);
  return (
    <div className="mb-3" data-testid="screen-presets">
      <div
        role="group"
        aria-label={label}
        className="flex flex-wrap items-center gap-1"
      >
        <span className="mr-1">{label}</span>
        {SCREEN_PRESETS.map((preset) => {
          const pressed = preset.id === activeId;
          return (
            <button
              key={preset.id}
              type="button"
              aria-pressed={pressed}
              title={preset.description}
              onClick={() => onPick(preset)}
              className={`rounded px-2 py-1 text-sm ${
                pressed
                  ? // Active state: intentionally theme-independent accent colour.
                    'bg-indigo-600 text-white'
                  : 'bg-[var(--surface-muted-bg)] text-[var(--surface-muted-color)] hover:bg-[var(--menu-hover-bg)]'
              }`}
            >
              {preset.name}
            </button>
          );
        })}
      </div>
      {active && (
        <p className="mt-1 text-sm" data-testid="preset-description">
          {active.description}
        </p>
      )}
    </div>
  );
}

export default ScreenPresetButtons;
