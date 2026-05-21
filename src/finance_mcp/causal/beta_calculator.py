"""
finance_mcp.causal.beta_calculator
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
OLS-based causal beta estimation for supply-chain DEPENDS_ON edges.

For each lag in [1..max_lag] days, fits:

    downstream_return(t) ~ upstream_return(t - lag)

Selects the lag that maximises R² and runs a Granger-causality F-test
at that lag to provide a p-value.

Public API
----------
def compute_edge_beta(
    upstream_prices: pd.DataFrame,
    downstream_prices: pd.DataFrame,
    max_lag: int = 30,
) -> Optional[EdgeCalibration]
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

_DEFAULT_MAX_LAG: int = 30
# Minimum common trading days required (max_lag + safety margin)
_MIN_OBS_BUFFER: int = 30


@dataclass
class EdgeCalibration:
    """Causal properties computed for a single DEPENDS_ON edge."""
    beta: float        # OLS slope (upstream return → downstream return)
    lag_days: int      # lag in trading days that maximises R²
    r_squared: float   # coefficient of determination at best lag
    p_value: float     # Granger-causality F-test p-value at best lag
    n_observations: int


def compute_edge_beta(
    upstream_prices: pd.DataFrame,
    downstream_prices: pd.DataFrame,
    max_lag: int = _DEFAULT_MAX_LAG,
) -> Optional[EdgeCalibration]:
    """
    Compute the causal beta from *upstream* to *downstream*.

    Parameters
    ----------
    upstream_prices : pd.DataFrame
        Daily close prices for the supplier (upstream) company.
        Must have a 'Close' column and DatetimeIndex.
    downstream_prices : pd.DataFrame
        Daily close prices for the dependent (downstream) company.
    max_lag : int
        Maximum lag to search over (default 30 trading days).

    Returns
    -------
    EdgeCalibration or None
        None when there are fewer than ``max_lag + _MIN_OBS_BUFFER``
        common trading days in the two series.
    """
    from statsmodels.regression.linear_model import OLS
    from statsmodels.tools import add_constant
    from statsmodels.tsa.stattools import grangercausalitytests

    upstream_ret = _log_returns(upstream_prices)
    downstream_ret = _log_returns(downstream_prices)

    common = upstream_ret.index.intersection(downstream_ret.index)
    if len(common) < max_lag + _MIN_OBS_BUFFER:
        logger.debug(
            "compute_edge_beta: insufficient data (%d common days, need %d)",
            len(common), max_lag + _MIN_OBS_BUFFER,
        )
        return None

    upstream_ret = upstream_ret.loc[common]
    downstream_ret = downstream_ret.loc[common]

    best_beta: float = 0.0
    best_lag: int = 1
    best_r2: float = -np.inf

    for lag in range(1, max_lag + 1):
        upstream_lagged = upstream_ret.shift(lag).dropna()
        downstream_aligned = downstream_ret.loc[upstream_lagged.index]

        X = add_constant(upstream_lagged.values, has_constant="add")
        y = downstream_aligned.values

        try:
            model = OLS(y, X).fit()
            if model.rsquared > best_r2:
                best_r2 = model.rsquared
                best_beta = float(model.params[1])
                best_lag = lag
        except Exception as exc:
            logger.debug("OLS failed at lag=%d: %s", lag, exc)

    if best_r2 < 0:
        best_r2 = 0.0

    # Granger causality F-test at the selected lag
    p_value: float = 1.0
    try:
        combined = pd.DataFrame(
            {"downstream": downstream_ret.values, "upstream": upstream_ret.values},
            index=downstream_ret.index,
        )
        gc_results = grangercausalitytests(combined, maxlag=best_lag, verbose=False)
        p_value = float(gc_results[best_lag][0]["ssr_ftest"][1])
    except Exception as exc:
        logger.debug("Granger test failed at lag=%d: %s", best_lag, exc)

    return EdgeCalibration(
        beta=round(best_beta, 4),
        lag_days=best_lag,
        r_squared=round(best_r2, 4),
        p_value=round(p_value, 4),
        n_observations=len(common),
    )


def _log_returns(prices: pd.DataFrame) -> pd.Series:
    close = prices["Close"]
    return np.log(close / close.shift(1)).dropna()
