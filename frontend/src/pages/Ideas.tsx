import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useConfig } from "../ConfigContext";
import { isModeEnabled } from "../pageManifest";
import type { Mode } from "../modes";
import Trading from "./Trading";
import { Screener } from "./Screener";

export type IdeasTab = "signals" | "screen";

// One Ideas page over two existing modes (#9852). Each tab keeps its own
// mode and URL (/trading, /screener) so deep links, tab gating and smoke
// tests are unchanged; only the active tab is mounted, so opening Screen
// never fires the slow /trading-agent/* requests.
const IDEAS_TABS: { id: IdeasTab; mode: Mode; path: string }[] = [
  { id: "signals", mode: "trading", path: "/trading" },
  { id: "screen", mode: "screener", path: "/screener" },
];

export default function Ideas({ tab }: { tab: IdeasTab }) {
  const { t } = useTranslation();
  const { tabs, disabledTabs } = useConfig();
  const visibleTabs = IDEAS_TABS.filter(
    (item) => item.id === tab || isModeEnabled(item.mode, tabs, disabledTabs),
  );

  return (
    <div>
      {visibleTabs.length > 1 && (
        <nav
          aria-label={t("ideas.tabsLabel")}
          className="container mx-auto mb-2 flex flex-wrap gap-2 px-4 pt-4"
        >
          {visibleTabs.map((item) => (
            <Link
              key={item.id}
              to={item.path}
              aria-current={item.id === tab ? "page" : undefined}
              className={
                item.id === tab
                  ? "rounded bg-blue-700 px-3 py-1 text-white!"
                  : "rounded bg-gray-200 px-3 py-1 text-gray-900!"
              }
            >
              {t(`ideas.tabs.${item.id}`)}
            </Link>
          ))}
        </nav>
      )}
      <p className="container mx-auto px-4 text-sm opacity-80">
        {t(`ideas.explain.${tab}`)}
      </p>
      {tab === "signals" ? <Trading /> : <Screener />}
    </div>
  );
}
