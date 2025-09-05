import { useEffect, useState, memo } from "react";
import i18n from "i18next";
import "./LanguageSwitcher.css";

const LANGUAGES = [
  { code: "en", flag: "/flags/en.svg" },
  { code: "fr", flag: "/flags/fr.svg" },
  { code: "de", flag: "/flags/de.svg" },
  { code: "es", flag: "/flags/es.svg" },
  { code: "pt", flag: "/flags/pt.svg" },
];

export const LanguageSwitcher = memo(function LanguageSwitcher() {
  const [current, setCurrent] = useState(i18n.language);

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

  return (
    <div
      style={{
        display: "flex",
        gap: "0.5rem",
        justifyContent: "flex-end",
        marginBottom: "1rem",
      }}
    >
      {LANGUAGES.map((l) => (
        <button
          key={l.code}
          onClick={() => handleChange(l.code)}
          className="language-btn"
          style={{ opacity: current === l.code ? 1 : 0.5 }}
          aria-label={l.code}
        >
          <img
            src={l.flag}
            alt={l.code}
            width={24}
            height={24}
          />
        </button>
      ))}
    </div>
  );
});

