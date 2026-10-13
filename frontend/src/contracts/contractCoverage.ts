// Compile-time guard against Zod silently stripping fields the UI reads (#10771).
//
// The response schemas in ./apiContracts.ts are plain `z.object(...)`, so
// `.parse()` drops every key they do not declare. When a field is added to a
// frontend response type in ../types.ts but not to the matching schema, the UI
// compiles fine and then renders a default (0, blank, "—") because the value
// never survives parsing -- e.g. #10752 (realised gains always £0.00), #10640
// and #4883. Each assertion below fails `tsc` if a type key is missing from its
// schema, so that drift is caught at build time instead of in a QA sweep.
import type { z } from "zod";

import type {
  AwsCostService,
  AwsCostsResponse,
  DataQualityAuditEntry,
  DataQualityAuditResponse,
  DataQualityIssue,
  DataQualityIssuesResponse,
} from "../api";
import type {
  Account,
  DataQualityTimeseriesResponse,
  GroupPortfolio,
  GroupSummary,
  Holding,
  OwnerSummary,
  Portfolio,
  TimeseriesQualityPosition,
  Transaction,
} from "../types";
import type {
  accountContractSchema,
  awsCostsContractSchema,
  dataQualityAuditContractSchema,
  dataQualityIssuesContractSchema,
  dataQualityTimeseriesContractSchema,
  groupPortfolioContractSchema,
  groupsContractSchema,
  holdingContractSchema,
  ownerSummarySchema,
  portfolioContractSchema,
  transactionContractSchema,
} from "./apiContracts";

/** Keys of the frontend type `T` that the schema output `S` does not declare. */
type UndeclaredKeys<T, S> = Exclude<keyof T, keyof S>;

/** Resolves to `true` only when `K` is `never`; otherwise names the missing keys. */
type AssertAllDeclared<K> = [K] extends [never] ? true : { undeclaredKeys: K };

type Output<S extends z.ZodType> = z.output<S>;

export type OwnerSummaryCoverage = AssertAllDeclared<
  UndeclaredKeys<OwnerSummary, Output<typeof ownerSummarySchema>>
>;
export type GroupSummaryCoverage = AssertAllDeclared<
  UndeclaredKeys<GroupSummary, Output<typeof groupsContractSchema>[number]>
>;
export type HoldingCoverage = AssertAllDeclared<
  UndeclaredKeys<Holding, Output<typeof holdingContractSchema>>
>;
export type AccountCoverage = AssertAllDeclared<
  UndeclaredKeys<Account, Output<typeof accountContractSchema>>
>;
export type PortfolioCoverage = AssertAllDeclared<
  UndeclaredKeys<Portfolio, Output<typeof portfolioContractSchema>>
>;
export type GroupPortfolioCoverage = AssertAllDeclared<
  UndeclaredKeys<GroupPortfolio, Output<typeof groupPortfolioContractSchema>>
>;
// The #10752 regression: realised_gain_gbp etc. were typed but undeclared.
export type TransactionCoverage = AssertAllDeclared<
  UndeclaredKeys<Transaction, Output<typeof transactionContractSchema>>
>;

type TimeseriesQualityOutput = Output<typeof dataQualityTimeseriesContractSchema>;
type IssuesOutput = Output<typeof dataQualityIssuesContractSchema>;
type AuditOutput = Output<typeof dataQualityAuditContractSchema>;
type AwsCostsOutput = Output<typeof awsCostsContractSchema>;

export type DataQualityTimeseriesCoverage = AssertAllDeclared<
  | UndeclaredKeys<DataQualityTimeseriesResponse, TimeseriesQualityOutput>
  | UndeclaredKeys<TimeseriesQualityPosition, TimeseriesQualityOutput["positions"][number]>
>;
export type DataQualityIssuesCoverage = AssertAllDeclared<
  | UndeclaredKeys<DataQualityIssuesResponse, IssuesOutput>
  | UndeclaredKeys<DataQualityIssue, IssuesOutput["issues"][number]>
>;
export type DataQualityAuditCoverage = AssertAllDeclared<
  | UndeclaredKeys<DataQualityAuditResponse, AuditOutput>
  | UndeclaredKeys<DataQualityAuditEntry, AuditOutput["entries"][number]>
>;
export type AwsCostsCoverage = AssertAllDeclared<
  | UndeclaredKeys<AwsCostsResponse, AwsCostsOutput>
  | UndeclaredKeys<AwsCostService, AwsCostsOutput["services"][number]>
>;

// Assigning `true` fails to compile when any coverage type above is not `true`.
export const contractCoverageChecks: [
  OwnerSummaryCoverage,
  GroupSummaryCoverage,
  HoldingCoverage,
  AccountCoverage,
  PortfolioCoverage,
  GroupPortfolioCoverage,
  TransactionCoverage,
  DataQualityTimeseriesCoverage,
  DataQualityIssuesCoverage,
  DataQualityAuditCoverage,
  AwsCostsCoverage,
] = [true, true, true, true, true, true, true, true, true, true, true];
