"""Planejador de Limpeza: Streamlit.

Rode com: streamlit run app.py
"""
from __future__ import annotations

from datetime import time
from pathlib import Path

import pandas as pd
import streamlit as st

from planejador import dados, graficos, indicadores
from planejador.alocacao import planejar
from planejador.parametros import Cenario, Checagem, Duracoes, Grupo, Lavacao, Turno

EXEMPLO = Path(__file__).parent / "dados_exemplo"

st.set_page_config(page_title="Planejador de Limpeza", layout="wide")


def minutos(t: time) -> int:
    return t.hour * 60 + t.minute


def pct(v: float) -> str:
    return f"{v:.0%}"


@st.cache_data(show_spinner=False)
def carregar(fluxo_bytes: bytes | None, alertas_bytes: bytes | None):
    import io
    f = io.BytesIO(fluxo_bytes) if fluxo_bytes else EXEMPLO / "fluxo_setembro_2026.csv"
    a = io.BytesIO(alertas_bytes) if alertas_bytes else EXEMPLO / "alertas.csv"
    fluxo = dados.ler_fluxo(f)
    alertas = dados.ler_alertas(a)
    banheiros, sem_alerta, sem_fluxo = dados.cruzar(fluxo, alertas)
    cheio, faltas = dados.preencher_faltas(fluxo)
    cheio = cheio[cheio["id"].isin(banheiros["id"])]
    return cheio, banheiros, faltas, sem_alerta, sem_fluxo


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("Dados")
    up_fluxo = st.file_uploader("CSV de fluxo", type="csv")
    up_alertas = st.file_uploader("CSV de alertas", type="csv")
    try:
        fluxo, banheiros, faltas, sem_alerta, sem_fluxo = carregar(
            up_fluxo.getvalue() if up_fluxo else None, up_alertas.getvalue() if up_alertas else None)
    except ValueError as e:
        st.error(str(e))
        st.stop()
    if not (up_fluxo and up_alertas):
        st.caption("Usando os dados de exemplo (10 banheiros, setembro/2026).")
    if faltas:
        st.caption(f"{faltas} horas sem telemetria foram preenchidas com a média da mesma hora e dia da semana.")
    if sem_alerta:
        st.warning(f"{len(sem_alerta)} banheiro(s) com fluxo e sem alerta ficaram de fora.")
    if sem_fluxo:
        st.warning(f"{len(sem_fluxo)} banheiro(s) com alerta e sem fluxo ficaram de fora.")

    st.header("Filtros")
    predios = sorted(banheiros["building"].unique())
    sel_predios = st.multiselect("Prédios", predios, default=predios)
    andares = sorted(banheiros.loc[banheiros["building"].isin(sel_predios), "floor"].unique())
    sel_andares = st.multiselect("Andares", andares, default=andares)
    dias = st.multiselect("Dias da semana do plano", dados.DIAS_SEMANA, default=dados.DIAS_UTEIS,
                          help="O plano usa o fluxo médio por hora desses dias. Padrão: dia útil típico.")

    st.header("Durações (min)")
    c1, c2 = st.columns(2)
    dur = Duracoes(
        limpeza=c1.number_input("Limpeza", 1, 120, 15),
        lavacao=c2.number_input("Lavação", 1, 240, 20),
        checagem=c1.number_input("Checagem", 1, 60, 5),
        deslocamento=c2.number_input("Deslocamento", 0, 60, 5),
    )

banheiros = banheiros[banheiros["building"].isin(sel_predios) & banheiros["floor"].isin(sel_andares)]
if banheiros.empty or not dias:
    st.info("Escolha ao menos um prédio, um andar e um dia da semana.")
    st.stop()

ids = list(banheiros["id"])
nome = dict(zip(banheiros["id"], banheiros["asset"] + " · " + banheiros["building"] + " " + banheiros["floor"]))
perfil = dados.perfil_demanda(fluxo[fluxo["id"].isin(ids)], dias).reindex(columns=ids, fill_value=0.0)
alerta_original = banheiros.set_index("id")["alerta"].astype(float)

