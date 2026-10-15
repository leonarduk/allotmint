// FTSE constituents (allotmint#10912). Source: FTSE Russell "Constituents &
// Weights" for FTSE 100 (UKX) and FTSE 250 (MCX) as at 30 June 2026
// (published 19 August 2026), plus every change since:
//   - September 2026 quarterly review, effective 21 September 2026:
//     FTSE 100 +Easyjet +Ithaca Energy, -Entain -Persimmon;
//     FTSE 250 +Entain +Persimmon +Volex, -Aston Martin -GB Group.
//   - Takeover deletions with FTSE Russell's replacements: Bluefield Solar ->
//     Halfords and International Personal Finance -> Auction Technology
//     (4 Aug); JTC -> North American Income Trust (20 Aug); Beazley -> WPP,
//     Schroders -> Balfour Beatty in the FTSE 100, with ASOS and Meridian
//     Mining filling the FTSE 250 places (1 Oct); Senior -> Amaroq (8 Oct);
//     Pinewood -> Young & Co's Brewery (9 Oct).
// FTSE_AS_OF is the effective date of the last index change applied above
// (shown in the UI). Separately, every ticker was checked on 14 Oct 2026 to
// resolve to the named company and trade on the LSE. Standard Life (SDLF.L,
// formerly Phoenix) and Aberdeen Group (ABDN.L) are distinct constituents.
// When refreshing, update FTSE_AS_OF and WATCHLIST_META below.
const FTSE_AS_OF = "2026-10-09";

export const FTSE100 = [
  "III.L", // 3i Group
  "ABDN.L", // Aberdeen Group
  "ADM.L", // Admiral Group
  "AAF.L", // Airtel Africa
  "ALW.L", // Alliance Witan
  "AAL.L", // Anglo American
  "ANTO.L", // Antofagasta
  "ABF.L", // Associated British Foods
  "AZN.L", // AstraZeneca
  "AUTO.L", // Autotrader Group
  "AV.L", // Aviva
  "BAB.L", // Babcock International Group
  "BA.L", // BAE Systems
  "BBY.L", // Balfour Beatty
  "BARC.L", // Barclays
  "BTRW.L", // Barratt Redrow
  "BP.L", // BP
  "BATS.L", // British American Tobacco
  "BLND.L", // British Land Co
  "BT-A.L", // BT Group
  "BNZL.L", // Bunzl
  "BRBY.L", // Burberry Group
  "CNA.L", // Centrica
  "CCEP.L", // Coca-Cola Europacific Partners
  "CCH.L", // Coca-Cola HBC AG
  "CPG.L", // Compass Group
  "CCC.L", // Computacenter
  "CTEC.L", // ConvaTec Group
  "CRDA.L", // Croda International
  "DCC.L", // DCC
  "DGE.L", // Diageo
  "DPLM.L", // Diploma
  "EZJ.L", // Easyjet
  "EDV.L", // Endeavour Mining
  "EXPN.L", // Experian
  "FCIT.L", // F&C Investment Trust
  "FRES.L", // Fresnillo
  "GAW.L", // Games Workshop Group
  "GLEN.L", // Glencore
  "GSK.L", // GSK
  "HLN.L", // Haleon
  "HLMA.L", // Halma
  "HSX.L", // Hiscox
  "HWDN.L", // Howden Joinery Group
  "HSBA.L", // HSBC Hldgs
  "ICG.L", // ICG
  "IGG.L", // IG Group Holdings
  "IMI.L", // IMI
  "IMB.L", // Imperial Brands
  "INF.L", // Informa
  "IHG.L", // InterContinental Hotels Group
  "IAG.L", // International Consolidated Airlines Group
  "ITRK.L", // Intertek Group
  "INVP.L", // Investec
  "ITH.L", // Ithaca Energy
  "JD.L", // JD Sports Fashion
  "KGF.L", // Kingfisher
  "LAND.L", // Land Securities Group
  "LGEN.L", // Legal & General Group
  "BGEO.L", // Lion Finance Group
  "LLOY.L", // Lloyds Banking Group
  "LSEG.L", // London Stock Exchange Group
  "LMP.L", // LondonMetric Property
  "MNG.L", // M&G
  "MKS.L", // Marks & Spencer Group
  "MRO.L", // Melrose Industries
  "MTLN.L", // Metlen Energy & Metals
  "NG.L", // National Grid
  "NWG.L", // Natwest Group
  "NXT.L", // Next
  "PSON.L", // Pearson
  "PSH.L", // Pershing Square Holdings
  "PCT.L", // Polar Capital Technology Trust
  "PRU.L", // Prudential
  "RKT.L", // Reckitt Benckiser Group
  "REL.L", // RELX
  "RTO.L", // Rentokil Initial
  "RIO.L", // Rio Tinto
  "RR.L", // Rolls-Royce Holdings
  "SGE.L", // Sage Group
  "SBRY.L", // Sainsbury (J)
  "SMT.L", // Scottish Mortgage Inv Tst
  "SGRO.L", // Segro
  "SVT.L", // Severn Trent
  "SHEL.L", // Shell
  "SN.L", // Smith & Nephew
  "SMIN.L", // Smiths Group
  "SPX.L", // Spirax Group
  "SSE.L", // SSE
  "STJ.L", // St. James's Place
  "STAN.L", // Standard Chartered
  "SDLF.L", // Standard Life
  "TSCO.L", // Tesco
  "BBOX.L", // Tritax Big Box REIT
  "ULVR.L", // Unilever
  "UU.L", // United Utilities Group
  "VOD.L", // Vodafone Group
  "WEIR.L", // Weir Group
  "WTB.L", // Whitbread
  "WPP.L", // WPP
];

