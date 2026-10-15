"""Gráficos Plotly do app. Todas as cores de tarefa vêm de CORES, para os gráficos
de turnos e de plano falarem a mesma língua."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

# limpeza roxo, lavação laranja, checagem rosa (validadas juntas: separáveis inclusive para daltonismo)
CORES = {
    "limpeza": "#6a4fd6",
    "lavação": "#f07a1a",
    "checagem": "#e05ca8",
    "deslocamento": "#d9d7d0",
    "intervalo": "#f1f0ec",
}
TEXTO, TEXTO_2, GRADE = "#2b2a28", "#6b6a65", "#ecebe7"
FONTE = "Source Sans Pro, Inter, system-ui, sans-serif"

# mapa de calor "fogo": amarelo bem claro em 0, laranja forte e vermelho no máximo
FOGO = [[0.0, "#fffbe8"], [0.2, "#fff0b8"], [1 / 3, "#ffd166"], [0.5, "#fb9b35"],
        [0.75, "#ea5a1f"], [1.0, "#b51d14"]]
ESCALA_MAX = 3.0
DIA_BASE = pd.Timestamp("2026-01-01")


def _estilo(fig: go.Figure, titulo: str, altura: int, legenda: bool = True) -> go.Figure:
    fig.update_layout(
        height=altura,
        title=dict(text=titulo, x=0, xanchor="left", font=dict(size=16, color=TEXTO, family=FONTE)),
        font=dict(family=FONTE, size=13, color=TEXTO_2),
        margin=dict(l=8, r=8, t=56, b=8),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        showlegend=legenda,
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=1, xanchor="right",
                    title_text="", font=dict(size=12), bgcolor="rgba(0,0,0,0)"),
        hoverlabel=dict(bgcolor="white", bordercolor=GRADE, font=dict(family=FONTE, size=13, color=TEXTO)),
    )
    fig.update_xaxes(showline=False, ticks="", gridcolor=GRADE, zeroline=False)
    fig.update_yaxes(showline=False, ticks="", gridcolor=GRADE, zeroline=False)
    return fig


def _hhmm(m: int) -> str:
    m = int(m) % (24 * 60)
    return f"{m // 60:02d}:{m % 60:02d}"


def mapa_calor(mapa: pd.DataFrame, titulo: str) -> go.Figure:
    """Banheiro x hora; valor = pior necessidade da hora em limpezas (1 = bateu o alerta)."""
    z = mapa.values
    fig = go.Figure(go.Heatmap(
        z=z, x=list(mapa.columns), y=list(mapa.index), zmin=0, zmax=ESCALA_MAX,
        colorscale=FOGO, xgap=3, ygap=3,
        colorbar=dict(title=dict(text="limpezas", side="top"), tickvals=[0, 1, 2, 3],
                      ticktext=["0", "1 · alerta", "2", "3+"], thickness=12, len=0.9, outlinewidth=0),
        hovertemplate="<b>%{y}</b><br>%{x}<br>%{z:.1f} limpezas<extra></extra>",
    ))
    # números só onde passou do alerta; texto claro nas células escuras
    for r, banheiro in enumerate(mapa.index):
        for c, hora in enumerate(mapa.columns):
            v = z[r, c]
            if v >= 1.05:
                fig.add_annotation(x=hora, y=banheiro, text=f"{v:.1f}".replace(".", ","), showarrow=False,
                                   font=dict(size=11, color="white" if v >= 1.8 else TEXTO))
    fig.update_yaxes(autorange="reversed", showgrid=False)
    fig.update_xaxes(showgrid=False)
    return _estilo(fig, titulo, max(320, 38 * len(mapa) + 110), legenda=False)


def capacidade_carga(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    for col in ("limpeza", "lavação", "checagem"):
        if df[col].sum() == 0:
            continue
        fig.add_bar(x=df.hora, y=df[col], name=col, marker=dict(color=CORES[col], line=dict(width=0)),
                    hovertemplate=f"{col}: %{{y:.0f}} min<extra></extra>")
    fig.add_scatter(x=df.hora, y=df.capacidade, name="capacidade da equipe", mode="lines",
                    line=dict(color=TEXTO, width=2, dash="dot", shape="hv"),
                    hovertemplate="capacidade: %{y:.0f} min<extra></extra>")
    fig.update_layout(barmode="stack", bargap=0.35, barcornerradius=4, hovermode="x unified")
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(title=dict(text="minutos de trabalho", font=dict(size=12)), rangemode="tozero")
    return _estilo(fig, "Capacidade da equipe x carga de trabalho, por hora", 380)


def linha_do_tempo(t: pd.DataFrame, eixo: str, titulo: str, tipos: list[str],
                   ordem: list[str] | None = None, altura_linha: int = 34) -> go.Figure:
    """Barras horizontais no tempo. eixo = coluna das linhas (banheiro ou colaborador)."""
    t = t[t.tipo.isin(tipos)].copy()
    linhas = ordem or list(dict.fromkeys(t[eixo].dropna()))
    fig = go.Figure()
    for tipo in tipos:
        p = t[t.tipo == tipo]
        if p.empty:
            continue
        ini, fim = p.inicio.astype(int), p.fim.astype(int)
        rotulo = (p.colaborador if eixo == "banheiro" else p.banheiro).fillna("").astype(str)
        fig.add_bar(
            y=p[eixo], x=(fim - ini).values * 60_000,
            base=(DIA_BASE + pd.to_timedelta(ini.values, unit="m")).strftime("%Y-%m-%d %H:%M"),
            orientation="h", name=tipo,
            width=0.36 if tipo == "deslocamento" else 0.7,
            marker=dict(color=CORES[tipo], line=dict(color="white", width=1),
                        pattern=dict(shape="/", fgcolor="#cfccc4", size=6) if tipo == "intervalo" else None),
            customdata=list(zip(ini.map(_hhmm), fim.map(_hhmm), rotulo)),
            hovertemplate=f"<b>{tipo}</b> %{{customdata[0]}}–%{{customdata[1]}}<br>%{{customdata[2]}}<extra></extra>",
        )
    fig.update_layout(barmode="overlay", barcornerradius=3)
    fig.update_xaxes(type="date", tickformat="%H:%M", dtick=3_600_000, gridcolor=GRADE)
    fig.update_yaxes(categoryorder="array", categoryarray=linhas, autorange="reversed", showgrid=False)
    return _estilo(fig, titulo, max(300, altura_linha * len(linhas) + 110))


GRADE_TIPOS = ["vazio", "intervalo", "limpeza", "lavação", "checagem"]
GRADE_CORES = ["#f6f5f2", "#e2e0da", CORES["limpeza"], CORES["lavação"], CORES["checagem"]]


def grade_15min(t: pd.DataFrame, eixo: str, titulo: str, inicio: int, fim: int,
                ordem: list[str] | None = None, altura_linha: int = 34) -> go.Figure:
    """Grade de blocos de 15 minutos: cada célula mostra o que a linha (banheiro ou colaborador)
    está fazendo naquele bloco. Cada tarefa entra no bloco em que começa; o intervalo ocupa
    todos os blocos que cobre. Deslocamento não aparece (fica dentro do bloco)."""
    t = t[t.tipo.isin(GRADE_TIPOS)]
    linhas = ordem or list(dict.fromkeys(t[eixo].dropna()))
    s0 = inicio // 15 * 15
    blocos = list(range(s0, fim, 15))
    pos = {r: n for n, r in enumerate(linhas)}
    z = [[0] * len(blocos) for _ in linhas]
    dica = [[f"{_hhmm(b)}–{_hhmm(b + 15)}" for b in blocos] for _ in linhas]
    outro = "colaborador" if eixo == "banheiro" else "banheiro"

    def marcar(r, c, tipo, texto):
        if 0 <= c < len(blocos):
            if GRADE_TIPOS.index(tipo) >= z[r][c]:
                z[r][c] = GRADE_TIPOS.index(tipo)
            dica[r][c] += f"<br><b>{tipo}</b> {texto}"

    for _, x in t.iterrows():
        if x[eixo] not in pos:
            continue
        r = pos[x[eixo]]
        texto = f"{_hhmm(x.inicio)}–{_hhmm(x.fim)}"
        if isinstance(x.get(outro), str) and x[outro]:
            texto += f" · {x[outro].split('<br>')[0]}"
        if x.tipo == "intervalo":
            for c in range((int(x.inicio) - s0) // 15, -(-(int(x.fim) - s0) // 15)):
                if 0 <= c < len(blocos) and z[r][c] == 0:
                    z[r][c] = 1
                    dica[r][c] += f"<br><b>intervalo</b> {texto}"
            continue
        c0 = (int(x.inicio) - s0) // 15
        for c in range(c0, c0 + max(1, round((x.fim - x.inicio) / 15))):
            marcar(r, c, x.tipo, texto)

    n = len(GRADE_TIPOS)
    escala = []
    for k, cor in enumerate(GRADE_CORES):
        escala += [[k / n, cor], [(k + 1) / n, cor]]
    fig = go.Figure(go.Heatmap(
        z=z, x=list(range(len(blocos))), y=linhas, zmin=-0.5, zmax=n - 0.5, colorscale=escala,
        showscale=False, xgap=1, ygap=3, customdata=dica, hovertemplate="%{customdata}<extra></extra>",
    ))
    # linhas mais marcadas a cada hora
    for c, b in enumerate(blocos):
        if b % 60 == 0 and c:
            fig.add_vline(x=c - 0.5, line=dict(color="#bdbab2", width=1))
    for tipo in ("limpeza", "lavação", "checagem", "intervalo"):
        if (t.tipo == tipo).any():
            fig.add_scatter(x=[None], y=[None], mode="markers", name=tipo,
                            marker=dict(symbol="square", size=12, color=GRADE_CORES[GRADE_TIPOS.index(tipo)]))
    horas = [c for c, b in enumerate(blocos) if b % 60 == 0]
    fig.update_xaxes(tickvals=horas, ticktext=[_hhmm(blocos[c]) for c in horas], showgrid=False,
                     range=[-0.5, len(blocos) - 0.5])
    fig.update_yaxes(autorange="reversed", showgrid=False)
    return _estilo(fig, titulo, max(260, altura_linha * len(linhas) + 110))
