# Planejador de Limpeza

App em Streamlit que monta o plano de limpeza dos banheiros a partir do fluxo
horário (telemetria) e do alerta de cada banheiro.

## Como rodar

```bash
pip install -r requirements.txt
streamlit run app.py
```

Sem upload, o app abre com os dados de exemplo em `dados_exemplo/`
(10 banheiros fictícios, setembro/2026).

## Dados de entrada

**Fluxo** (`corporate, site, building, floor, asset, data, dia_semana, hora, fluxo`):
um registro por banheiro por hora. Horas faltando são preenchidas com a média
da mesma hora e dia da semana do banheiro.

**Alertas** (`corporate, site, building, floor, asset, alerta`): um alerta por banheiro.

A chave do banheiro é a hierarquia inteira. Aceita `,` ou `;` como separador.

## Abas

- **Alertas**: slider por banheiro e limpeza ideal = fluxo médio do dia / alerta.
- **Turnos**: turnos, colaboradores, intervalo fixo ou escalonado, grupos de banheiros,
  lavações e checagens. Mostra se a equipe dá conta, o mapa de calor da necessidade
  (banheiro x hora) e a capacidade x carga por hora.
- **Plano de limpeza**: resumo por banheiro, intervenções por hora, Gantt e roteiro
  por colaborador, download em CSV.

## Regra de alocação

`necessidade = fluxo acumulado desde a última limpeza ou lavação / alerta`

- Limpeza na hora de bater 100%: o colaborador sai para o banheiro no último momento
  em que ainda chega antes de passar do alerta. Se ninguém está para bater 100%, ele espera.
- Lavações começam no horário escolhido. Se lavar agora fizer algum banheiro passar de
  100% antes da próxima volta do colaborador, esse banheiro é atendido antes.
- Lavação zera a necessidade; checagem não.
- O dia operacional começa no primeiro turno com tudo zerado.
- Com grupos, cada colaborador só atende os banheiros do seu grupo.

No mapa de calor, 1 é o alerta; 1,2 quer dizer que já era para ter sido feita
1,2 limpeza e ninguém foi.

## Testes

```bash
python -m pytest
```
