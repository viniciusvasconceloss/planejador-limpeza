import numpy as np
import pandas as pd

from planejador.alocacao import planejar
from planejador.parametros import Cenario, Duracoes, Lavacao, Turno


def perfil_constante(fluxos_hora: dict[str, float]) -> pd.DataFrame:
    return pd.DataFrame({k: [v] * 24 for k, v in fluxos_hora.items()}, index=range(24))


def cenario(n, **kw):
    return Cenario(turnos=[Turno("T", 6 * 60, 14 * 60, n)], duracoes=Duracoes(15, 20, 5, 5), **kw)


def test_limpa_na_hora_de_bater_100():
    # 30 usos/h e alerta 30: bate 100% a cada 60 min
    res = planejar(perfil_constante({"B1": 30}), pd.Series({"B1": 30.0}), cenario(1))
    limp = res.tarefas[res.tarefas.tipo == "limpeza"]
    assert len(limp) > 0
    assert limp.necessidade_chegada.between(0.9, 1.0).all()


def test_sem_excesso_com_equipe_sobrando():
    p, a = perfil_constante({"B1": 30, "B2": 15}), pd.Series({"B1": 30.0, "B2": 30.0})
    poucos = planejar(p, a, cenario(2)).tarefas
    muitos = planejar(p, a, cenario(10)).tarefas
    n = lambda t: (t.tipo == "limpeza").sum()
    assert n(muitos) == n(poucos)  # mais gente não cria limpeza à toa
    assert (muitos.necessidade_chegada.dropna() >= 0.9).all()


def test_falta_de_equipe_aparece_como_atraso():
    p = perfil_constante({f"B{i}": 120 for i in range(6)})
    a = pd.Series({f"B{i}": 30.0 for i in range(6)})
    res = planejar(p, a, cenario(1))
    assert res.necessidade.values.max() > 1.5
    assert (res.tarefas.necessidade_chegada > 1).any()


def test_limpeza_urgente_passa_na_frente_da_lavacao():
    # B1 bate 100% às 07:00. Lavações começam 06:50: lavar B2 primeiro faria B1 estourar,
    # então B1 é limpo antes e a lavação de B2 vem logo depois.
    p, a = perfil_constante({"B1": 30, "B2": 1}), pd.Series({"B1": 30.0, "B2": 100.0})
    res = planejar(p, a, cenario(1, lavacao=Lavacao(True, 6 * 60 + 50, ["B2"])))
    t = res.tarefas[res.tarefas.tipo.isin(["limpeza", "lavação"])]
    depois = t[t.inicio >= 6 * 60 + 50].sort_values("inicio")
    assert list(depois.tipo[:2]) == ["limpeza", "lavação"]
    assert depois.banheiro.iloc[0] == "B1"
    assert (t[t.banheiro == "B1"].necessidade_chegada <= 1.0 + 1e-9).all()


def test_lavacao_zera_e_checagem_nao():
    from planejador.parametros import Checagem
    p, a = perfil_constante({"B1": 10}), pd.Series({"B1": 1000.0})
    res = planejar(p, a, cenario(1, lavacao=Lavacao(True, 8 * 60, ["B1"]), checagem=Checagem(True, [7 * 60], ["B1"])))
    nec = res.necessidade["B1"]
    lav = res.tarefas[res.tarefas.tipo == "lavação"].inicio.iloc[0]
    chk = res.tarefas[res.tarefas.tipo == "checagem"].inicio.iloc[0]
    assert nec.loc[chk + 15] > nec.loc[chk - 5]          # checagem não zerou
    assert nec.loc[lav + 10] < nec.loc[lav - 5]          # lavação zerou


def test_grupos_so_atendem_seus_banheiros():
    from planejador.parametros import Grupo
    p, a = perfil_constante({"B1": 30, "B2": 30}), pd.Series({"B1": 30.0, "B2": 30.0})
    cen = cenario(0, grupos=[Grupo("G1", ["B1"], {"T": 1}), Grupo("G2", ["B2"], {"T": 1})])
    t = planejar(p, a, cen).tarefas
    t = t[t.tipo == "limpeza"]
    for g, b in (("G1", "B1"), ("G2", "B2")):
        assert set(t[t.grupo == g].banheiro) == {b}


def test_antecipa_quando_varios_banheiros_batem_100_juntos():
    # três banheiros iguais batem 100% no mesmo minuto: esperar até a última hora atrasa dois deles
    p = perfil_constante({f"B{i}": 30 for i in range(3)})
    a = pd.Series({f"B{i}": 30.0 for i in range(3)})
    atrasos = lambda r: (r.tarefas.necessidade_chegada > 1).sum()
    so_na_hora = planejar(p, a, cenario(1), antecipar=False)
    com_antecipacao = planejar(p, a, cenario(1))
    assert atrasos(com_antecipacao) < atrasos(so_na_hora)
