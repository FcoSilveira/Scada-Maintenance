# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from config import CAMPOS_SCRIPT_CONHECIDOS, INDICADORES_JAVASCRIPT

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScriptEncontrado:
    script_id: int
    campo_script: str
    script: str
    caminho_datapoint: str
    caminho_script: str
    tipo_elemento: str
    datasource: str
    device: str
    datapoint: str
    xid: str
    habilitado: str
    contexto: tuple[str, ...]
    contexto_determinado: bool
    objeto_proprietario: dict[str, Any]

    @property
    def caminho_json(self) -> str:
        return self.caminho_script


@dataclass(frozen=True)
class ResultadoJson:
    scripts: tuple[ScriptEncontrado, ...]
    total_meta_data_points: int


def _parece_javascript(chave: str, valor: str) -> bool:
    if chave in CAMPOS_SCRIPT_CONHECIDOS:
        return bool(valor.strip())
    chave_normalizada = chave.casefold()
    if "script" in chave_normalizada or "javascript" in chave_normalizada:
        return bool(valor.strip())
    texto = valor.strip()
    return len(texto) >= 3 and any(indicador in texto for indicador in INDICADORES_JAVASCRIPT)


def _caminho(partes: list[str]) -> str:
    resultado = "$"
    for parte in partes:
        resultado += parte if parte.startswith("[") else "." + parte
    return resultado


def _texto(objeto: dict[str, Any], *chaves: str) -> str:
    for chave in chaves:
        valor = objeto.get(chave)
        if valor is not None and not isinstance(valor, (dict, list)):
            return str(valor)
    return ""


def _habilitado(objeto: dict[str, Any]) -> str:
    valor = objeto.get("enabled")
    if isinstance(valor, bool):
        return "SIM" if valor else "NÃO"
    if valor is None:
        return "DESCONHECIDO"
    return str(valor)


def _contexto_point_locator(point_locator: Any) -> tuple[tuple[str, ...], bool]:
    if not isinstance(point_locator, dict) or "context" not in point_locator:
        return tuple(), False
    contexto = point_locator.get("context")
    if not isinstance(contexto, list):
        return tuple(), False
    variaveis: set[str] = set()
    for item in contexto:
        if not isinstance(item, dict):
            continue
        var_name = item.get("varName")
        if isinstance(var_name, str) and var_name.strip():
            variaveis.add(var_name.strip())
    return tuple(sorted(variaveis, key=str.casefold)), True


def _criar_script_datapoint(
    script_id: int,
    indice: int,
    datapoint: dict[str, Any],
) -> ScriptEncontrado | None:
    point_locator = datapoint.get("pointLocator", {})
    if not isinstance(point_locator, dict):
        return None
    script = point_locator.get("script", "")
    if not isinstance(script, str) or not script.strip():
        return None

    contexto, determinado = _contexto_point_locator(point_locator)
    caminho_datapoint = f"$.dataPoints[{indice}]"
    return ScriptEncontrado(
        script_id=script_id,
        campo_script="script",
        script=script,
        caminho_datapoint=caminho_datapoint,
        caminho_script=f"{caminho_datapoint}.pointLocator.script",
        tipo_elemento="Meta Data Point",
        datasource=_texto(datapoint, "dataSourceXid", "dataSource", "datasource"),
        device=_texto(datapoint, "deviceName", "device"),
        datapoint=_texto(datapoint, "name", "pointName", "dataPointName"),
        xid=_texto(datapoint, "xid", "XID"),
        habilitado=_habilitado(datapoint),
        contexto=contexto,
        contexto_determinado=determinado,
        objeto_proprietario=datapoint,
    )


def _contexto_generico(proprietario: dict[str, Any]) -> tuple[tuple[str, ...], bool]:
    point_locator = proprietario.get("pointLocator")
    contexto, determinado = _contexto_point_locator(point_locator)
    if determinado:
        return contexto, determinado
    contexto_direto = proprietario.get("context")
    if not isinstance(contexto_direto, list):
        return tuple(), False
    variaveis = {
        item.get("varName").strip()
        for item in contexto_direto
        if isinstance(item, dict)
        and isinstance(item.get("varName"), str)
        and item.get("varName").strip()
    }
    return tuple(sorted(variaveis, key=str.casefold)), True