export const FTSE250 = [
  "3IN.L", // 3i Infrastructure
  "FOUR.L", // 4imprint Group
  "AAS.L", // Aberdeen Asia Focus
  "ASL.L", // Aberforth Smaller Companies Tst
  "AEP.L", // AEP Plantations Plc
  "AJB.L", // AJ Bell
  "ALFA.L", // Alfa Financial Software Holdings
  "ATT.L", // Allianz Technology Trust
  "AMRQ.L", // Amaroq
  "AO.L", // AO World
  "APN.L", // Applied Nutrition
  "ASHM.L", // Ashmore Group
  "AIE.L", // Ashoka India Equity Investment Trust
  "ASC.L", // ASOS
  "ATYM.L", // Atalaya Mining Copper
  "ATG.L", // Auction Technology Group
  "AGT.L", // Avi Global Trust
  "AVON.L", // Avon Technologies
  "BME.L", // B&M European Value Retail
  "BGFD.L", // Baillie Gifford Japan Trust
  "USA.L", // Baillie Gifford US Growth Trust
  "BCG.L", // Baltic Classifieds Group
  "BNKR.L", // Bankers Investment Trust
  "BAG.L", // Barr (A.G.)
  "BWY.L", // Bellway
  "BKG.L", // Berkeley Group Holdings
  "BHMG.L", // BH Macro (GBP)
  "BYG.L", // Big Yellow Group
  "BPCR.L", // Biopharma Credit
  "BRGE.L", // BlackRock Greater Euro Inv Tst
  "BRSC.L", // BlackRock Smaller Companies Tst
  "BRWM.L", // BlackRock World Mining Trust
  "BMY.L", // Bloomsbury Publishing
  "BOY.L", // Bodycote
  "BREE.L", // Breedon Group
  "BPT.L", // Bridgepoint Group
  "BUT.L", // Brunner Investment Trust
  "BYIT.L", // Bytes Technology Group
  "CLDN.L", // Caledonia Investments
  "CGT.L", // Capital Gearing Trust
  "CWR.L", // Ceres Power Holdings
  "CHG.L", // Chemring Group
  "CSN.L", // Chesnara
  "CTY.L", // City of London Investment Trust
  "CKN.L", // Clarkson
  "CBG.L", // Close Brothers Group
  "CMCX.L", // CMC Markets
  "COA.L", // Coats Group
  "CORD.L", // Cordiant Digital Infrastructure
  "COST.L", // Costain Group
  "CWK.L", // Cranswick
  "CURY.L", // Currys
  "CVSG.L", // CVS Group
  "DLN.L", // Derwent London
  "DSCV.L", // Discoverie Group
  "DOM.L", // Dominos Pizza Group
  "DOCS.L", // Dr Martens
  "DRX.L", // Drax Group
  "DNLM.L", // Dunelm Group
  "EDIN.L", // Edinburgh Investment Trust
  "EWI.L", // Edinburgh Worldwide Inv Tst
  "ELM.L", // Elementis
  "ENOG.L", // Energean
  "ENT.L", // Entain
  "ESCT.L", // European Smaller Companies Trust
  "FCSS.L", // Fidelity China Special Situations
  "FEML.L", // Fidelity Emerging Markets
  "FEV.L", // Fidelity European Trust
  "FSV.L", // Fidelity Special Values
  "FGT.L", // Finsbury Growth & Income Trust
  "FGP.L", // FirstGroup
  "FGEN.L", // Foresight Environmental Infrastructure
  "FSG.L", // Foresight Group Holdings
  "FRAS.L", // Frasers Group
  "FCH.L", // Funding Circle Holdings
  "GFRD.L", // Galliford Try Holdings
  "GAMA.L", // Gamma Communications
  "GCP.L", // GCP Infrastructure Investments
  "GEN.L", // Genuit Group
  "GNS.L", // Genus
  "GSCT.L", // Global Smaller Companies Trust
  "DATA.L", // Globaldata
  "GDWN.L", // Goodwin
  "GFTU.L", // Grafton Group
  "GRI.L", // Grainger
  "GPE.L", // Great Portland Estates
  "UKW.L", // Greencoat UK Wind
  "GNC.L", // Greencore Group
  "GRG.L", // Greggs
  "HFD.L", // Halfords Group
  "HMSO.L", // Hammerson
  "HAN.L", // Hansa Investment Company
  "HBR.L", // Harbour Energy
  "HVPE.L", // HarbourVest Global Private Equity
  "HWG.L", // Harworth Group
  "HAS.L", // Hays
  "HTWS.L", // Helios Towers
  "HFEL.L", // Henderson Far East Income
  "HSL.L", // Henderson Smaller Cos Inv Tst
  "HRI.L", // Herald Investment Trust
  "HGT.L", // HG Capital Trust
  "HICL.L", // HICL Infrastructure
  "HIK.L", // Hikma Pharmaceuticals
  "HILS.L", // Hill & Smith
  "HFG.L", // Hilton Food Group
  "HOC.L", // Hochschild Mining
  "BOWL.L", // Hollywood Bowl Group
  "HTG.L", // Hunting
  "ICGT.L", // ICG Enterprise Trust
  "INCH.L", // Inchcape
  "IHP.L", // Integrafin Holdings
  "INPP.L", // International Public Partnership
  "IWG.L", // International Workplace Group
  "IAD.L", // INVESCO Asia Dragon Trust Plc
  "IPO.L", // IP Group
  "ITV.L", // ITV
  "JMAT.L", // Johnson Matthey
  "JSG.L", // Johnson Service Group
  "JAM.L", // JPMorgan American IT
  "JCH.L", // Jpmorgan Claverhouse IT
  "JEMI.L", // JPMorgan Emerging Markets Dividend Income plc
  "JMGI.L", // JPMorgan Emerging Markets Growth & Income
  "JEDT.L", // JPMorgan European Discovery Trust
  "JEGI.L", // JPMorgan European Growth & Income
  "JGGI.L", // JPMorgan Global Growth & Income
  "JFJ.L", // JPMorgan Japanese Inv. Trust
  "JUP.L", // Jupiter Fund Management
  "KNOS.L", // Kainos Group
  "KLR.L", // Keller Group
  "KIE.L", // Kier Group
  "LRE.L", // Lancashire Holdings
  "LWDB.L", // Law Debenture Corp
  "EMG.L", // Man Group
  "MEGP.L", // Me Group International
  "MRC.L", // Mercantile Investment Tst
  "MRCH.L", // Merchants Trust
  "MNO.L", // Meridian Mining
  "MTRO.L", // Metro Bank Holdings
  "MAB.L", // Mitchells & Butlers
  "MTO.L", // MITIE Group
  "GROW.L", // Molten Ventures
  "MNDI.L", // Mondi
  "MNKS.L", // Monks Investment Trust
  "MONY.L", // MONY Group Plc
  "MOON.L", // Moonpig Group
  "MGAM.L", // Morgan Advanced Materials
  "MGNS.L", // Morgan Sindall Group
  "MUT.L", // Murray Income Trust (Ord)
  "MYI.L", // Murray International Trust (Ord)
  "NCC.L", // NCC Group
  "NBPE.L", // Neuberger Private Equity Partners (A)
  "N91.L", // Ninety One
  "NAIT.L", // North American Income Trust
  "NAS.L", // North Atlantic SmallerCosInvTst
  "OCI.L", // Oakley Capital Investments
  "OCDO.L", // Ocado Group
  "OSB.L", // OSB Group
  "OXB.L", // Oxford Biomedica
  "OXIG.L", // Oxford Instruments
  "ONT.L", // Oxford Nanopore Technologies
  "PHI.L", // Pacific Horizon Investment Trust
  "PAGE.L", // Pagegroup
  "PAF.L", // Pan African Resources
  "PINT.L", // Pantheon Infrastructure
  "PIN.L", // Pantheon International
  "PAG.L", // Paragon Banking Group
  "PEY.L", // Partners Group Private Equity
  "PPET.L", // Patria Private Equity Trust
  "PNN.L", // Pennon Group
  "PSN.L", // Persimmon
  "PNL.L", // Personal Assets Trust
  "PETS.L", // Pets At Home Group
  "PTEC.L", // Playtech
  "PLUS.L", // Plus500
  "PCGH.L", // Polar Capital Global Healthcare Trust
  "POLN.L", // Pollen Street Group
  "PPH.L", // PPHE Hotel Group
  "PFD.L", // Premier Foods
  "PHP.L", // Primary Health Prop.
  "PRN.L", // Princes Group
  "QQ.L", // Qinetiq Group
  "QLT.L", // Quilter
  "RNK.L", // Rank Group
  "RPI.L", // Raspberry Pi Holdings
  "RAT.L", // Rathbones Group
  "TRIG.L", // Renewables Infrastructure Group
  "RSW.L", // Renishaw
  "RHIM.L", // RHI Magnesita
  "RMV.L", // Rightmove
  "RCP.L", // RIT Capital Partners
  "ROSE.L", // Rosebank Industries
  "ROR.L", // Rotork
  "RS1.L", // RS Group
  "RTW.L", // RTW Biotech Opportunities
  "RICA.L", // Ruffer Investment Company
  "SAFE.L", // Safestore Holdings
  "SAGA.L", // Saga
  "SVS.L", // Savills
  "MNTN.L", // The Schiehallion Fund
  "SDP.L", // Schroder Asia Pacific Fund
  "ATR.L", // Schroder Asian Total Return Investment Company
  "SOI.L", // Schroder Oriental Income Fund
  "SAIN.L", // Scottish American Investment
  "SEIT.L", // SDCL Efficiency Income Trust
  "SEQI.L", // Sequoia Economic Infrastructure Income Fund
  "SSIT.L", // Seraphim Space Investment Trust
  "SRP.L", // Serco Group
  "SHC.L", // Shaftesbury Capital
  "SHAW.L", // Shawbrook Group
  "SRE.L", // Sirius Real Estate
  "SCT.L", // Softcat
  "SPI.L", // Spire Healthcare Group
  "SSPG.L", // SSP Group
  "SUPR.L", // Supermarket Income REIT
  "SYNC.L", // Syncona
  "THRL.L", // Target Healthcare REIT
  "TATE.L", // Tate & Lyle
  "TW.L", // Taylor Wimpey
  "TBCG.L", // TBC Bank Group
  "TEP.L", // Telecom Plus
  "TMPL.L", // Temple Bar Inv Tst
  "TEM.L", // Templeton Emerging Markets IT
  "THG.L", // THG
  "TCAP.L", // TP ICAP Group
  "TRY.L", // TR Property Investment Trust
  "TRN.L", // Trainline
  "TPK.L", // Travis Perkins
  "TRST.L", // Trustpilot Group
  "TFIF.L", // Twentyfour Income Fund
  "UTG.L", // Unite Group
  "UEM.L", // Utilico Emerging Markets Trust
  "VSVS.L", // Vesuvius
  "VCT.L", // Victrex
  "VEIL.L", // Vietnam Enterprise Investments
  "VOF.L", // Vinacapital Vietnam Opportunity Fund
  "VTY.L", // Vistry Group
  "VLX.L", // Volex
  "FAN.L", // Volution Group
  "EWG.L", // WAG Payment Solutions
  "WOSG.L", // Watches of Switzerland Group
  "JDW.L", // Wetherspoon(J D)
  "SMWH.L", // WH Smith
  "WIX.L", // Wickes Group
  "WIZZ.L", // Wizz Air Holdings
  "WKP.L", // Workspace Group
  "WWH.L", // Worldwide Healthcare Trust
  "XPP.L", // XP Power
  "XPS.L", // XPS Pensions Group
  "YNGA.L", // Young & Co's Brewery (A)
  "ZIG.L", // ZIGUP
];

