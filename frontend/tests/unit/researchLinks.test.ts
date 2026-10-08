import { describe, expect, it } from "vitest";
import { buildExternalResearchLinks } from "@/utils/researchLinks";

const ids = (links: { id: string }[]) => links.map((link) => link.id);

describe("buildExternalResearchLinks", () => {
  it("builds the UK company links for a London equity", () => {
    const links = buildExternalResearchLinks({
      ticker: "REC.L",
      exchange: "L",
      isin: "GB00B28ZPS36",
      name: "Record Plc",
      instrumentType: "Equity",
    });
    expect(links).toEqual([
      { id: "yahoo", url: "https://uk.finance.yahoo.com/quote/REC.L" },
      { id: "ft", url: "https://markets.ft.com/data/search?query=GB00B28ZPS36" },
      { id: "lseShareChat", url: "https://www.lse.co.uk/ShareChat.html?ShareTicker=REC" },
      { id: "investegate", url: "https://www.investegate.co.uk/company/REC" },
      { id: "marketBeat", url: "https://www.marketbeat.com/stocks/LON/REC/" },
      {
        id: "companiesHouse",
        url: "https://find-and-update.company-information.service.gov.uk/search/companies?q=Record%20Plc",
      },
    ]);
  });

  it("builds the US links for a US equity and omits UK-only sites", () => {
    const links = buildExternalResearchLinks({
      ticker: "BRK.B.N",
      exchange: "N",
      isin: "US0846707026",
      name: "Berkshire Hathaway",
      instrumentType: "equity",
    });
    expect(ids(links)).toEqual(["yahoo", "ft", "finviz", "edgar"]);
    expect(links[0].url).toBe("https://uk.finance.yahoo.com/quote/BRK.B");
    expect(links[2].url).toBe("https://finviz.com/quote.ashx?t=BRK.B");
  });

  it("omits company-only links for ETFs and funds", () => {
    for (const instrumentType of ["ETF", "Fund"]) {
      const links = buildExternalResearchLinks({
        ticker: "VUSA.L",
        exchange: "L",
        isin: "IE00B3XXRP09",
        name: "Vanguard S&P 500",
        instrumentType,
      });
      expect(ids(links)).toEqual(["yahoo", "ft"]);
    }
  });

  it("treats investment trusts as UK companies", () => {
    const links = buildExternalResearchLinks({
      ticker: "CTY.L",
      exchange: "L",
      name: "City of London Investment Trust",
      instrumentType: "Investment Trust",
    });
    expect(ids(links)).toEqual([
      "yahoo",
      "lseShareChat",
      "investegate",
      "marketBeat",
      "companiesHouse",
    ]);
  });

  it("skips links whose required field is missing", () => {
    const links = buildExternalResearchLinks({
      ticker: "XYZ",
      exchange: "",
      isin: "not-an-isin",
      name: "",
      instrumentType: null,
    });
    expect(links).toEqual([]);
  });

  it("uses the exchange's Yahoo suffix and skips unmapped exchanges", () => {
    expect(
      buildExternalResearchLinks({ ticker: "SAP.DE", exchange: "DE" })[0],
    ).toEqual({ id: "yahoo", url: "https://uk.finance.yahoo.com/quote/SAP.DE" });
    expect(buildExternalResearchLinks({ ticker: "ABC.CA", exchange: "CA" })).toEqual([]);
  });
});
