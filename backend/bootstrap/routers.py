"""Router registration for the FastAPI application."""

from __future__ import annotations

from fastapi import Depends, FastAPI

import backend.auth as auth
from backend.config import Config
from backend.routes.agent import router as agent_router
from backend.routes.alert_settings import router as alert_settings_router
from backend.routes.alerts import router as alerts_router
from backend.routes.analytics import router as analytics_router
from backend.routes.approvals import router as approvals_router
from backend.routes.compliance import router as compliance_router
from backend.routes.config import router as config_router
from backend.routes.events import router as events_router
from backend.routes.goals import router as goals_router
from backend.routes.instrument import router as instrument_router
from backend.routes.instrument_admin import router as instrument_admin_router
from backend.routes.logs import router as logs_router
from backend.routes.market import router as market_router
from backend.routes.metrics import router as metrics_router
from backend.routes.models import router as models_router
from backend.routes.movers import router as movers_router
from backend.routes.news import router as news_router
from backend.routes.nudges import router as nudges_router
from backend.routes.opportunities import router as opportunities_router
from backend.routes.pension import router as pension_router
from backend.routes.performance import router as performance_router
from backend.routes.portfolio import public_router as public_portfolio_router
from backend.routes.portfolio import router as portfolio_router
from backend.routes.query import router as query_router
from backend.routes.quest_routes import router as quest_router
from backend.routes.quotes import router as quotes_router
from backend.routes.rebalance import router as rebalance_router
from backend.routes.reports import router as reports_router
from backend.routes.scenario import router as scenario_router
from backend.routes.screener import router as screener_router
from backend.routes.support import router as support_router
from backend.routes.tax import router as tax_router
from backend.routes.timeseries_admin import router as timeseries_admin_router
from backend.routes.timeseries_edit import router as timeseries_edit_router
from backend.routes.timeseries_meta import router as timeseries_router
from backend.routes.trading_agent import router as trading_agent_router
from backend.routes.trail import router as trail_router
from backend.routes.transactions import router as transactions_router
from backend.routes.user_config import router as user_config_router
from backend.routes.virtual_portfolio import router as virtual_portfolio_router


def register_routers(app: FastAPI, cfg: Config) -> None:
    """Register the API routers with auth dependencies applied as needed."""

    protected = [] if cfg.disable_auth else [Depends(auth.get_current_user)]

    app.include_router(public_portfolio_router)
    app.include_router(portfolio_router, dependencies=protected)
    app.include_router(performance_router, dependencies=protected)
    app.include_router(opportunities_router)
    app.include_router(instrument_router)
    app.include_router(instrument_admin_router, dependencies=protected)
    app.include_router(timeseries_router)
    app.include_router(timeseries_edit_router)
    app.include_router(timeseries_admin_router, dependencies=protected)
    app.include_router(transactions_router)
    app.include_router(alert_settings_router, dependencies=protected)
    app.include_router(alerts_router, dependencies=protected)
    app.include_router(nudges_router, dependencies=protected)
    app.include_router(quest_router, dependencies=protected)
    app.include_router(trail_router, dependencies=protected)
    app.include_router(compliance_router)
    app.include_router(screener_router)
    app.include_router(support_router)
    app.include_router(query_router, dependencies=protected)
    app.include_router(virtual_portfolio_router, dependencies=protected)
    app.include_router(metrics_router)
    app.include_router(analytics_router, dependencies=protected)
    app.include_router(agent_router)
    app.include_router(trading_agent_router, dependencies=protected)
    app.include_router(rebalance_router)
    app.include_router(config_router)
    app.include_router(quotes_router)
    app.include_router(news_router)
    app.include_router(market_router)
    app.include_router(movers_router)
    app.include_router(models_router)
    app.include_router(user_config_router, dependencies=protected)
    app.include_router(approvals_router, dependencies=protected)
    app.include_router(events_router)
    app.include_router(scenario_router)
    app.include_router(logs_router)
    app.include_router(goals_router, dependencies=protected)
    app.include_router(tax_router)
    app.include_router(pension_router)
    app.include_router(reports_router, dependencies=protected)
