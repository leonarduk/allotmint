import { useTranslation } from "react-i18next";

interface Props {
  onRetry?: () => void;
}

export default function BackendUnavailableCard({ onRetry }: Props) {
  const { t } = useTranslation();
  return (
    <div className="mx-auto my-8 max-w-[400px] rounded-lg border border-gray-300 p-4 text-center">
      <h2>{t("backendUnavailable.title")}</h2>
      <p className="mb-4 text-gray-600">
        {t("backendUnavailable.message")}
      </p>
      <div className="mb-4">
        <button onClick={onRetry} disabled={!onRetry}>
          {t("common.retry")}
        </button>
      </div>
      <div className="text-sm">
        <a
          href="/snapshots/index.html"
          target="_blank"
          rel="noopener noreferrer"
          className="mr-2"
        >
          {t("backendUnavailable.cachedView")}
        </a>
        <a
          href="/offline"
          target="_blank"
          rel="noopener noreferrer"
        >
          {t("backendUnavailable.readOnlyMode")}
        </a>
      </div>
    </div>
  );
}
