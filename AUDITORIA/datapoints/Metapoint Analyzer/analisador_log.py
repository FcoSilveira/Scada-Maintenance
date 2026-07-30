# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

PADRAO_REFERENCE_ERROR = re.compile(
    r'(?P<tipo>ReferenceError):\s*["\'](?P<variavel>[A-Za-z_$][\w$]*)["\']\s+'
    r'is not defined\.?\s*\(<cmd>#(?P<linha>\d+)\)',
    re.IGNORECASE,
)
PADRAO_DATA_HORA = re.compile(
    r'(?P<data>\d{4}[-/]\d{2}[-/]\d{2}|\d{2}[-/]\d{2}[-/]\d{4})'
    r'(?:[ T]+)(?P<hora>\d{2}:\d{2}:\d{2}(?:[.,]\d{1,6})?)'
)


@dataclass(frozen=True)
class OcorrenciaErro:
    tipo_erro: str
    variavel: str
    linha_script: int
    data: str
    hora: str
    texto_completo: str
    numero_linha_log: int


@dataclass(frozen=True)
class ErroAgrupado:
    tipo_erro: str
    variavel: str
    linha_script: int
    quantidade: int
    ocorrencias: tuple[OcorrenciaErro, ...]

    @property
    def descricao(self) -> str:
        return f'{self.tipo_erro}: "{self.variavel}" is not defined'


@dataclass(frozen=True)
class ResultadoLog:
    total_linhas: int
    total_reference_errors: int
    erros_agrupados: tuple[ErroAgrupado, ...]
    variaveis_distintas: tuple[str, ...]


def _extrair_data_hora(linha: str) -> tuple[str, str]:
    correspondencia = PADRAO_DATA_HORA.search(linha)
    if correspondencia is None:
        return "", ""
    return correspondencia.group("data"), correspondencia.group("hora")


def analisar_log(caminho: Path) -> ResultadoLog:
    grupos: dict[tuple[str, str, int], list[OcorrenciaErro]] = defaultdict(list)
    total_linhas = 0
    total_reference_errors = 0

    with caminho.open("r", encoding="utf-8", errors="replace") as arquivo:
        for numero_linha, linha in enumerate(arquivo, start=1):
            total_linhas += 1
            correspondencia = PADRAO_REFERENCE_ERROR.search(linha)
            if correspondencia is None:
                continue

            total_reference_errors += 1
            tipo_erro = "ReferenceError"
            variavel = correspondencia.group("variavel")
            linha_script = int(correspondencia.group("linha"))
            data, hora = _extrair_data_hora(linha)

            ocorrencia = OcorrenciaErro(
                tipo_erro=tipo_erro,
                variavel=variavel,
                linha_script=linha_script,
                data=data,
                hora=hora,
                texto_completo=linha.rstrip("\r\n"),
                numero_linha_log=numero_linha,
            )
            grupos[(tipo_erro, variavel, linha_script)].append(ocorrencia)

    erros = tuple(
        ErroAgrupado(
            tipo_erro=tipo,
            variavel=variavel,
            linha_script=linha,
            quantidade=len(ocorrencias),
            ocorrencias=tuple(ocorrencias),
        )
        for (tipo, variavel, linha), ocorrencias in sorted(
            grupos.items(),
            key=lambda item: (
                item[0][1].casefold(),
                item[0][2],
                item[0][0].casefold(),
            ),
        )
    )
    variaveis = tuple(sorted({erro.variavel for erro in erros}, key=str.casefold))

    return ResultadoLog(
        total_linhas=total_linhas,
        total_reference_errors=total_reference_errors,
        erros_agrupados=erros,
        variaveis_distintas=variaveis,
    )
