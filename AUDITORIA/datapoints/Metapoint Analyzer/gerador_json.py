# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from analisador_scripts import ResultadoAnalise

MAX_DOUBLE = 1.7976931348623157e308
MARCADOR_MAX = "__SCADA_MAX_DOUBLE_POSITIVO__"
MARCADOR_MIN = "__SCADA_MAX_DOUBLE_NEGATIVO__"


def _normalizar_valores_especiais(valor: Any) -> Any:
    """
    Prepara os valores para serialização sem permitir que o formatador altere
    os limites máximos usados pelo Scada-LTS.
    """
    if isinstance(valor, float):
        if valor == MAX_DOUBLE:
            return MARCADOR_MAX
        if valor == -MAX_DOUBLE:
            return MARCADOR_MIN
        return valor

    if isinstance(valor, dict):
        return {
            chave: _normalizar_valores_especiais(subvalor)
            for chave, subvalor in valor.items()
        }

    if isinstance(valor, list):
        return [
            _normalizar_valores_especiais(item)
            for item in valor
        ]

    if isinstance(valor, tuple):
        return [
            _normalizar_valores_especiais(item)
            for item in valor
        ]

    return valor


def _serializar_json_scada(dados: Any) -> str:
    normalizado = _normalizar_valores_especiais(dados)

    texto = json.dumps(
        normalizado,
        ensure_ascii=False,
        indent=4,
        allow_nan=True,
    )

    texto = texto.replace(
        f'"{MARCADOR_MAX}"',
        "1.7976931348623157E308",
    )
    texto = texto.replace(
        f'"{MARCADOR_MIN}"',
        "-1.7976931348623157E308",
    )

    return texto + "\n"


def _chave_datapoint(candidato) -> str:
    xid = candidato.script.xid.strip()
    if xid:
        return f"xid:{xid}"
    return f"caminho:{candidato.script.caminho_datapoint}"


def gerar_json_confirmados(
    caminho: Path,
    analise: ResultadoAnalise,
) -> int:
    """
    Reúne os objetos proprietários dos candidatos CONFIRMADOS.

    A deduplicação usa o XID como identificador principal e, quando o XID não
    existe, utiliza o caminho do datapoint.
    """
    caminho.parent.mkdir(parents=True, exist_ok=True)

    datapoints: list[dict[str, Any]] = []
    chaves_vistas: set[str] = set()

    confirmados = sorted(
        (
            candidato
            for candidato in analise.candidatos
            if candidato.status == "CONFIRMADO"
        ),
        key=lambda candidato: (
            candidato.script.xid.casefold(),
            candidato.script.caminho_datapoint,
        ),
    )

    for candidato in confirmados:
        chave = _chave_datapoint(candidato)

        if chave in chaves_vistas:
            continue

        proprietario = candidato.script.objeto_proprietario

        if not isinstance(proprietario, dict):
            continue

        datapoints.append(proprietario)
        chaves_vistas.add(chave)

    saida = {
        "dataPoints": datapoints,
    }

    caminho.write_text(
        _serializar_json_scada(saida),
        encoding="utf-8",
        newline="\n",
    )

    return len(datapoints)
