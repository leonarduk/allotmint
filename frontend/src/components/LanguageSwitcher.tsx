import { useEffect, useState } from "react";
import i18n from "i18next";

const LANGUAGES = [
  { code: "en", flag: "🇬🇧" },
  { code: "fr", flag: "🇫🇷" },
  { code: "de", flag: "🇩🇪" },
  { code: "es", flag: "🇪🇸" },
  { code: "pt", flag: "🇵🇹" },
];

export function LanguageSwitcher() {
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
          style={{
            fontSize: "1.5rem",
            background: "none",
            border: "none",
            cursor: "pointer",
            opacity: current === l.code ? 1 : 0.5,
          }}
          aria-label={l.code}
        >
          {l.flag}
        </button>
      ))}
    </div>
  );
}