# alertas ajustados ficam na sessão; recomeçam quando os dados mudam
assinatura = (tuple(ids), tuple(alerta_original.values))
if st.session_state.get("assinatura") != assinatura:
    st.session_state["assinatura"] = assinatura
    for i in ids:
        st.session_state[f"alerta::{i}"] = int(alerta_original[i])

st.title("Planejador de Limpeza")
aba_alertas, aba_turnos, aba_plano = st.tabs(["Alertas", "Turnos", "Plano de limpeza"])

# ---------------------------------------------------------------- aba alertas
with aba_alertas:
    st.subheader("Alertas por banheiro")
    st.caption("Limpeza ideal = fluxo médio diário / alerta: quantos alertas apareceriam no dia sem nenhuma limpeza.")
    if st.button("Restaurar alertas originais"):
        for i in ids:
            st.session_state[f"alerta::{i}"] = int(alerta_original[i])
    for predio, grupo in banheiros.groupby("building", sort=True):
        with st.expander(predio, expanded=True):
            cols = st.columns(2)
            for n, i in enumerate(grupo["id"]):
                orig = int(alerta_original[i])
                cols[n % 2].slider(nome[i], 1, max(100, orig * 3), key=f"alerta::{i}",
                                   help=f"Alerta original: {orig}")

alertas = pd.Series({i: float(st.session_state[f"alerta::{i}"]) for i in ids})

with aba_alertas:
    fluxo_dia = perfil.sum()
    tabela = pd.DataFrame({
        "banheiro": [nome[i] for i in ids],
        "fluxo médio/dia": fluxo_dia.round(0).values,
        "alerta original": alerta_original.values.astype(int),
        "alerta": alertas.values.astype(int),
        "original": (fluxo_dia / alerta_original).round(1).values,
        "ajustada": (fluxo_dia / alertas).round(1).values,
    })
    c1, c2, c3 = st.columns(3)
    c1.metric("Banheiros", len(ids))
    c2.metric("Limpeza ideal total/dia", f"{tabela['ajustada'].sum():.0f}",
              delta=f"{tabela['ajustada'].sum() - tabela['original'].sum():+.0f} vs. original", delta_color="off")
    c3.metric("Fluxo médio/dia", f"{fluxo_dia.sum():,.0f}".replace(",", "."))
    st.plotly_chart(graficos.limpeza_ideal(tabela), width="stretch")
    st.dataframe(tabela.rename(columns={"original": "limpeza ideal (original)", "ajustada": "limpeza ideal"}),
                 hide_index=True, width="stretch")

