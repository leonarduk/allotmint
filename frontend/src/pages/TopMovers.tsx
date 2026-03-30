import { TopMoversPage } from "../components/TopMoversPage";
import { useTranslation } from "react-i18next";

export default function TopMovers() {
  const { t } = useTranslation();

  return (
    <div className="container mx-auto p-4">
      <h1 className="mb-4 text-2xl">
        {t("app.modes.movers", { defaultValue: "Top Movers" })}
      </h1>
      <TopMoversPage />
    </div>
  );
}
