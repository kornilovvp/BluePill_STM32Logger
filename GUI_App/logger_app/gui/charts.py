"""Четыре графика на общей оси времени (Docs/40_Host/02).

A1/A2 — линии в вольтах (0…3,3), D1/D2 — ступеньки 0/1.
Обновление — set_value с готовыми (уже децимированными) массивами.
"""

from __future__ import annotations

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


class Charts:

    def __init__(self):
        self._series: dict[str, int] = {}
        self._x_axes: list[int] = []
        self._analog_y: list[int] = []
        self._y_released = False

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

                    dpg.bind_item_theme(series, _series_theme(color, style))

                    self._series[key] = series
                    self._x_axes.append(x_axis)

    # ── обновление ──────────────────────────────────────────────────────────

    def update(self, x, channels: dict, window_s: float) -> None:
        if not self._y_released:
            #  с первой отрисовкой Y аналоговых каналов отпускаются на свободу:
            #  колесо мыши — масштаб, перетаскивание — сдвиг, двойной клик — автофит
            for axis in self._analog_y:
                dpg.set_axis_limits_auto(axis)
            self._y_released = True

        for axis in self._x_axes:
            dpg.set_axis_limits(axis, -window_s, 0.0)

        for key, series in self._series.items():
            xd, yd = minmax(x, channels[key], settings.MAX_PLOT_POINTS)
            dpg.set_value(series, [xd.tolist(), yd.tolist()])

    def clear(self) -> None:
        for series in self._series.values():
            dpg.set_value(series, [[], []])


# ── внутреннее ──────────────────────────────────────────────────────────────


def _series_theme(color, style):
    component = dpg.mvLineSeries if style == "line" else dpg.mvStairSeries

    with dpg.theme() as theme:
        with dpg.theme_component(component):
            dpg.add_theme_color(dpg.mvPlotCol_Line, (*color, 255),
                                category=dpg.mvThemeCat_Plots)

    return theme
