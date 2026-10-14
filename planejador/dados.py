"""Leitura e preparação dos CSVs de fluxo e de alertas."""
from __future__ import annotations

import io

import numpy as np
import pandas as pd

HIERARQUIA = ["corporate", "site", "building", "floor", "asset"]
DIAS_SEMANA = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
DIAS_UTEIS = DIAS_SEMANA[:5]

COLUNAS_FLUXO = HIERARQUIA + ["data", "hora", "fluxo"]
COLUNAS_ALERTA = HIERARQUIA + ["alerta"]


def _ler_csv(arquivo) -> pd.DataFrame:
    """Lê CSV com `,` ou `;` (Excel BR) e vírgula decimal."""
    if hasattr(arquivo, "read"):
        bruto = arquivo.read()
        if isinstance(bruto, bytes):
            bruto = bruto.decode("utf-8-sig")
        arquivo = io.StringIO(bruto)
    df = pd.read_csv(arquivo, sep=None, engine="python", decimal=",")
    df.columns = [c.strip().lower() for c in df.columns]
    return df


def _checar_colunas(df: pd.DataFrame, obrigatorias: list[str], nome: str) -> None:
    faltando = [c for c in obrigatorias if c not in df.columns]
    if faltando:
        raise ValueError(f"CSV de {nome} sem as colunas: {', '.join(faltando)}")


def ler_fluxo(arquivo) -> pd.DataFrame:
    df = _ler_csv(arquivo)
    _checar_colunas(df, COLUNAS_FLUXO, "fluxo")
    df["data"] = pd.to_datetime(df["data"]).dt.normalize()
    df["h"] = df["hora"].astype(str).str.slice(0, 2).astype(int)
    df["fluxo"] = pd.to_numeric(df["fluxo"], errors="coerce").fillna(0).clip(lower=0)
    # dia_semana vem no CSV; se faltar ou vier vazio, calcula pela data
    calculado = df["data"].dt.weekday.map(lambda i: DIAS_SEMANA[i])
    if "dia_semana" not in df.columns:
        df["dia_semana"] = calculado
    else:
        df["dia_semana"] = df["dia_semana"].astype(str).str.strip().str.lower()
        df.loc[~df["dia_semana"].isin(DIAS_SEMANA), "dia_semana"] = calculado
    for c in HIERARQUIA:
        df[c] = df[c].astype(str).str.strip()
    return df


def ler_alertas(arquivo) -> pd.DataFrame:
    df = _ler_csv(arquivo)
    _checar_colunas(df, COLUNAS_ALERTA, "alertas")
    for c in HIERARQUIA:
        df[c] = df[c].astype(str).str.strip()
    df["alerta"] = pd.to_numeric(df["alerta"], errors="coerce")
    return df.dropna(subset=["alerta"]).drop_duplicates(HIERARQUIA, keep="last")


def chave(df: pd.DataFrame) -> pd.Series:
    """Identificador único do banheiro: a hierarquia inteira."""
    return df[HIERARQUIA].agg(" / ".join, axis=1)


def preencher_faltas(fluxo: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Completa as horas que a telemetria não mandou com a média da mesma
    hora e dia da semana daquele banheiro. Devolve o df completo e quantas
    horas foram preenchidas."""
    fluxo = fluxo.copy()
    fluxo["id"] = chave(fluxo)
    ids = fluxo["id"].unique()
    datas = pd.date_range(fluxo["data"].min(), fluxo["data"].max(), freq="D")
    grade = pd.MultiIndex.from_product([ids, datas, range(24)], names=["id", "data", "h"]).to_frame(index=False)
    cheio = grade.merge(fluxo[["id", "data", "h", "fluxo"]], on=["id", "data", "h"], how="left")
    cheio["dia_semana"] = cheio["data"].dt.weekday.map(lambda i: DIAS_SEMANA[i])
    faltas = int(cheio["fluxo"].isna().sum())
    media = cheio.groupby(["id", "dia_semana", "h"])["fluxo"].transform("mean")
    cheio["fluxo"] = cheio["fluxo"].fillna(media).fillna(0)
    return cheio, faltas


def perfil_demanda(fluxo_cheio: pd.DataFrame, dias: list[str]) -> pd.DataFrame:
    """Fluxo médio por hora (linhas 0..23) x banheiro (colunas), só com os dias escolhidos."""
    sel = fluxo_cheio[fluxo_cheio["dia_semana"].isin(dias)]
    if sel.empty:
        return pd.DataFrame(index=range(24))
    perfil = sel.pivot_table(index="h", columns="id", values="fluxo", aggfunc="mean")
    return perfil.reindex(range(24)).fillna(0.0)


def cruzar(fluxo: pd.DataFrame, alertas: pd.DataFrame) -> tuple[pd.DataFrame, list[str], list[str]]:
    """Tabela de banheiros (hierarquia + alerta) e avisos de banheiros sem par."""
    a = alertas.copy()
    a["id"] = chave(a)
    ids_fluxo = set(chave(fluxo.drop_duplicates(HIERARQUIA)))
    sem_alerta = sorted(ids_fluxo - set(a["id"]))
    sem_fluxo = sorted(set(a["id"]) - ids_fluxo)
    banheiros = a[a["id"].isin(ids_fluxo)].reset_index(drop=True)
    return banheiros, sem_alerta, sem_fluxo


def limpeza_ideal(perfil: pd.DataFrame, alertas: pd.Series, inicio_h: int = 0, fim_h: int = 24) -> pd.Series:
    """Limpezas por dia = fluxo médio do dia (na janela de horas) / alerta.
    É quantos alertas apareceriam numa 'tela em branco', sem nenhuma limpeza."""
    horas = [h % 24 for h in range(inicio_h, fim_h)]
    total = perfil.loc[horas].sum()
    return (total / alertas.reindex(total.index)).replace([np.inf, -np.inf], np.nan).fillna(0)
