"""Parâmetros do cenário. Tempos em minutos desde 00:00 do dia operacional."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Duracoes:
    limpeza: int = 15
    lavacao: int = 20
    checagem: int = 5
    deslocamento: int = 5


@dataclass
class Turno:
    nome: str
    inicio: int            # minutos, ex.: 6*60
    fim: int               # minutos; se menor que o início, passa da meia-noite
    colaboradores: int = 1
    intervalo_inicio: int | None = None   # None = sem intervalo
    intervalo_duracao: int = 60

    @property
    def fim_abs(self) -> int:
        return self.fim if self.fim > self.inicio else self.fim + 24 * 60


@dataclass
class Grupo:
    nome: str
    banheiros: list[str]
    colaboradores: dict[str, int] = field(default_factory=dict)  # nome do turno -> quantidade


@dataclass
class Lavacao:
    ativa: bool = False
    inicio: int = 17 * 60
    banheiros: list[str] = field(default_factory=list)


@dataclass
class Checagem:
    ativa: bool = False
    horarios: list[int] = field(default_factory=list)
    banheiros: list[str] = field(default_factory=list)


@dataclass
class Cenario:
    turnos: list[Turno]
    duracoes: Duracoes = field(default_factory=Duracoes)
    intervalo_escalonado: bool = True
    escalas_intervalo: int = 3          # quantos horários de intervalo diferentes no modo escalonado
    grupos: list[Grupo] | None = None   # None = qualquer colaborador atende qualquer banheiro
    lavacao: Lavacao = field(default_factory=Lavacao)
    checagem: Checagem = field(default_factory=Checagem)
