import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { API_BASE, getOwners } from "../api";
import type { OwnerSummary } from "../types";
import { OwnerSelector } from "../components/OwnerSelector";

export default function Reports() {
  const { t } = useTranslation();
  const [owners, setOwners] = useState<OwnerSummary[]>([]);
  const [owner, setOwner] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");

  useEffect(() => {
    getOwners().then(setOwners).catch(() => setOwners([]));
  }, []);

  const baseUrl = owner ? `${API_BASE}/reports/${owner}` : null;
  const params = new URLSearchParams();
  if (start) params.set("start", start);
  if (end) params.set("end", end);
  const query = params.toString();

  return (
    <div style={{ maxWidth: 900, margin: "0 auto", padding: "1rem" }}>
      <h1>{t("reports.title")}</h1>
      <OwnerSelector owners={owners} selected={owner} onSelect={setOwner} />
      <div style={{ margin: "1rem 0" }}>
        <label style={{ marginRight: "0.5rem" }}>
          {t("query.start")}: <input type="date" value={start} onChange={(e) => setStart(e.target.value)} />
        </label>
        <label>
          {t("query.end")}: <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
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

