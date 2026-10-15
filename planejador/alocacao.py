"""Regra de alocação: simulação do dia em passos de 5 minutos.

Necessidade de um banheiro = fluxo acumulado desde a última limpeza/lavação / alerta.
A regra é "limpar na hora de bater 100%": o colaborador sai para o banheiro no
último passo em que ainda chega antes de a necessidade passar de 100%.

Toda vez que um colaborador fica livre (dentro do turno e fora do intervalo):
1. checagem marcada para agora (ou atrasada) na área dele: faz a checagem (não zera);
2. bloco de lavação (a partir do horário de início, enquanto houver lavação pendente):
   se lavar agora fizer algum banheiro passar de 100% antes da próxima volta,
   atende esse banheiro primeiro (lavando, se ele também tiver lavação pendente);
   senão, lava o banheiro pendente com maior necessidade;
3. fora do bloco: vai ao banheiro que vai bater 100% primeiro, se já for a hora de sair.
   Se ninguém está para bater 100%, espera.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .parametros import Cenario

PASSO = 5  # minutos
HORIZONTE = 90  # minutos à frente olhados para decidir se precisa antecipar


@dataclass
class Colaborador:
    id: str
    turno: str
    grupo: str | None
    ini: int
    fim: int
    pausa_ini: int
    pausa_fim: int
    area: np.ndarray  # máscara booleana sobre os banheiros
    livre: int = 0


@dataclass
class Resultado:
    tarefas: pd.DataFrame        # colaborador, turno, grupo, inicio, fim, banheiro, tipo, necessidade_chegada
    necessidade: pd.DataFrame    # índice = minuto do dia, colunas = banheiros (necessidade a cada passo)
    colaboradores: list[Colaborador]
    lavacoes_pendentes: list[str]
    checagens_pendentes: list[tuple[int, str]]
    inicio: int
    fim: int


def criar_colaboradores(cen: Cenario, ids: list[str]) -> list[Colaborador]:
    todos = np.ones(len(ids), dtype=bool)
    out: list[Colaborador] = []
    for t in cen.turnos:
        if cen.grupos:
            equipe = []
            for g in cen.grupos:
                area = np.isin(ids, g.banheiros)
                equipe += [(g.nome, area)] * int(g.colaboradores.get(t.nome, 0))
        else:
            equipe = [(None, todos)] * int(t.colaboradores)
        for k, (grupo, area) in enumerate(equipe):
            if t.intervalo_inicio is None:
                p_ini = p_fim = -1
            else:
                p_ini = t.intervalo_inicio
                if p_ini < t.inicio:
                    p_ini += 24 * 60
                if cen.intervalo_escalonado:
                    p_ini += (k % max(1, cen.escalas_intervalo)) * t.intervalo_duracao
                p_fim = p_ini + t.intervalo_duracao
            nome = f"{t.nome} · {grupo + ' · ' if grupo else ''}C{k + 1}"
            out.append(Colaborador(nome, t.nome, grupo, t.inicio, t.fim_abs, p_ini, p_fim, area.copy(), t.inicio))
    return out


def cabe(c: Colaborador, ini: int, fim: int) -> bool:
    """A tarefa termina dentro do turno e não invade o intervalo."""
    return fim <= c.fim and not (c.pausa_ini >= 0 and ini < c.pausa_ini < fim)


def planejar(perfil: pd.DataFrame, alertas: pd.Series, cen: Cenario, antecipar: bool = True) -> Resultado:
    """perfil: fluxo médio por hora (0..23) x banheiro. alertas: alerta por banheiro (mesmos ids)."""
    ids = list(perfil.columns)
    A = alertas.reindex(ids).astype(float).values
    N = len(ids)
    d = cen.duracoes
    t0 = min(t.inicio for t in cen.turnos)
    t1 = max(t.fim_abs for t in cen.turnos)
    K = max(1, (t1 - t0) // PASSO)
    minutos = t0 + PASSO * np.arange(K)

    horas = (minutos // 60) % 24
    taxa = perfil.values[horas] * (PASSO / 60)                  # fluxo por passo
    CUM = np.vstack([np.zeros(N), np.cumsum(taxa, axis=0)])     # CUM[k] = fluxo até o início do passo k
    base = np.zeros(N)                                          # CUM no momento da última intervenção
    ds = math.ceil(d.deslocamento / PASSO)

    def indice_estouro(i: int) -> int:
        """Primeiro índice de CUM em que o banheiro i passa de 100%."""
        return int(np.searchsorted(CUM[:, i], base[i] + A[i], side="right"))

    estouro = np.array([indice_estouro(i) for i in range(N)])
    reservado = np.full(N, -1)                                  # banheiro com alguém indo/atendendo
    colabs = criar_colaboradores(cen, ids)

    lav = cen.lavacao
    lav_pend = np.isin(ids, lav.banheiros) if lav.ativa else np.zeros(N, dtype=bool)
    chk = cen.checagem
    chk_pend = sorted((h, ids.index(b)) for h in chk.horarios for b in chk.banheiros if b in ids) if chk.ativa else []

    def vai_faltar_gente(c: Colaborador, m: int, disp: np.ndarray) -> bool:
        """Simula a fila das próximas limpezas (prazo mais próximo primeiro) com a equipe do
        mesmo turno e grupo, supondo que c espere mais um passo. True se alguém passaria de 100%."""
        livres = []
        for o in colabs:
            if o.turno != c.turno or o.grupo != c.grupo or not (o.ini <= m < o.fim):
                continue
            f = m + PASSO if o is c else max(o.livre, m)
            if o.pausa_ini <= f < o.pausa_fim:
                f = o.pausa_fim
            if f < o.fim:
                livres.append(f)
        if not livres:
            return False
        limite = m + HORIZONTE
        ultimo_ok = t0 + (estouro - 1) * PASSO          # último minuto de chegada sem passar de 100%
        fila = sorted((ultimo_ok[i], i) for i in np.where(disp)[0] if ultimo_ok[i] <= limite)
        for prazo_i, _ in fila:
            k = int(np.argmin(livres))
            chegada = livres[k] + d.deslocamento
            if chegada > prazo_i:
                return True
            # na simulação o colaborador chega em cima do prazo (não antes) e segue
            livres[k] = max(chegada, prazo_i - 0) + d.limpeza
        return False

    hist = np.zeros((K, N))
    tarefas = []

    def registrar(c, ini, fim, i, tipo, n_cheg=np.nan):
        tarefas.append(dict(colaborador=c.id, turno=c.turno, grupo=c.grupo, inicio=ini, fim=fim,
                            banheiro=ids[i] if i is not None else None, tipo=tipo, necessidade_chegada=n_cheg))

    for k in range(K):
        m = int(minutos[k])
        hist[k] = np.maximum(0, CUM[k + 1] - base) / A
        for c in colabs:
            if not (c.ini <= m < c.fim) or c.livre > m or c.pausa_ini <= m < c.pausa_fim:
                continue
            disp = c.area & (reservado <= m)

            # 1. checagem com horário marcado
            j = next((x for x in chk_pend if x[0] <= m and disp[x[1]]), None)
            if j is not None:
                fim = m + d.deslocamento + d.checagem
                if not cabe(c, m, fim):
                    continue
                chk_pend.remove(j)
                i = j[1]
                registrar(c, m, m + d.deslocamento, i, "deslocamento")
                registrar(c, m + d.deslocamento, fim, i, "checagem", hist[k, i])
                reservado[i] = fim
                c.livre = fim
                continue

            chegada = k + 1 + ds                                # índice de CUM na chegada
            lav_disp = lav_pend & disp
            if lav.ativa and m >= lav.inicio and lav_disp.any():
                # 2. bloco de lavação, olhando à frente
                volta = chegada + math.ceil(d.lavacao / PASSO) + ds
                urg = disp & (estouro <= volta)  # passaria de 100% antes da próxima volta
                if urg.any():
                    i = int(np.where(urg, estouro, 10**9).argmin())
                    tipo = "lavação" if lav_pend[i] else "limpeza"
                else:
                    i = int(np.where(lav_disp, hist[k], -1).argmax())
                    tipo = "lavação"
            else:
                # 3. limpeza na hora de bater 100%; antecipa só se esperar fizer alguém estourar
                cand = disp & (estouro <= chegada + 1)
                if not cand.any():
                    if not (antecipar and vai_faltar_gente(c, m, disp)):
                        continue
                    cand = disp & (estouro < K + 1)
                    if not cand.any():
                        continue
                i = int(np.where(cand, estouro, 10**9).argmin())
                tipo = "limpeza"

            dur = d.lavacao if tipo == "lavação" else d.limpeza
            fim = m + d.deslocamento + dur
            if not cabe(c, m, fim):
                continue
            kc = min(chegada, K)
            n_cheg = (CUM[kc, i] - base[i]) / A[i]
            base[i] = CUM[kc, i]
            estouro[i] = indice_estouro(i)
            reservado[i] = fim
            c.livre = fim
            if tipo == "lavação":
                lav_pend[i] = False
            registrar(c, m, m + d.deslocamento, i, "deslocamento")
            registrar(c, m + d.deslocamento, fim, i, tipo, n_cheg)

    for c in colabs:
        if c.pausa_ini >= 0:
            registrar(c, c.pausa_ini, c.pausa_fim, None, "intervalo")

    cols = ["colaborador", "turno", "grupo", "inicio", "fim", "banheiro", "tipo", "necessidade_chegada"]
    tarefas_df = pd.DataFrame(tarefas, columns=cols).sort_values(["colaborador", "inicio"]).reset_index(drop=True)
    return Resultado(
        tarefas=tarefas_df,
        necessidade=pd.DataFrame(hist, index=minutos, columns=ids),
        colaboradores=colabs,
        lavacoes_pendentes=[ids[i] for i in np.where(lav_pend)[0]],
        checagens_pendentes=[(h, ids[i]) for h, i in chk_pend],
        inicio=t0,
        fim=t1,
    )
