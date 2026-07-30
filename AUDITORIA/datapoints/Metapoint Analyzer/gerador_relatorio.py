# -*- coding: utf-8 -*-
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from analisador_json import ResultadoJson
from analisador_log import ErroAgrupado, ResultadoLog
from analisador_scripts import Candidato, ResultadoAnalise

SEPARADOR = "=" * 60
SUBSEPARADOR = "-" * 60
PRIORIDADE_STATUS = {"CONFIRMADO": 0, "PROVÁVEL": 1, "POSSÍVEL": 2}


def _valor(valor: str) -> str:
    return valor if valor else "NÃO INFORMADO"


def _xid(candidato: Candidato) -> str:
    return candidato.script.xid.strip() or candidato.script.caminho_datapoint


def _script_numerado(script: str) -> str:
    linhas = script.splitlines() or [""]
    return "\n".join(
        f"{numero:04d} | {linha}"
        for numero, linha in enumerate(linhas, start=1)
    )


def _linhas_uso(candidato: Candidato) -> str:
    linhas_script = candidato.script.script.splitlines()
    resultado: list[str] = []
    for numero in candidato.linhas_uso:
        conteudo = linhas_script[numero - 1] if 1 <= numero <= len(linhas_script) else ""
        resultado.append(f"{numero}: {conteudo}")
    return "\n".join(resultado) if resultado else "NENHUMA"


def _contexto(candidato: Candidato) -> str:
    if not candidato.script.contexto:
        return "NENHUMA OU NÃO DETERMINADA"
    return "\n".join(candidato.script.contexto)


def _motivo_erro(candidato: Candidato) -> str:
    linhas = ", ".join(str(linha) for linha in candidato.linhas_uso)
    termo_linha = "na linha" if len(candidato.linhas_uso) == 1 else "nas linhas"
    return (
        f'A variável "{candidato.variavel}" é utilizada como identificador independente '
        f'{termo_linha} {linhas}, mas não existe no pointLocator.context, '
        "não foi declarada no script e não foi recebida como parâmetro de função."
    )


def _correcao_provavel(candidato: Candidato) -> str:
    return (
        f'Adicionar "{candidato.variavel}" ao contexto do Meta Data Point, '
        "apontando para o datapoint correto, ou alterar o script para usar o "
        "varName já configurado no contexto."
    )


def _chave_erro(candidato: Candidato) -> tuple[str, int, str]:
    return candidato.variavel, candidato.linha_log, candidato.tipo_erro


def _grupos(
    resultado_analise: ResultadoAnalise,
) -> dict[tuple[str, int, str], list[Candidato]]:
    grupos: dict[tuple[str, int, str], list[Candidato]] = defaultdict(list)
    for candidato in resultado_analise.candidatos:
        grupos[_chave_erro(candidato)].append(candidato)
    for candidatos in grupos.values():
        candidatos.sort(
            key=lambda c: (
                PRIORIDADE_STATUS[c.status],
                -c.confianca,
                _xid(c).casefold(),
            )
        )
    return dict(
        sorted(
            grupos.items(),
            key=lambda item: (
                item[0][0].casefold(),
                item[0][1],
                item[0][2].casefold(),
            ),
        )
    )


def _mapa_erros(log: ResultadoLog) -> dict[tuple[str, int, str], ErroAgrupado]:
    return {
        (erro.variavel, erro.linha_script, erro.tipo_erro): erro
        for erro in log.erros_agrupados
    }


