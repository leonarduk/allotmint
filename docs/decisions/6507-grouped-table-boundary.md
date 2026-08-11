# Decision: keep the catalogue and holdings tables separate (#6507)

Status: **Accepted**

## Context

`InstrumentTable` and `HoldingsTable` both offer the grouping vocabulary
`group | flat | category`, but they serve different workflows and row models.
The catalogue table consumes `InstrumentSummary[]`, filters by exchange, and
owns instrument-group mutations. The holdings table consumes holding lots or
portfolio rollups and is read-only. It also has lot-only filters, account
provenance, and virtualization.

The shared appearance does not make their state interchangeable. In
particular, a portfolio rollup is a change in row shape, while catalogue
grouping only partitions the same summary rows.

## Decision

Keep the two top-level components and their workflow-specific state separate.
Do not introduce a configurable “universal table” component or make one table
render the other workflow.

Share only presentation-neutral grouping primitives:

- `GroupingMode`, `GroupedRows`, and `RowWithCost` remain in
  `components/instrumentTable/types.ts`;
- category lookup and `createGroups` remain in
  `components/instrumentTable/utils.tsx` and are consumed by both tables; and
- future grouping fixes must be made in those shared primitives, with coverage
  for both callers when their rendering could differ.

Workflow state stays with its owner. `useInstrumentTableState` continues to
manage catalogue-only exchange filters, editable group overrides, visible
columns, and expansion. Holdings filters, sorting, virtualization, and the
portfolio's flat/rollup selection continue to be owned by the portfolio path.

## Grouping contract and defaults

Both tables use the same mode meanings:

| Mode | Meaning |
| --- | --- |
| `flat` | One unsectioned list; it does not aggregate rows. |
| `group` | Sections based on the instrument grouping value. |
| `category` | Sections based on the category definition for each grouping. If no category definitions exist, fall back to `group`. |

The defaults intentionally differ because the routes answer different user
questions:

- the catalogue defaults to `group`, so its administrative classification is
  visible immediately;
- portfolio lot views default to `flat`, so accounts and individual lots are
  not hidden behind classification sections; and
- portfolio rollup views request `category` explicitly from
  `GroupPortfolioView`; this is a portfolio display choice, not a second
  grouping state inside `HoldingsTable`.

Callers must pass the desired holdings mode explicitly when it is part of a
page-level display choice. Neither component should persist or infer the
other component's mode. Labels presented to users should describe these same
three meanings even when the control placement differs.

## Consequences

- The catalogue write path cannot leak into a read-only portfolio component.
- Each table may evolve workflow-specific columns and controls independently.
- Group construction and category fallback cannot drift because both callers
  use the same types and utilities.
- Different defaults are documented product behavior, not an inconsistency to
  “fix” by coupling the components.

Reconsider this decision only if instrument-group editing moves out of the
catalogue table and both routes converge on the same row model and interaction
contract. At that point retiring a route-specific component is preferable to
adding more configuration to a shared renderer.

