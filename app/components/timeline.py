"""Графики звонка: временная шкала реплик с паузами и столбики пауз перед ответом агента.
Цвета — по ролям: агент — синий (категориальный слот 1), клиент — нейтральный серый (фон);
статус паузы — цвет + значок + подпись (✓ норма / ⚠ долго / ⤫ перебил), никогда не цвет в одиночку.
"""
import textwrap

import plotly.graph_objects as go

AGENT, CLIENT = "#3987e5", "#8f8e88"
GOOD, CRIT = "#0ca30c", "#d03b3b"
GRID = "rgba(128,128,128,0.18)"
LANES = {"agent": "Агент", "client": "Клиент"}


def _status(g: float, slow_s: float):
    if g < 0:
        return CRIT, "⤫", f"перебил {abs(g):.1f} с"
    if g > slow_s:
        return CRIT, "⚠", f"{g:.1f} с"
    return GOOD, "✓", f"{g:.1f} с"


def _wrap(text: str, width: int = 60) -> str:
    return "<br>".join(textwrap.wrap(text, width)[:6])


def _base_layout(fig: go.Figure, height: int):
    fig.update_layout(height=height, margin={"l": 8, "r": 8, "t": 36, "b": 8},
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      hoverlabel={"align": "left"}, bargap=0.45,
                      legend={"orientation": "h", "x": 1, "xanchor": "right", "y": 1.12, "title": None})
    fig.update_xaxes(showgrid=True, gridcolor=GRID, zeroline=False, ticksuffix=" с", showline=False)
    fig.update_yaxes(showgrid=False, zeroline=False, showline=False)


def timeline_figure(turns: list[dict], slow_s: float = 1.5) -> go.Figure:
    fig = go.Figure()
    main = sorted((t for t in turns if not t.get("backchannel")), key=lambda t: t["start"])

    # паузы перед ответом агента: полупрозрачная полоса через обе дорожки + подпись над ней
    for t in main:
        g = t.get("gap_s")
        if t["role"] != "agent" or g is None or t.get("after") != "client":
            continue
        color, icon, label = _status(g, slow_s)
        x0, x1 = sorted((t["start"] - g, t["start"]))
        fig.add_vrect(x0=x0, x1=x1, fillcolor=color, opacity=0.14, line_width=0, layer="below")
        if icon == "✓":                     # нормальные паузы не подписываем — значения есть на графике ниже
            continue
        fig.add_annotation(x=(x0 + x1) / 2, y=1, yref="paper", yanchor="bottom", showarrow=False,
                           text=f"<b>{icon} {label}</b>", font={"size": 12})

    for role, color in (("client", CLIENT), ("agent", AGENT)):
        ts = [t for t in turns if t["role"] == role]
        if not ts:
            continue
        fig.add_bar(
            y=[LANES[role]] * len(ts), base=[t["start"] for t in ts], x=[t["end"] - t["start"] for t in ts],
            orientation="h", name=LANES[role], marker={"color": color, "cornerradius": 4,
                                                       "opacity": [0.4 if t.get("backchannel") else 1 for t in ts]},
            width=0.42,
            customdata=[[t["start"], t["end"], _wrap(t["text"]), "поддакивание · " if t.get("backchannel") else ""]
                        for t in ts],
            hovertemplate=f"<b>{LANES[role]}</b> · %{{customdata[3]}}%{{customdata[0]:.1f}}–%{{customdata[1]:.1f}} с"
                          "<br>%{customdata[2]}<extra></extra>")

    _base_layout(fig, 240)
    fig.update_layout(barmode="overlay", showlegend=False)
    fig.update_yaxes(categoryorder="array", categoryarray=["Клиент", "Агент"], tickfont={"size": 13})
    return fig


def gaps_figure(turns: list[dict], slow_s: float = 1.5) -> go.Figure:
    """Пауза перед каждым ответом агента: столбик на ход + пунктир порога «долгой паузы»."""
    rows = [t for t in sorted(turns, key=lambda t: t["start"])
            if t["role"] == "agent" and t.get("after") == "client" and not t.get("backchannel")]
    fig = go.Figure()
    if rows:
        st = [_status(t["gap_s"], slow_s) for t in rows]
        fig.add_bar(x=[f"№{i + 1} · {t['start']:.0f} с" for i, t in enumerate(rows)], y=[t["gap_s"] for t in rows],
                    marker={"color": [s[0] for s in st], "cornerradius": 4}, width=0.3,
                    text=[f"{s[1]} {s[2]}" for s in st], textposition="outside", cliponaxis=False,
                    textfont={"size": 12}, constraintext="none",
                    customdata=[_wrap(t["text"]) for t in rows],
                    hovertemplate="Пауза %{y:.2f} с<br>%{customdata}<extra></extra>", showlegend=False)
    else:
        fig.add_annotation(text="Нет ответов агента после реплик клиента", showarrow=False,
                           xref="paper", yref="paper", x=0.5, y=0.5)
        fig.update_xaxes(visible=False)
    fig.add_hline(y=slow_s, line_dash="dot", line_width=1, line_color="rgba(128,128,128,0.9)",
                  annotation_text=f"порог {slow_s:g} с", annotation_position="top right")
    _base_layout(fig, 260)
    fig.update_xaxes(showgrid=False, ticksuffix="")
    fig.update_yaxes(showgrid=True, gridcolor=GRID, ticksuffix=" с", rangemode="tozero")
    return fig
