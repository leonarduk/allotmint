// Compile-time guard against Zod silently stripping fields the UI reads (#10771).
//
// The response schemas in ./apiContracts.ts are plain `z.object(...)`, so
// `.parse()` drops every key they do not declare. When a field is added to a
// frontend response type in ../types.ts but not to the matching schema, the UI
// compiles fine and then renders a default (0, blank, "—") because the value
// never survives parsing -- e.g. #10752 (realised gains always £0.00), #10640
// and #4883. Each assertion below fails `tsc` if a type key is missing from its
// schema, so that drift is caught at build time instead of in a QA sweep.
//
// Transactions are not covered yet: the fix for #10752 (PR #10759) adds the
// missing keys to transactionContractSchema; add a `Transaction` line here
// once it lands.
import type { z } from "zod";

import type {
  Account,
  GroupPortfolio,
  GroupSummary,
  Holding,
  OwnerSummary,
  Portfolio,
} from "../types";
import type {
  accountContractSchema,
  groupPortfolioContractSchema,
  groupsContractSchema,
  holdingContractSchema,
  ownerSummarySchema,
  portfolioContractSchema,
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

// Assigning `true` fails to compile when any coverage type above is not `true`.
export const contractCoverageChecks: [
  OwnerSummaryCoverage,
  GroupSummaryCoverage,
  HoldingCoverage,
  AccountCoverage,
  PortfolioCoverage,
  GroupPortfolioCoverage,
] = [true, true, true, true, true, true];