def gerar_relatorio(
    caminho: Path,
    log: ResultadoLog,
    resultado_json: ResultadoJson,
    analise: ResultadoAnalise,
) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    grupos = _grupos(analise)
    erros = _mapa_erros(log)

    # Garante que erros sem candidatos também sejam exibidos.
    for chave in erros:
        grupos.setdefault(chave, [])
    grupos = dict(sorted(grupos.items(), key=lambda item: (item[0][0].casefold(), item[0][1], item[0][2].casefold())))

    with caminho.open("w", encoding="utf-8", newline="\n") as arquivo:
        arquivo.write(SEPARADOR + "\n")
        arquivo.write("RESUMO GERAL\n")
        arquivo.write(SEPARADOR + "\n\n")

        for (variavel, linha, tipo), candidatos in grupos.items():
            arquivo.write(f"ERRO: {variavel} não definido — linha {linha}\n")
            arquivo.write("XIDs encontrados:\n")
            if candidatos:
                for candidato in candidatos:
                    arquivo.write(f"- {_xid(candidato)}\n")
            else:
                arquivo.write("- NENHUM DATAPOINT COMPATÍVEL ENCONTRADO\n")
            arquivo.write("\n")

        for chave, candidatos in grupos.items():
            variavel, linha, tipo = chave
            erro = erros.get(chave)
            ocorrencias = erro.quantidade if erro else (candidatos[0].ocorrencias_log if candidatos else 0)

            arquivo.write(SEPARADOR + "\n")
            arquivo.write(f'ERRO: {tipo}: "{variavel}" is not defined\n')
            arquivo.write(f"LINHA INFORMADA PELO LOG: {linha}\n")
            arquivo.write(f"OCORRÊNCIAS NO LOG: {ocorrencias}\n\n")
            arquivo.write("XIDs DOS DATAPOINTS COM POSSÍVEL PROBLEMA:\n\n")
            if candidatos:
                for indice, candidato in enumerate(candidatos, start=1):
                    arquivo.write(f"{indice}. {_xid(candidato)}\n")
            else:
                arquivo.write("NENHUM DATAPOINT COMPATÍVEL ENCONTRADO\n")
            arquivo.write(SEPARADOR + "\n\n")

            for candidato in candidatos:
                script = candidato.script
                arquivo.write(SUBSEPARADOR + "\n")
                arquivo.write(f"XID: {_xid(candidato)}\n")
                arquivo.write(f"NOME: {_valor(script.datapoint)}\n")
                arquivo.write(f"DATASOURCE: {_valor(script.datasource)}\n")
                arquivo.write(f"DEVICE: {_valor(script.device)}\n")
                arquivo.write(f"HABILITADO: {_valor(script.habilitado)}\n")
                arquivo.write(f"STATUS: {candidato.status}\n")
                arquivo.write(f"CONFIANÇA: {candidato.confianca}%\n\n")
                arquivo.write("CAMINHO DO DATAPOINT:\n")
                arquivo.write(f"{script.caminho_datapoint}\n\n")
                arquivo.write("CAMINHO DO SCRIPT:\n")
                arquivo.write(f"{script.caminho_script}\n\n")
                arquivo.write("LINHAS ONDE A VARIÁVEL APARECE:\n")
                arquivo.write(_linhas_uso(candidato) + "\n\n")
                arquivo.write("VARIÁVEIS DISPONÍVEIS NO CONTEXTO:\n")
                arquivo.write(_contexto(candidato) + "\n\n")
                arquivo.write("MOTIVO DO ERRO:\n")
                arquivo.write(_motivo_erro(candidato) + "\n\n")
                arquivo.write("CORREÇÃO PROVÁVEL:\n")
                arquivo.write(_correcao_provavel(candidato) + "\n\n")
                arquivo.write("SCRIPT COMPLETO NUMERADO:\n")
                arquivo.write(_script_numerado(script.script) + "\n")
                arquivo.write(SUBSEPARADOR + "\n\n")

            confirmados = sum(c.status == "CONFIRMADO" for c in candidatos)
            provaveis = sum(c.status == "PROVÁVEL" for c in candidatos)
            possiveis = sum(c.status == "POSSÍVEL" for c in candidatos)

            arquivo.write("RESUMO DO ERRO\n\n")
            arquivo.write(f"Variável: {variavel}\n")
            arquivo.write(f"Linha indicada: {linha}\n")
            arquivo.write(f"Tipo do erro: {tipo}\n")
            arquivo.write(f"Quantidade de ocorrências no log: {ocorrencias}\n")
            arquivo.write(f"Quantidade de datapoints encontrados: {len(candidatos)}\n")
            arquivo.write(f"Confirmados: {confirmados}\n")
            arquivo.write(f"Prováveis: {provaveis}\n")
            arquivo.write(f"Possíveis: {possiveis}\n\n")
            arquivo.write("XIDs encontrados:\n")
            if candidatos:
                for candidato in candidatos:
                    arquivo.write(f"- {_xid(candidato)}\n")
            else:
                arquivo.write("- NENHUM\n")
            arquivo.write("\n")

        arquivo.write(SEPARADOR + "\n")
        arquivo.write("RESUMO TÉCNICO GLOBAL\n")
        arquivo.write(SEPARADOR + "\n\n")
        arquivo.write(f"Total de linhas do log: {log.total_linhas}\n")
        arquivo.write(f"Total de ReferenceError: {log.total_reference_errors}\n")
        arquivo.write(f"Total de variáveis distintas: {len(log.variaveis_distintas)}\n")
        arquivo.write(f"Total de scripts encontrados: {len(resultado_json.scripts)}\n")
        arquivo.write(f"Total de Meta Data Points: {resultado_json.total_meta_data_points}\n")
        arquivo.write(f"Total de candidatos: {len(analise.candidatos)}\n")
        arquivo.write(f"Total CONFIRMADO: {analise.total_confirmado}\n")
        arquivo.write(f"Total PROVÁVEL: {analise.total_provavel}\n")
        arquivo.write(f"Total POSSÍVEL: {analise.total_possivel}\n")