export const FTSE350 = Array.from(new Set([...FTSE100, ...FTSE250]));

// Approximation: the real All-Share also includes ~250 FTSE SmallCap
// members, which this list does not carry (see WATCHLIST_META).
export const FTSEAllShare = [...FTSE350];

export const SP500 = [
  "MMM",
  "AOS",
  "ABT",
  "ABBV",
  "ACN",
  "ADBE",
  "AMD",
  "AES",
  "AFL",
  "A",
  "APD",
  "ABNB",
  "AKAM",
  "ALB",
  "ARE",
  "ALGN",
  "ALLE",
  "LNT",
  "ALL",
  "GOOGL",
  "GOOG",
  "MO",
  "AMZN",
  "AMCR",
  "AEE",
  "AEP",
  "AXP",
  "AIG",
  "AMT",
  "AWK",
  "AMP",
  "AME",
  "AMGN",
  "APH",
  "ADI",
  "AON",
  "APA",
  "APO",
  "PFE",
  "AMAT",
  "APTV",
  "ACGL",
  "ADM",
  "ANET",
  "AJG",
  "AIZ",
  "T",
  "ATO",
  "ADSK",
  "ADP",
  "AZO",
  "AVB",
  "AVY",
  "AXON",
  "BKR",
  "BALL",
  "BAC",
  "BAX",
  "BDX",
  "BRK.B",
  "BBY",
  "TECH",
  "BIIB",
  "BLK",
  "BX",
  "XYZ",
  "BK",
  "BA",
  "BKNG",
  "BSX",
  "BMY",
  "AVGO",
  "BR",
  "BRO",
  "BF.B",
  "BLDR",
  "BG",
  "BXP",
  "CHRW",
  "CDNS",
  "CZR",
  "CPT",
  "CPB",
  "COF",
  "CAH",
  "KMX",
  "CCL",
  "CARR",
  "CAT",
  "CBOE",
  "CBRE",
  "CDW",
  "COR",
  "CNC",
  "CNP",
  "CF",
  "CRL",
  "SCHW",
  "CHTR",
  "CVX",
  "CMG",
  "CB",
  "CHD",
  "CI",
  "CINF",
  "CTAS",
  "CSCO",
  "C",
  "CFG",
  "CLX",
  "CME",
  "CMS",
  "KO",
  "CTSH",
  "COIN",
  "CL",
  "CMCSA",
  "CAG",
  "COP",
  "ED",
  "STZ",
  "CEG",
  "COO",
  "CPRT",
  "GLW",
  "CPAY",
  "CTVA",
  "CSGP",
  "COST",
  "CTRA",
  "CRWD",
  "CCI",
  "CSX",
  "CMI",
  "CVS",
  "DHR",
  "DRI",
  "DDOG",
  "DVA",
  "DAY",
  "DECK",
  "DE",
  "DELL",
  "DAL",
  "DVN",
  "DXCM",
  "FANG",
  "DLR",
  "DG",
  "DLTR",
  "D",
  "DPZ",
  "DASH",
  "DOV",
  "DOW",
  "DHI",
  "DTE",
  "DUK",
  "DD",
  "EMN",
  "ETN",
  "EBAY",
  "ECL",
  "EIX",
  "EW",
  "EA",
  "ELV",
  "EMR",
  "ENPH",
  "ETR",
  "EOG",
  "EPAM",
  "EQT",
  "EFX",
  "EQIX",
  "EQR",
  "ERIE",
  "ESS",
  "EL",
  "EG",
  "EVRG",
  "ES",
  "EXC",
  "EXE",
  "EXPE",
  "EXPD",
  "EXR",
  "XOM",
  "FFIV",
  "FDS",
  "FICO",
  "FAST",
  "FRT",
  "FDX",
  "FIS",
  "FITB",
  "FSLR",
  "FE",
  "FI",
  "F",
  "FTNT",
  "FTV",
  "FOXA",
  "FOX",
  "BEN",
  "FCX",
  "GRMN",
  "IT",
  "GE",
  "GEHC",
  "GEV",
  "GEN",
  "GNRC",
  "GD",
  "GIS",
  "GM",
  "GPC",
  "GILD",
  "GPN",
  "GL",
  "GDDY",
  "GS",
  "HAL",
  "HIG",
  "HAS",
  "HCA",
  "DOC",
  "HSIC",
  "HSY",
  "HPE",
  "HLT",
  "HOLX",
  "HD",
  "HON",
  "HRL",
  "HST",
  "HWM",
  "HPQ",
  "HUBB",
  "HUM",
  "HBAN",
  "HII",
  "IBM",
  "IEX",
  "IDXX",
  "ITW",
  "INCY",
  "IR",
  "PODD",
  "INTC",
  "ICE",
  "IFF",
  "IP",
  "IPG",
  "INTU",
  "ISRG",
  "IVZ",
  "INVH",
  "IQV",
  "IRM",
  "JBHT",
  "JBL",
  "JKHY",
  "J",
  "JNJ",
  "JCI",
  "JPM",
  "K",
  "KVUE",
  "KDP",
  "KEY",
  "KEYS",
  "KMB",
  "KIM",
  "KMI",
  "KKR",
  "KLAC",
  "KHC",
  "KR",
  "LHX",
  "LH",
  "LRCX",
  "LW",
  "LVS",
  "LDOS",
  "LEN",
  "LII",
  "LLY",
  "LIN",
  "LYV",
  "LKQ",
  "LMT",
  "L",
  "LOW",
  "LULU",
  "LYB",
  "MTB",
  "MPC",
  "MKTX",
  "MAR",
  "MMC",
  "MLM",
  "MAS",
  "MA",
  "MTCH",
  "MKC",
  "MCD",
  "MCK",
  "MDT",
  "MRK",
  "META",
  "MET",
  "MTD",
  "MGM",
  "MCHP",
  "MU",
  "MSFT",
  "MAA",
  "MRNA",
  "MHK",
  "MOH",
  "TAP",
  "MDLZ",
  "MPWR",
  "MNST",
  "MCO",
  "MS",
  "MOS",
  "MSI",
  "MSCI",
  "NDAQ",
  "NTAP",
  "NFLX",
  "NEM",
  "NWSA",
  "NWS",
  "NEE",
  "NKE",
  "NI",
  "NDSN",
  "NSC",
  "NTRS",
  "NOC",
  "NCLH",
  "NRG",
  "NUE",
  "NVDA",
  "NVR",
  "NXPI",
  "ORLY",
  "OXY",
  "ODFL",
  "OMC",
  "ON",
  "OKE",
  "ORCL",
  "OTIS",
  "PCAR",
  "PKG",
  "PLTR",
  "PANW",
  "PSKY",
  "PH",
  "PAYX",
  "PAYC",
  "PYPL",
  "PNR",
  "PEP",
  "PFE",
  "PCG",
  "PM",
  "PSX",
  "PNW",
  "PNC",
  "POOL",
  "PPG",
  "PPL",
  "PFG",
  "PG",
  "PGR",
  "PLD",
  "PRU",
  "PEG",
  "PTC",
  "PSA",
  "PHM",
  "PWR",
  "QCOM",
  "DGX",
  "RL",
  "RJF",
  "RTX",
  "O",
  "REG",
  "REGN",
  "RF",
  "RSG",
  "RMD",
  "RVTY",
  "ROK",
  "ROL",
  "ROP",
  "ROST",
  "RCL",
  "SPGI",
  "CRM",
  "SBAC",
  "SLB",
  "STX",
  "SRE",
  "NOW",
  "SHW",
  "SPG",
  "SWKS",
  "SJM",
  "SW",
  "SNA",
  "SOLV",
  "SO",
  "LUV",
  "SWK",
  "SBUX",
  "STT",
  "STLD",
  "STE",
  "SYK",
  "SMCI",
  "SYF",
  "SNPS",
  "SYY",
  "TMUS",
  "TROW",
  "TTWO",
  "TPR",
  "TRGP",
  "TGT",
  "TEL",
  "TDY",
  "TER",
  "TSLA",
  "TXN",
  "TPL",
  "TXT",
  "TMO",
  "TJX",
  "TKO",
  "TTD",
  "TSCO",
  "TT",
  "TDG",
  "TRV",
  "TRMB",
  "TFC",
  "TYL",
  "TSN",
  "USB",
  "UBER",
  "UDR",
  "ULTA",
  "UNP",
  "UAL",
  "UPS",
  "URI",
  "UNH",
  "UHS",
  "VLO",
  "VTR",
  "VLTO",
  "VRSN",
  "VRSK",
  "VZ",
  "VRTX",
  "VTRS",
  "VICI",
  "V",
  "VST",
  "VMC",
  "WRB",
  "GWW",
  "WAB",
  "WBA",
  "WMT",
  "DIS",
  "WBD",
  "WM",
  "WAT",
  "WEC",
  "WFC",
  "WELL",
  "WST",
  "WDC",
  "WY",
  "WSM",
  "WMB",
  "WTW",
  "WDAY",
  "WYNN",
  "XEL",
  "XYL",
  "YUM",
  "ZBRA",
  "ZBH",
  "ZTS",
];


