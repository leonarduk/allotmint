import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

export default function MetricsExplanation() {
  const { t } = useTranslation();
  const alphaNotesRaw = t("metricsExplanation.sections.alpha.notes", {
    returnObjects: true,
  });
  const trackingErrorNotesRaw = t(
    "metricsExplanation.sections.trackingError.notes",
    { returnObjects: true },
  );
  const drawdownNotesRaw = t(
    "metricsExplanation.sections.maxDrawdown.notes",
    {
      returnObjects: true,
    },
  );
  const alphaNotes = Array.isArray(alphaNotesRaw)
    ? (alphaNotesRaw as string[])
    : [];
  const trackingErrorNotes = Array.isArray(trackingErrorNotesRaw)
    ? (trackingErrorNotesRaw as string[])
    : [];
  const drawdownNotes = Array.isArray(drawdownNotesRaw)
    ? (drawdownNotesRaw as string[])
    : [];

  return (
    <main className="container mx-auto max-w-3xl space-y-10 p-4">
      <header className="space-y-2">
        <Link to="/" className="inline-block text-blue-500 hover:underline">
          {t("metricsExplanation.backLink")}
        </Link>
        <h1 className="text-3xl font-bold">
          {t("metricsExplanation.title")}
        </h1>
        <p className="text-lg text-gray-300">
          {t("metricsExplanation.intro")}
        </p>
      </header>

      <section className="space-y-4">
        <h2 className="text-2xl font-semibold">
          {t("metricsExplanation.sections.alpha.title")}
        </h2>
        <p>{t("metricsExplanation.sections.alpha.summary")}</p>
        <h3 className="text-xl font-semibold">
          {t("metricsExplanation.calculationHeading")}
        </h3>
        <p>{t("metricsExplanation.sections.alpha.calculation")}</p>
        {alphaNotes.length > 0 && (
          <div>
            <h3 className="text-xl font-semibold">
              {t("metricsExplanation.notesHeading")}
            </h3>
            <ul className="list-disc space-y-1 pl-6">
              {alphaNotes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          </div>
        )}
      </section>

      <section className="space-y-4">
        <h2 className="text-2xl font-semibold">
          {t("metricsExplanation.sections.trackingError.title")}
        </h2>
        <p>{t("metricsExplanation.sections.trackingError.summary")}</p>
        <h3 className="text-xl font-semibold">
          {t("metricsExplanation.calculationHeading")}
        </h3>
        <p>{t("metricsExplanation.sections.trackingError.calculation")}</p>
        {trackingErrorNotes.length > 0 && (
          <div>
            <h3 className="text-xl font-semibold">
              {t("metricsExplanation.notesHeading")}
            </h3>
            <ul className="list-disc space-y-1 pl-6">
              {trackingErrorNotes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          </div>
        )}
      </section>

      <section className="space-y-4">
        <h2 className="text-2xl font-semibold">
          {t("metricsExplanation.sections.maxDrawdown.title")}
        </h2>
        <p>{t("metricsExplanation.sections.maxDrawdown.summary")}</p>
        <h3 className="text-xl font-semibold">
          {t("metricsExplanation.calculationHeading")}
        </h3>
        <p>{t("metricsExplanation.sections.maxDrawdown.calculation")}</p>
        {drawdownNotes.length > 0 && (
          <div>
            <h3 className="text-xl font-semibold">
              {t("metricsExplanation.notesHeading")}
            </h3>
            <ul className="list-disc space-y-1 pl-6">
              {drawdownNotes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          </div>
        )}
      </section>

      <section className="space-y-2">
        <h2 className="text-2xl font-semibold">
          {t("metricsExplanation.dataHeading")}
        </h2>
        <p>{t("metricsExplanation.dataBody")}</p>
        <p className="text-sm text-gray-400">
          {t("metricsExplanation.disclaimer")}
        </p>
      </section>
    </main>
  );
}
