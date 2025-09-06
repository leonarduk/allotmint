# Performance Budgets

Rendering was profiled with React DevTools. The following budgets help catch regressions:

- **TopMoversPage**: initial table render under **50ms** for 200 rows.
- **Alert list**: scroll and render under **40ms** for 1,000 alerts.
- **Sparkline component**: render under **5ms** per instance.

Use React DevTools' Profiler to validate these numbers when modifying related components.
