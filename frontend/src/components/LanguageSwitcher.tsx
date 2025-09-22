import { useEffect, useState, memo } from "react";
import i18n from "i18next";
import "./LanguageSwitcher.css";

const base = import.meta.env.BASE_URL;

const LANGUAGES = [
  { code: "en", flag: `${base}flags/en.svg`, name: "English" },
  { code: "fr", flag: `${base}flags/fr.svg`, name: "French" },
  { code: "de", flag: `${base}flags/de.svg`, name: "German" },
  { code: "es", flag: `${base}flags/es.svg`, name: "Spanish" },
  { code: "pt", flag: `${base}flags/pt.svg`, name: "Portuguese" },
  { code: "it", flag: `${base}flags/it.svg`, name: "Italian" },
];

export const LanguageSwitcher = memo(function LanguageSwitcher() {
  const [current, setCurrent] = useState(i18n.language);
  const [open, setOpen] = useState(false);
  const [fallbackFlags, setFallbackFlags] = useState<Record<string, boolean>>({});

  useEffect(() => {
    const saved = localStorage.getItem("lang");
    if (saved) {
      i18n.changeLanguage(saved);
      setCurrent(saved);
    }
  }, []);

  function handleChange(code: string) {
    i18n.changeLanguage(code);
    localStorage.setItem("lang", code);
    setCurrent(code);
  }

  function selectLanguage(code: string) {
    handleChange(code);
    setOpen(false);
  }

  function handleFlagError(code: string) {
    setFallbackFlags((prev) =>
      prev[code]
        ? prev
        : {
            ...prev,
            [code]: true,
          }
    );
  }

  const isFallback = (code: string) => Boolean(fallbackFlags[code]);

  const currentLang =
    LANGUAGES.find((l) => l.code === current) || LANGUAGES[0];
  const currentFallback = isFallback(currentLang.code);

  return (
    <div
      style={{
        position: "relative",
        display: "flex",
        justifyContent: "flex-end",
        marginBottom: "1rem",
      }}
    >
      <button
        onClick={() => setOpen((o) => !o)}
        className="language-btn"
        aria-label={currentLang.name}
      >
        {!currentFallback && (
          <img
            src={currentLang.flag}
            alt={currentLang.name}
            width={24}
            height={24}
            onError={() => handleFlagError(currentLang.code)}
          />
        )}
        {currentFallback && (
          <span className="language-name">{currentLang.name}</span>
        )}
      </button>
      {open && (
        <div className="language-menu">
          {LANGUAGES.filter((l) => l.code !== current).map((l) => {
            const fallback = isFallback(l.code);

            return (
              <button
                key={l.code}
                onClick={() => selectLanguage(l.code)}
                className="language-btn"
                aria-label={l.name}
              >
                {!fallback && (
                  <img
                    src={l.flag}
                    alt={l.name}
                    width={24}
                    height={24}
                    onError={() => handleFlagError(l.code)}
                  />
                )}
                {fallback && (
                  <span className="language-name">{l.name}</span>
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
});