# ---------------------------------------------------------------- aba turnos
with aba_turnos:
    st.subheader("Turnos e equipe")
    c1, c2, c3 = st.columns(3)
    n_turnos = c1.number_input("Quantidade de turnos", 1, 4, 2)
    modo_int = c2.radio("Intervalo", ["Escalonado por grupo", "Fixo (todos param juntos)"], horizontal=True)
    escalas = c3.number_input("Horários de intervalo diferentes", 1, 6, 3,
                              disabled=modo_int.startswith("Fixo"),
                              help="No escalonado, a equipe é dividida e cada parte para num horário seguido do outro.")
    usar_grupos = st.checkbox("Dividir em grupos (cada grupo atende só os seus banheiros)")

    padrao = [("Manhã", time(6), time(14), 4, time(10)), ("Tarde", time(14), time(22), 4, time(17)),
              ("Noite", time(22), time(6), 1, time(2)), ("Madrugada", time(2), time(6), 1, None)]
    turnos: list[Turno] = []
    cols = st.columns(int(n_turnos))
    for k in range(int(n_turnos)):
        nm, ini, fim, n, pausa = padrao[k]
        with cols[k].container(border=True):
            nm = st.text_input("Nome", nm, key=f"t{k}_nome")
            a, b = st.columns(2)
            ini = a.time_input("Início", ini, key=f"t{k}_ini", step=1800)
            fim = b.time_input("Fim", fim, key=f"t{k}_fim", step=1800)
            n = st.slider("Colaboradores", 0, 20, n, key=f"t{k}_n", disabled=usar_grupos)
            tem_pausa = st.checkbox("Tem intervalo", pausa is not None, key=f"t{k}_tp")
            a, b = st.columns(2)
            p_ini = a.time_input("Intervalo às", pausa or time(12), key=f"t{k}_pi", step=1800, disabled=not tem_pausa)
            p_dur = b.number_input("Duração (min)", 15, 180, 60, step=15, key=f"t{k}_pd", disabled=not tem_pausa)
            i_min, f_min = minutos(ini), minutos(fim)
            if turnos and i_min < turnos[0].inicio:  # turno depois da meia-noite: dia operacional continua
                i_min += 24 * 60
                f_min += 24 * 60
            turnos.append(Turno(nm, i_min, f_min, n, minutos(p_ini) if tem_pausa else None, int(p_dur)))

    grupos = None
    if usar_grupos:
        n_grupos = st.number_input("Quantidade de grupos", 1, 6, 2)
        grupos = []
        cols = st.columns(int(n_grupos))
        por_predio = [list(g["id"]) for _, g in banheiros.groupby("building")]
        for g in range(int(n_grupos)):
            with cols[g].container(border=True):
                gnome = st.text_input("Grupo", f"Grupo {g + 1}", key=f"g{g}_nome")
                sugestao = por_predio[g] if g < len(por_predio) else []
                bs = st.multiselect("Banheiros", ids, default=sugestao, format_func=nome.get, key=f"g{g}_b")
                qtd = {t.nome: st.number_input(f"Colaboradores · {t.nome}", 0, 20, 2, key=f"g{g}_{k}")
                       for k, t in enumerate(turnos)}
                grupos.append(Grupo(gnome, bs, qtd))
        sem_grupo = set(ids) - {b for g in grupos for b in g.banheiros}
        if sem_grupo:
            st.warning(f"{len(sem_grupo)} banheiro(s) sem grupo não serão atendidos: "
                       + ", ".join(nome[i] for i in sorted(sem_grupo)))

    with st.expander("Lavações e checagens", expanded=True):
        a, b = st.columns(2)
        with a:
            lav_on = st.toggle("Lavações", True)
            lav_ini = st.time_input("Começam às", time(17), step=1800, disabled=not lav_on)
            maiores = list(fluxo_dia.sort_values(ascending=False).index[:5])
            lav_b = st.multiselect("Banheiros com lavação (1 por dia)", ids, default=maiores,
                                   format_func=nome.get, disabled=not lav_on)
        with b:
            chk_on = st.toggle("Checagens", False)
            opcoes = [time(h, m) for h in range(24) for m in (0, 30)]
            chk_h = st.multiselect("Horários", opcoes, default=[time(10), time(16)],
                                   format_func=lambda t: t.strftime("%H:%M"), disabled=not chk_on)
            chk_b = st.multiselect("Banheiros com checagem", ids, default=ids[:2],
                                   format_func=nome.get, disabled=not chk_on)

    cen = Cenario(
        turnos=turnos, duracoes=dur, intervalo_escalonado=modo_int.startswith("Escalonado"),
        escalas_intervalo=int(escalas), grupos=grupos,
        lavacao=Lavacao(lav_on, minutos(lav_ini), lav_b),
        checagem=Checagem(chk_on, [minutos(t) for t in chk_h], chk_b),
    )
    res = planejar(perfil, alertas, cen)
    sem_limpeza = planejar(perfil, alertas, Cenario(
        turnos=[Turno(t.nome, t.inicio, t.fim, 0) for t in turnos], duracoes=dur))

    st.subheader("A equipe dá conta?")
    rt = indicadores.resumo_turnos(res, cen)
    for _, r in rt.iterrows():
        c = st.columns(6)
        c[0].markdown(f"**{r['turno']}**  \n{int(r['colaboradores'])} colaboradores")
        c[1].metric("Limpezas", int(r["limpezas"]))
        c[2].metric("Lavações", int(r["lavações"]))
        c[3].metric("Atendidos acima de 100%", int(r["atrasos"]))
        c[4].metric("Pior necessidade", pct(r["pico"]))
        c[5].metric("Ocupação da equipe", pct(r["ocupação"]))
    if res.lavacoes_pendentes:
        st.warning("Lavações que não couberam no dia: " + ", ".join(nome[i] for i in res.lavacoes_pendentes))
    if res.checagens_pendentes:
        st.warning(f"{len(res.checagens_pendentes)} checagem(ns) não couberam no dia.")

    visao = st.radio("Mapa de calor", ["Com o plano", "Sem nenhuma limpeza (tela em branco)"], horizontal=True)
    base = res if visao == "Com o plano" else sem_limpeza
    mapa = indicadores.mapa_necessidade(base).rename(index=nome)
    st.plotly_chart(graficos.mapa_calor(
        mapa, "Necessidade por banheiro e hora: 1 = bateu o alerta, 2 = duas limpezas devidas"),
        width="stretch")
    st.caption("Azul: banheiro com folga. Cinza: perto de 100%. Vermelho: passou do alerta e ninguém foi ainda "
               "(1,2 = era para ter sido feita 1,2 limpeza).")
    st.plotly_chart(graficos.capacidade_carga(indicadores.capacidade_carga(res, cen, perfil, alertas)),
                    width="stretch")

