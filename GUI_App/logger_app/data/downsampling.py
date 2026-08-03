"""Min/max-децимация кривых для отрисовки (Docs/40_Host/02).

Dear PyGui не умеет прореживать сам. Сигнал делится на бины, из каждого
берутся минимум и максимум (интерливингом) — одиночный выброс шириной
в один тик остаётся видимым при любом окне отображения.
"""

from __future__ import annotations

import warnings

import numpy as np


def minmax(x: np.ndarray, y: np.ndarray, max_points: int = 2_000):

    n = len(y)
    if n <= max_points or n < 4:
        return x, y

    bins = max_points // 2
    m    = (n // bins) * bins          # усечь до кратного числа точек

    xb = x[n - m:].reshape(bins, -1)
    yb = y[n - m:].reshape(bins, -1)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)   # all-NaN бины (разрывы)
        y_min = np.nanmin(yb, axis=1)
        y_max = np.nanmax(yb, axis=1)

    out_y        = np.empty(bins * 2, np.float32)
    out_y[0::2]  = y_min
    out_y[1::2]  = y_max
    out_x        = np.repeat(xb[:, 0], 2)

    return out_x, out_y