// Widely held ETFs for risk/return screening (allotmint#10607): US listings
// (bare tickers, as in SP500 above) then London listings (.L).
export const CORE_ETFS = [
  "SPY", "QQQ", "IWM", "DIA", "VTI", "VOO", "VT", "VEA", "VWO", "EFA",
  "EEM", "IEMG", "ACWI", "IOO", "MTUM", "QUAL", "USMV", "SPLV", "VLUE", "SCHD",
  "VIG", "DGRO", "NOBL", "VYM", "HDV", "RSP", "XLK", "XLV", "XLF", "XLE",
  "XLI", "XLP", "XLU", "XLY", "XLB", "XLRE", "XLC", "SMH", "SOXX", "IGV",
  "IBB", "XBI", "ITA", "KRE", "GDX", "GDXJ", "SLV", "GLD", "IAU", "DBC",
  "PDBC", "USO", "TLT", "IEF", "SHY", "AGG", "BND", "LQD", "HYG", "TIP",
  "VNQ", "IJH", "IJR", "IJS", "MDY", "VBR", "VUG", "VTV", "IWF", "IWD",
  "AVUV", "EWJ", "EWG", "EWU", "EWZ", "INDA", "FXI", "MCHI", "EWT", "EWY",
  "JEPI", "JEPQ", "COWZ", "SPHQ", "DBMF", "KMLM", "CTA", "BTAL",
  "VWRL.L", "VWRP.L", "VUSA.L", "VUAG.L", "CSP1.L", "ISF.L", "VUKE.L", "VMID.L",
  "VFEM.L", "EIMI.L", "IWRD.L", "SWDA.L", "HMWO.L", "XDWD.L", "SSAC.L", "IUSA.L",
  "CSPX.L", "EQQQ.L", "CNDX.L", "IUIT.L", "XDWT.L", "IUHC.L", "IUFS.L", "IUES.L",
  "WQDV.L", "MINV.L", "XDEB.L", "IWFQ.L", "IWFM.L", "IWFV.L", "IEFV.L", "IEFM.L",
  "WSML.L", "VHYL.L", "IUKD.L", "ISPY.L", "HEAL.L", "INRG.L", "RBOT.L", "ECAR.L",
  "SGLN.L", "PHAU.L", "PHGP.L", "SGLD.L", "SSLN.L", "PHSP.L", "SPGP.L", "GDGB.L",
  "CMOP.L", "BCOG.L", "IGLT.L", "VGOV.L", "IGLS.L", "INXG.L", "SLXX.L", "VUCP.L",
  "IHYG.L", "SEMB.L", "EMIM.L", "HMCH.L", "IJPN.L", "VJPN.L", "VERX.L", "VEUR.L",
  "IUKP.L", "IMEU.L", "XLKS.L", "XLES.L", "JPGL.L", "JGGI.L", "VAPX.L", "IAPD.L",
  "XDEM.L", "XDEV.L", "XDEQ.L", "GBDV.L", "TDIV.L", "FUSD.L", "FGQI.L",
];

export const WATCHLISTS = {
  "FTSE 100": FTSE100,
  "FTSE 250": FTSE250,
  "FTSE 350": FTSE350,
  "FTSE All-Share": FTSEAllShare,
  "S&P 500": SP500,
  "Core ETFs": CORE_ETFS,
} as const;

export type WatchlistName = keyof typeof WATCHLISTS;

export interface WatchlistMeta {
  /** ISO date the constituents were last checked against `source`. */
  asOf: string;
  source: string;
}

export const WATCHLIST_META: Record<WatchlistName, WatchlistMeta> = {
  "FTSE 100": { asOf: FTSE_AS_OF, source: "FTSE Russell" },
  "FTSE 250": { asOf: FTSE_AS_OF, source: "FTSE Russell" },
  "FTSE 350": { asOf: FTSE_AS_OF, source: "FTSE 100 + FTSE 250" },
  "FTSE All-Share": {
    asOf: FTSE_AS_OF,
    source: "FTSE 350 only, excludes SmallCap",
  },
  // Last refreshed in #1219; not re-checked against S&P Dow Jones Indices.
  "S&P 500": { asOf: "2025-09-10", source: "S&P Dow Jones Indices" },
  "Core ETFs": { asOf: "2026-10-11", source: "curated list" },
};
