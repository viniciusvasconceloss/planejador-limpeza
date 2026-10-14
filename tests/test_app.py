from streamlit.testing.v1 import AppTest


def test_app_abre_com_dados_de_exemplo():
    at = AppTest.from_file("../app.py", default_timeout=60).run()
    assert not at.exception
    assert len(at.tabs) == 3


def test_mais_colaboradores_menos_atrasos():
    at = AppTest.from_file("../app.py", default_timeout=60).run()
    def atrasos():
        return sum(int(m.value) for m in at.metric if m.label == "Atendidos acima de 100%")
    at.slider(key="t0_n").set_value(1).run(); at.slider(key="t1_n").set_value(1).run()
    poucos = atrasos()
    at.slider(key="t0_n").set_value(8).run(); at.slider(key="t1_n").set_value(8).run()
    assert not at.exception
    assert atrasos() < poucos
