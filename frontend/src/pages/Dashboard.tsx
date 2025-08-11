import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import {
  getGroupInstruments,
  getPortfolio,
  refreshPrices,
} from "../api";

import type {
  GroupSummary,
  InstrumentSummary,
  OwnerSummary,
  Portfolio,
} from "../types";

import { OwnerSelector } from "../components/OwnerSelector";
import { GroupSelector } from "../components/GroupSelector";
import { PortfolioView } from "../components/PortfolioView";
import { GroupPortfolioView } from "../components/GroupPortfolioView";
import { InstrumentTable } from "../components/InstrumentTable";
import { ComplianceWarnings } from "../components/ComplianceWarnings";

type Mode = "group" | "owner" | "instrument";

const path = window.location.pathname.split("/").filter(Boolean);
const initialMode: Mode =
  path[0] === "member" ? "owner" : path[0] === "instrument" ? "instrument" : "group";
const initialSlug = path[1] ?? "";

type Props = {
  owners: OwnerSummary[];
  groups: GroupSummary[];
};

export default function Dashboard({ owners, groups }: Props) {
  const navigate = useNavigate();
  const location = useLocation();
  const { t } = useTranslation();

  const params = new URLSearchParams(location.search);
  const [mode, setMode] = useState<Mode>(initialMode);
  const [selectedOwner, setSelectedOwner] = useState(
    initialMode === "owner" ? initialSlug : "",
  );
  const [selectedGroup, setSelectedGroup] = useState(
    initialMode === "instrument" ? initialSlug : params.get("group") ?? "",
  );

  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [instruments, setInstruments] = useState<InstrumentSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const [relativeView, setRelativeView] = useState(true);
  const [refreshingPrices, setRefreshingPrices] = useState(false);
  const [lastPriceRefresh, setLastPriceRefresh] = useState<string | null>(null);
  const [priceRefreshError, setPriceRefreshError] = useState<string | null>(null);

  useEffect(() => {
    const segs = location.pathname.split("/").filter(Boolean);
    const newMode: Mode = segs[0] === "member" ? "owner" : segs[0] === "instrument" ? "instrument" : "group";
    setMode(newMode);
    if (newMode === "owner") {
      setSelectedOwner(segs[1] ?? "");
    } else if (newMode === "instrument") {
      setSelectedGroup(segs[1] ?? "");
    } else if (newMode === "group") {
      setSelectedGroup(new URLSearchParams(location.search).get("group") ?? "");
    }
  }, [location.pathname, location.search]);

  useEffect(() => {
    if (mode === "owner" && !selectedOwner && owners.length) {
      const owner = owners[0].owner;
      setSelectedOwner(owner);
      navigate(`/member/${owner}`, { replace: true });
    }
    if (mode === "instrument" && !selectedGroup && groups.length) {
      const slug = groups[0].slug;
      setSelectedGroup(slug);
      navigate(`/instrument/${slug}`, { replace: true });
    }
    if (mode === "group" && !selectedGroup && groups.length) {
      const slug = groups[0].slug;
      setSelectedGroup(slug);
      navigate(`/?group=${slug}`, { replace: true });
    }
  }, [mode, selectedOwner, selectedGroup, owners, groups, navigate]);

  useEffect(() => {
    if (mode === "owner" && selectedOwner) {
      setLoading(true);
      setErr(null);
      getPortfolio(selectedOwner)
        .then(setPortfolio)
        .catch((e) => setErr(String(e)))
        .finally(() => setLoading(false));
    }
  }, [mode, selectedOwner]);

  useEffect(() => {
    if (mode === "instrument" && selectedGroup) {
      setLoading(true);
      setErr(null);
      getGroupInstruments(selectedGroup)
        .then(setInstruments)
        .catch((e) => setErr(String(e)))
        .finally(() => setLoading(false));
    }
  }, [mode, selectedGroup]);

  async function handleRefreshPrices() {
    setRefreshingPrices(true);
    setPriceRefreshError(null);
    try {
      const resp = await refreshPrices();
      setLastPriceRefresh(resp.timestamp ?? new Date().toISOString());

      if (mode === "owner" && selectedOwner) {
        setPortfolio(await getPortfolio(selectedOwner));
      } else if (mode === "instrument" && selectedGroup) {
        setInstruments(await getGroupInstruments(selectedGroup));
      }
    } catch (e) {
      setPriceRefreshError(e instanceof Error ? e.message : String(e));
    } finally {
      setRefreshingPrices(false);
    }
  }

  return (
    <div>
      {/* mode toggle */}
      <div style={{ marginBottom: "1rem" }}>
        <strong>{t("app.viewBy")}</strong>{" "}
        {(["group", "owner", "instrument"] as Mode[]).map((m) => (
          <label key={m} style={{ marginRight: "1rem" }}>
            <input
              type="radio"
              name="mode"
              value={m}
              checked={mode === m}
              onChange={() => {
                setMode(m);
                if (m === "group") {
                  navigate(selectedGroup ? `/?group=${selectedGroup}` : "/");
                } else if (m === "owner") {
                  const owner = selectedOwner || owners[0]?.owner;
                  if (owner) {
                    setSelectedOwner(owner);
                    navigate(`/member/${owner}`);
                  }
                } else {
                  const slug = selectedGroup || groups[0]?.slug;
                  if (slug) {
                    setSelectedGroup(slug);
                    navigate(`/instrument/${slug}`);
                  }
                }
              }}
            />{" "}
            {m === "owner" ? t("portfolio") : t(`app.modes.${m}`)}
          </label>
        ))}
      </div>

      {/* absolute vs relative toggle */}
      <div style={{ marginBottom: "1rem" }}>
        <label>
          <input
            type="checkbox"
            checked={relativeView}
            onChange={(e) => setRelativeView(e.target.checked)}
          />{" "}
          {t("app.relativeView")}
        </label>
      </div>

      <div style={{ marginBottom: "1rem" }}>
        <button onClick={handleRefreshPrices} disabled={refreshingPrices}>
          {refreshingPrices ? t("app.refreshing") : t("app.refreshPrices")}
        </button>
        {lastPriceRefresh && (
          <span style={{ marginLeft: "0.5rem", fontSize: "0.85rem", color: "#666" }}>
            {t("app.last")} {new Date(lastPriceRefresh).toLocaleString()}
          </span>
        )}
        {priceRefreshError && (
          <span style={{ marginLeft: "0.5rem", color: "red", fontSize: "0.85rem" }}>
            {priceRefreshError}
          </span>
        )}
      </div>

      {mode === "owner" && (
        <>
          <OwnerSelector
            owners={owners}
            selected={selectedOwner}
            onSelect={(owner) => {
              setSelectedOwner(owner);
              navigate(`/member/${owner}`);
            }}
          />
          <ComplianceWarnings owners={selectedOwner ? [selectedOwner] : []} />
          <PortfolioView
            data={portfolio}
            loading={loading}
            error={err}
            relativeView={relativeView}
          />
        </>
      )}

      {mode === "group" && groups.length > 0 && (
        <>
          <GroupSelector
            groups={groups}
            selected={selectedGroup}
            onSelect={(slug) => {
              setSelectedGroup(slug);
              navigate(`/?group=${slug}`);
            }}
          />
          <ComplianceWarnings
            owners={groups.find((g) => g.slug === selectedGroup)?.members ?? []}
          />
          <GroupPortfolioView
            slug={selectedGroup}
            relativeView={relativeView}
            onSelectMember={(owner) => {
              setMode("owner");
              setSelectedOwner(owner);
              navigate(`/member/${owner}`);
            }}
          />
        </>
      )}

      {mode === "instrument" && groups.length > 0 && (
        <>
          <GroupSelector
            groups={groups}
            selected={selectedGroup}
            onSelect={(slug) => {
              setSelectedGroup(slug);
              navigate(`/instrument/${slug}`);
            }}
          />
          {err && <p style={{ color: "red" }}>{err}</p>}
          {loading ? <p>{t("app.loading")}</p> : <InstrumentTable rows={instruments} />}
        </>
      )}
    </div>
  );
}

