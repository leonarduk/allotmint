import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { API_BASE, getOwners } from "../api";
import type { OwnerSummary } from "../types";
import { OwnerSelector } from "../components/OwnerSelector";

export default function Reports() {
  const { t } = useTranslation();
  const [owners, setOwners] = useState<OwnerSummary[]>([]);
  const [ownersLoaded, setOwnersLoaded] = useState(false);
  const [owner, setOwner] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");

  useEffect(() => {
    getOwners()
      .then(setOwners)
      .catch(() => setOwners([]))
      .finally(() => setOwnersLoaded(true));
  }, []);

  const baseUrl = owner ? `${API_BASE}/reports/${owner}` : null;
  const params = new URLSearchParams();
  if (start) params.set("start", start);
  if (end) params.set("end", end);
  const query = params.toString();

  return (
    <div className="container mx-auto p-4 max-w-3xl">
      <h1 className="mb-4 text-2xl md:text-4xl">{t("reports.title")}</h1>
      {ownersLoaded && owners.length === 0 ? (
        <p>{t("reports.noOwners")}</p>
      ) : (
        <OwnerSelector owners={owners} selected={owner} onSelect={setOwner} />
      )}
      <div className="my-4">
        <label className="mr-2">
          {t("query.start")}:{" "}
          <input type="date" value={start} onChange={(e) => setStart(e.target.value)} />
        </label>
        <label>
          {t("query.end")}:{" "}
          <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
        </label>
      </div>
      {baseUrl && (
        <p>
          <a href={`${baseUrl}?${query}&format=csv`}>{t("reports.csv")}</a>
          {" | "}
          <a href={`${baseUrl}?${query}&format=pdf`}>{t("reports.pdf")}</a>
        </p>
      )}
    </div>
  );
}