# ---------------------------------------------------------------- aba plano
with aba_plano:
    st.subheader("Plano geral")
    rb = indicadores.resumo_banheiros(res, perfil, alertas).rename(index=nome)
    st.dataframe(rb.style.format({"limpeza ideal": "{:.1f}", "pico": "{:.0%}", "cobertura": "{:.0%}"}),
                 width="stretch")

    t = res.tarefas
    atend = t[t.tipo.isin(["limpeza", "lavação", "checagem"])].copy()
    atend["hora"] = (atend.inicio // 60 * 60).map(indicadores.hhmm)
    atend["sigla"] = atend.tipo.map({"limpeza": "L", "lavação": "Lv", "checagem": "C"})
    grade = atend.pivot_table(index="banheiro", columns="hora", values="sigla", aggfunc=" ".join)
    horas = [indicadores.hhmm(h * 60) for h in range(res.inicio // 60, -(-res.fim // 60))]
    grade = grade.reindex(index=ids, columns=horas).fillna("").rename(index=nome)
    st.markdown("**Intervenções por banheiro e hora** (L = limpeza, Lv = lavação, C = checagem)")
    st.dataframe(grade, width="stretch")

    st.subheader("Plano por colaborador")
    st.plotly_chart(graficos.gantt(t.assign(banheiro=t.banheiro.map(nome))), width="stretch")
    colabs = list(dict.fromkeys(t.colaborador))
    if colabs:
        quem = st.selectbox("Colaborador", colabs)
        rot = t[(t.colaborador == quem) & (t.tipo != "deslocamento")].sort_values("inicio")
        st.dataframe(pd.DataFrame({
            "início": rot.inicio.map(indicadores.hhmm), "fim": rot.fim.map(indicadores.hhmm),
            "tarefa": rot.tipo, "banheiro": rot.banheiro.map(nome).fillna(""),
            "necessidade na chegada": rot.necessidade_chegada.map(lambda v: "" if pd.isna(v) else pct(v)),
        }), hide_index=True, width="stretch")
    exp = t.assign(inicio=t.inicio.map(indicadores.hhmm), fim=t.fim.map(indicadores.hhmm),
                   banheiro=t.banheiro.map(nome))
    st.download_button("Baixar plano (CSV)", exp.to_csv(index=False).encode("utf-8-sig"),
                       "plano_limpeza.csv", "text/csv")
