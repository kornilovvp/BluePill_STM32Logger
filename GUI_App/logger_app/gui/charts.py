"""Четыре графика на общей оси времени (Docs/40_Host/02).

A1/A2 — линии в вольтах, D1/D2 — ступеньки 0/1. Два режима:

  live   — лента едет, X заперта переключателем Window, обновление 30 Гц;
  frozen — пауза: снапшот всего буфера, X свободна (зум колесом, пан мышью),
           в видимый диапазон подкачивается ПОЛНОЕ разрешение, а при сильном
           приближении на аналоговых каналах появляются маркеры отсчётов.
"""

from __future__ import annotations

import numpy as np
import dearpygui.dearpygui as dpg

from ..core import settings
from ..data.downsampling import minmax


#          заголовок   канал  цвет (RGB)        стиль    пределы Y     вес строки
_LAYOUT = [
    ("A1, V",          "a1",  (255, 200,  60),  "line",  (0.0, 3.3),   2),
    ("A2, V",          "a2",  ( 90, 200, 255),  "line",  (0.0, 3.3),   2),
    ("D1",             "d1",  (120, 220, 120),  "stair", (-0.1, 1.1),  1),
    ("D2",             "d2",  (255, 160,  80),  "stair", (-0.1, 1.1),  1),
]

#  нижний ряд несёт подписи оси X — добавка выравнивает видимую высоту D1 и D2
_X_STRIP_EXTRA = 0.35

#  пауза: до скольких точек в кадре рисуем без децимации / с маркерами отсчётов
_FROZEN_MAX_POINTS  = 4_000
_MARKER_MAX_POINTS  = 400


class Charts:

    def __init__(self):
        self._series:  dict[str, int] = {}
        self._markers: dict[str, int] = {}      # scatter-слой аналоговых каналов
        self._x_axes:  list[int] = []
        self._analog_y: list[int] = []
        self._y_released = False

        self._frozen: tuple[np.ndarray, dict] | None = None

    # ── построение ──────────────────────────────────────────────────────────

    def build(self) -> None:
        row_ratios = [row[5] for row in _LAYOUT]
        row_ratios[-1] += _X_STRIP_EXTRA

        with dpg.subplots(rows=len(_LAYOUT), columns=1,
                          link_all_x=True, width=-1, height=-1,
                          row_ratios=row_ratios):

            for i, (title, key, color, style, ylim, _w) in enumerate(_LAYOUT):
                last_row = (i == len(_LAYOUT) - 1)

                with dpg.plot(no_mouse_pos=True):
                    x_axis = dpg.add_plot_axis(
                        dpg.mvXAxis,
                        label=("time, s" if last_row else ""),
                        no_tick_labels=not last_row,
                    )
                    y_axis = dpg.add_plot_axis(dpg.mvYAxis, label=title)
                    dpg.set_axis_limits(y_axis, *ylim)

                    if style == "line":
                        self._analog_y.append(y_axis)   # освободим для зума колесом

                    add_series = (dpg.add_line_series if style == "line"
                                  else dpg.add_stair_series)
                    series = add_series([], [], parent=y_axis)
                    dpg.bind_item_theme(series, _line_theme(color, style))

                    self._series[key] = series
                    self._x_axes.append(x_axis)

                    if style == "line":
                        marker = dpg.add_scatter_series([], [], parent=y_axis)
                        dpg.bind_item_theme(marker, _marker_theme(color))
                        self._markers[key] = marker

    # ── живой режим ─────────────────────────────────────────────────────────

    def show_live(self, x, channels: dict, window_s: float) -> None:
        self._release_y_once()

        for axis in self._x_axes:
            dpg.set_axis_limits(axis, -window_s, 0.0)

        for key, series in self._series.items():
            xd, yd = minmax(x, channels[key], settings.MAX_PLOT_POINTS)
            dpg.set_value(series, [xd.tolist(), yd.tolist()])

        self._clear_markers()

    # ── пауза ───────────────────────────────────────────────────────────────

    def freeze(self, x, channels: dict) -> None:
        """Снапшот всего буфера + свободная ось X (зум/пан на месте)."""

        self._frozen = (x, channels)

        for axis in self._x_axes:
            dpg.set_axis_limits_auto(axis)

        self.render_frozen()

    def unfreeze(self) -> None:
        self._frozen = None          # X перезапрётся первым же show_live()

    def render_frozen(self) -> None:
        """Кадр паузы: подкачать в видимый диапазон полное разрешение."""

        if self._frozen is None:
            return

        x, channels = self._frozen
        lo, hi = dpg.get_axis_limits(self._x_axes[0])

        i0 = max(0,      int(np.searchsorted(x, lo)) - 1)
        i1 = min(len(x), int(np.searchsorted(x, hi)) + 2)

        xs = x[i0:i1]
        show_markers = 0 < len(xs) <= _MARKER_MAX_POINTS

        for key, series in self._series.items():
            xd, yd = xs, channels[key][i0:i1]

            if len(xd) > _FROZEN_MAX_POINTS:
                xd, yd = minmax(xd, yd, _FROZEN_MAX_POINTS)
            dpg.set_value(series, [xd.tolist(), yd.tolist()])

            if key in self._markers:
                data = ([xd.tolist(), yd.tolist()] if show_markers else [[], []])
                dpg.set_value(self._markers[key], data)

    # ── прочее ──────────────────────────────────────────────────────────────

    def clear(self) -> None:
        self._frozen = None
        for series in self._series.values():
            dpg.set_value(series, [[], []])
        self._clear_markers()

    def _clear_markers(self) -> None:
        for marker in self._markers.values():
            dpg.set_value(marker, [[], []])

    def _release_y_once(self) -> None:
        if not self._y_released:
            #  Y аналоговых каналов свободны: колесо — масштаб, двойной клик — автофит
            for axis in self._analog_y:
                dpg.set_axis_limits_auto(axis)
            self._y_released = True


# ── темы ────────────────────────────────────────────────────────────────────


def _line_theme(color, style):
    component = dpg.mvLineSeries if style == "line" else dpg.mvStairSeries

    with dpg.theme() as theme:
        with dpg.theme_component(component):
            dpg.add_theme_color(dpg.mvPlotCol_Line, (*color, 255),
                                category=dpg.mvThemeCat_Plots)

    return theme


def _marker_theme(color):
    with dpg.theme() as theme:
        with dpg.theme_component(dpg.mvScatterSeries):
            dpg.add_theme_color(dpg.mvPlotCol_MarkerFill, (*color, 255),
                                category=dpg.mvThemeCat_Plots)
            dpg.add_theme_color(dpg.mvPlotCol_MarkerOutline, (*color, 255),
                                category=dpg.mvThemeCat_Plots)
            dpg.add_theme_style(dpg.mvPlotStyleVar_MarkerSize, 3,
                                category=dpg.mvThemeCat_Plots)

    return theme
