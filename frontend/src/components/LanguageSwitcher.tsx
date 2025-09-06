import { useEffect, useState, memo } from "react";
import i18n from "i18next";
import "./LanguageSwitcher.css";

const LANGUAGES = [
  { code: "en", flag: "/flags/en.svg" },
  { code: "fr", flag: "/flags/fr.svg" },
  { code: "de", flag: "/flags/de.svg" },
  { code: "es", flag: "/flags/es.svg" },
  { code: "pt", flag: "/flags/pt.svg" },
  { code: "it", flag: "/flags/it.svg" },
];

export const LanguageSwitcher = memo(function LanguageSwitcher() {
  const [current, setCurrent] = useState(i18n.language);
  const [open, setOpen] = useState(false);

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

  const currentLang =
    LANGUAGES.find((l) => l.code === current) || LANGUAGES[0];

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
        aria-label={currentLang.code}
      >
        <img
          src={currentLang.flag}
          alt={currentLang.code}
          width={24}
          height={24}
        />
      </button>
      {open && (
        <div className="language-menu">
          {LANGUAGES.filter((l) => l.code !== current).map((l) => (
            <button
              key={l.code}
              onClick={() => selectLanguage(l.code)}
              className="language-btn"
              aria-label={l.code}
            >
              <img src={l.flag} alt={l.code} width={24} height={24} />
            </button>
          ))}
        </div>
      )}
    </div>
  );
});

