# Legacy App Features Worth Carrying Forward

## High-Value Core Functions
- **Data Acquisition & Caching**  
  Ensures resilience against upstream outages, improves response times, and keeps historical data available for analytics.
- **Backend Service Endpoints**  
  Exposes flexible APIs for historical prices, risk metrics, and localized responses, enabling integration with internal and external tools.
- **Scheduled Portfolio Summaries & Queue-Driven Workers**  
  Automate recurring tasks such as reports and emails while keeping user-facing services responsive.
- **Analytics Suite & Risk Utilities**  
  Provides technical indicators and risk/return calculations that support portfolio monitoring and decision-making.
- **Sentiment & Dividend Refresh Workflows**  
  Adds alternative data (news and social sentiment) and up-to-date dividend yields for more comprehensive analysis.
- **Integrations**  
  Includes stock-feed clients and portfolio connectors to streamline data exchange with existing systems.
- **Lightweight Front-End**  
  Offers a simple UI for ticker lookups, latest prices, and quick charting.

## Lower-Priority or Nice-to-Have
- **Stand-alone VaR service** can be deferred if VaR is available through core analytics.
- **Dividend yield table and instrument scraper** are useful but not essential until the core pipelines are established.
- **Screener pipeline** is powerful but complex; consider reintroducing after foundational services are stable.
