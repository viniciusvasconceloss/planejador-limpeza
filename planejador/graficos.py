"""Gráficos Plotly do app."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# Paleta: azul = coberto com folga, cinza = no limite (100%), vermelho = alerta estourado.
AZUL, CINZA, VERMELHO, VERMELHO_ESCURO = "#3987e5", "#f0efec", "#e66767", "#a3201f"
CORES_TAREFA = {"limpeza": "#2a78d6", "lavação": "#1baf7a", "checagem": "#eda100",
                "deslocamento": "#c3c2b7", "intervalo": "#e8e7e3"}
ESCALA_MAX = 3.0


def _layout(fig: go.Figure, altura: int = 420) -> go.Figure:
    fig.update_layout(height=altura, margin=dict(l=10, r=10, t=80, b=10),
                      plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title_text=""))
    return fig


def mapa_calor(mapa: pd.DataFrame, titulo: str) -> go.Figure:
    """Banheiro x hora; valor = pior necessidade da hora (0 a 3, acima de 1 é alerta estourado)."""
    z = mapa.values
    texto = [[f"{v:.1f}".replace(".", ",") if v >= 1.05 else "" for v in linha] for linha in z]
    fig = go.Figure(go.Heatmap(
        z=z, x=list(mapa.columns), y=list(mapa.index), zmin=0, zmax=ESCALA_MAX,
        # 1,0 = cinza; já em 1,2 fica vermelho claro, para o atraso aparecer cedo
        colorscale=[[0, AZUL], [1 / ESCALA_MAX, CINZA], [1.25 / ESCALA_MAX, VERMELHO], [1, VERMELHO_ESCURO]],
        text=texto, texttemplate="%{text}", textfont=dict(size=11),
        xgap=2, ygap=2,
        colorbar=dict(title="limpezas<br>devidas", tickvals=[0, 1, 2, 3], ticktext=["0", "1 (alerta)", "2", "3+"]),
        hovertemplate="%{y}<br>%{x}<br>pior necessidade na hora: %{z:.0%}<extra></extra>",
    ))
    fig.update_yaxes(autorange="reversed")
    fig.update_layout(title=titulo)
    return _layout(fig, altura=max(320, 34 * len(mapa) + 120))


def capacidade_carga(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    for col, cor in (("limpeza", CORES_TAREFA["limpeza"]), ("lavação", CORES_TAREFA["lavação"]),
                     ("checagem", CORES_TAREFA["checagem"])):
        fig.add_bar(x=df.hora, y=df[col], name=f"carga: {col}", marker_color=cor,
                    hovertemplate="%{x}<br>" + col + ": %{y:.0f} min<extra></extra>")
    fig.add_scatter(x=df.hora, y=df.capacidade, name="capacidade da equipe", mode="lines+markers",
                    line=dict(color="#0b0b0b", width=2, shape="hv"), marker=dict(size=8),
                    hovertemplate="%{x}<br>capacidade: %{y:.0f} min<extra></extra>")
    fig.update_layout(barmode="stack", bargap=0.15, title="Capacidade x carga por hora (minutos de trabalho)")
    fig.update_yaxes(title="minutos", gridcolor="rgba(128,128,128,0.15)")
    return _layout(fig)


def limpeza_ideal(df: pd.DataFrame) -> go.Figure:
    longo = df.melt(id_vars="banheiro", value_vars=["original", "ajustada"], var_name="alerta", value_name="limpezas/dia")
    fig = px.bar(longo, x="banheiro", y="limpezas/dia", color="alerta", barmode="group",
                 color_discrete_map={"original": "#c3c2b7", "ajustada": "#2a78d6"},
                 title="Limpeza ideal por dia (fluxo médio / alerta)")
    fig.update_traces(hovertemplate="%{x}<br>%{y:.1f} limpezas/dia<extra></extra>")
    return _layout(fig)


def gantt(tarefas: pd.DataFrame, base: str = "2026-01-01") -> go.Figure:
    t = tarefas.copy()
    t["Início"] = pd.Timestamp(base) + pd.to_timedelta(t.inicio, unit="m")
    t["Fim"] = pd.Timestamp(base) + pd.to_timedelta(t.fim, unit="m")
    t["banheiro"] = t["banheiro"].fillna("")
    fig = px.timeline(t, x_start="Início", x_end="Fim", y="colaborador", color="tipo",
                      color_discrete_map=CORES_TAREFA, hover_data={"banheiro": True, "tipo": True})
    fig.update_yaxes(autorange="reversed", title=None)
    fig.update_xaxes(tickformat="%H:%M", title=None)
    fig.update_layout(legend_title_text="")
    return _layout(fig, altura=max(300, 40 * t.colaborador.nunique() + 120))
