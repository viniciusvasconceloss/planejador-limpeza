"""Indicadores calculados a partir do plano."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .alocacao import Resultado
from .parametros import Cenario


def hhmm(minuto: int) -> str:
    minuto = int(minuto) % (24 * 60)
    return f"{minuto // 60:02d}:{minuto % 60:02d}"


def mapa_necessidade(res: Resultado) -> pd.DataFrame:
    """Pior necessidade de cada banheiro em cada hora (linhas = banheiros, colunas = hora).
    1,0 = bateu o alerta; 1,2 = era para ter sido feita 1,2 limpeza e ninguém foi."""
    nec = res.necessidade.copy()
    nec["hora"] = [hhmm((m // 60) * 60) for m in nec.index]
    return nec.groupby("hora", sort=False).max().T


def resumo_banheiros(res: Resultado, perfil: pd.DataFrame, alertas: pd.Series) -> pd.DataFrame:
    t = res.tarefas
    horas = [h % 24 for h in range(res.inicio // 60, -(-res.fim // 60))]
    ideal = perfil.loc[horas].sum() / alertas.reindex(perfil.columns)
    cont = t[t.tipo.isin(["limpeza", "lavação", "checagem"])].pivot_table(
        index="banheiro", columns="tipo", values="inicio", aggfunc="count").reindex(perfil.columns).fillna(0)
    for col in ["limpeza", "lavação", "checagem"]:
        if col not in cont:
            cont[col] = 0
    atendidas = t[t.tipo.isin(["limpeza", "lavação"])]
    atrasos = atendidas[atendidas.necessidade_chegada > 1.0].groupby("banheiro").size().reindex(perfil.columns).fillna(0)
    df = pd.DataFrame({
        "limpeza ideal": ideal.round(1),
        "limpezas": cont["limpeza"].astype(int),
        "lavações": cont["lavação"].astype(int),
        "checagens": cont["checagem"].astype(int),
        "atrasos": atrasos.astype(int),
        "pico": res.necessidade.max(),
    })
    df["cobertura"] = ((df["limpezas"] + df["lavações"]) / df["limpeza ideal"].replace(0, np.nan)).fillna(1.0)
    return df


def capacidade_carga(res: Resultado, cen: Cenario, perfil: pd.DataFrame, alertas: pd.Series) -> pd.DataFrame:
    """Minutos de trabalho por hora: carga (demanda de limpeza + lavações/checagens do plano)
    x capacidade (colaboradores em serviço, fora do intervalo)."""
    d = cen.duracoes
    inicio_h, fim_h = res.inicio // 60, -(-res.fim // 60)
    linhas = []
    t = res.tarefas
    for h in range(inicio_h, fim_h):
        a, b = h * 60, (h + 1) * 60
        limp = float((perfil.loc[h % 24] / alertas.reindex(perfil.columns)).sum()) * (d.limpeza + d.deslocamento)
        extra = {}
        for tipo, dur in (("lavação", d.lavacao), ("checagem", d.checagem)):
            ini = t.loc[t.tipo == tipo, "inicio"]
            extra[tipo] = float(((ini >= a) & (ini < b)).sum()) * (dur + d.deslocamento)
        cap = 0
        for c in res.colaboradores:
            trabalho = max(0, min(b, c.fim) - max(a, c.ini))
            pausa = max(0, min(b, c.pausa_fim, c.fim) - max(a, c.pausa_ini, c.ini)) if c.pausa_ini >= 0 else 0
            cap += trabalho - pausa
        linhas.append(dict(hora=hhmm(a), limpeza=limp, lavação=extra["lavação"], checagem=extra["checagem"], capacidade=cap))
    return pd.DataFrame(linhas)


def resumo_turnos(res: Resultado, cen: Cenario) -> pd.DataFrame:
    t = res.tarefas
    linhas = []
    for tr in cen.turnos:
        do_turno = t[t.turno == tr.nome]
        servico = do_turno[do_turno.tipo != "intervalo"]
        colabs = [c for c in res.colaboradores if c.turno == tr.nome]
        cap = sum((c.fim - c.ini) - (c.pausa_fim - c.pausa_ini if c.pausa_ini >= 0 else 0) for c in colabs)
        ocupado = float((servico.fim - servico.inicio).sum())
        atend = servico[servico.tipo.isin(["limpeza", "lavação"])]
        janela = (res.necessidade.index >= tr.inicio) & (res.necessidade.index < tr.fim_abs)
        linhas.append({
            "turno": tr.nome,
            "colaboradores": len(colabs),
            "limpezas": int((atend.tipo == "limpeza").sum()),
            "lavações": int((atend.tipo == "lavação").sum()),
            "atrasos": int((atend.necessidade_chegada > 1.0).sum()),
            "pico": float(res.necessidade[janela].values.max()) if janela.any() else 0.0,
            "ocupação": ocupado / cap if cap else 0.0,
        })
    return pd.DataFrame(linhas)