def _percorrer_generico(
    valor: Any,
    partes: list[str],
    proprietario: dict[str, Any] | None = None,
    caminho_proprietario: list[str] | None = None,
) -> Iterator[tuple[dict[str, Any], list[str], str, str, list[str]]]:
    if isinstance(valor, dict):
        dono = proprietario if proprietario is not None else valor
        caminho_dono = caminho_proprietario if caminho_proprietario is not None else partes
        for chave, subvalor in valor.items():
            novo_caminho = [*partes, chave]
            # O pointLocator pertence ao objeto pai; preserve esse proprietário.
            if chave == "pointLocator" and isinstance(subvalor, dict):
                yield from _percorrer_generico(subvalor, novo_caminho, valor, partes)
                continue
            if isinstance(subvalor, str) and _parece_javascript(chave, subvalor):
                yield dono, caminho_dono, chave, subvalor, novo_caminho
            if isinstance(subvalor, (dict, list)):
                yield from _percorrer_generico(subvalor, novo_caminho, None, None)
    elif isinstance(valor, list):
        for indice, item in enumerate(valor):
            yield from _percorrer_generico(item, [*partes, f"[{indice}]"], None, None)


def _criar_script_generico(
    script_id: int,
    proprietario: dict[str, Any],
    caminho_proprietario: list[str],
    campo: str,
    script: str,
    caminho_script: list[str],
) -> ScriptEncontrado:
    contexto, determinado = _contexto_generico(proprietario)
    point_locator = proprietario.get("pointLocator")
    tipo = "Meta Data Point" if isinstance(point_locator, dict) and "context" in point_locator else "Elemento SCADA com script"
    return ScriptEncontrado(
        script_id=script_id,
        campo_script=campo,
        script=script,
        caminho_datapoint=_caminho(caminho_proprietario),
        caminho_script=_caminho(caminho_script),
        tipo_elemento=tipo,
        datasource=_texto(proprietario, "dataSourceXid", "dataSource", "datasource"),
        device=_texto(proprietario, "deviceName", "device"),
        datapoint=_texto(proprietario, "name", "pointName", "dataPointName"),
        xid=_texto(proprietario, "xid", "XID"),
        habilitado=_habilitado(proprietario),
        contexto=contexto,
        contexto_determinado=determinado,
        objeto_proprietario=proprietario,
    )


def _analisar_completo(caminho: Path) -> ResultadoJson:
    with caminho.open("r", encoding="utf-8-sig") as arquivo:
        dados = json.load(arquivo)

    scripts: list[ScriptEncontrado] = []
    chaves_vistas: set[tuple[str, str]] = set()
    script_id = 0
    total_meta = 0

    data_points = dados.get("dataPoints", []) if isinstance(dados, dict) else []
    if isinstance(data_points, list):
        for indice, datapoint in enumerate(data_points):
            if not isinstance(datapoint, dict):
                continue
            candidato = _criar_script_datapoint(script_id + 1, indice, datapoint)
            if candidato is None:
                continue
            script_id += 1
            total_meta += 1
            scripts.append(candidato)
            chaves_vistas.add((candidato.caminho_script, candidato.script))

    for proprietario, caminho_dono, campo, script, caminho_script in _percorrer_generico(dados, []):
        caminho_script_texto = _caminho(caminho_script)
        chave = (caminho_script_texto, script)
        if chave in chaves_vistas:
            continue
        script_id += 1
        encontrado = _criar_script_generico(
            script_id,
            proprietario,
            caminho_dono,
            campo,
            script,
            caminho_script,
        )
        total_meta += int(encontrado.tipo_elemento == "Meta Data Point")
        scripts.append(encontrado)
        chaves_vistas.add(chave)

    return ResultadoJson(tuple(scripts), total_meta)


def analisar_json(caminho: Path) -> ResultadoJson:
    # A leitura completa é usada para garantir que os metadados sejam obtidos
    # do objeto proprietário e que scripts fora de dataPoints também sejam vistos.
    return _analisar_completo(caminho)
