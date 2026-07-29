import copy
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Optional


# ============================================================
# CONFIGURAÇÕES
# ============================================================

NOME_DATASOURCE = "Dados Calculados"

PASTA_BASE = os.path.dirname(os.path.abspath(__file__))
PASTA_ENTRADA = os.path.join(PASTA_BASE, "entrada")
PASTA_SAIDA = os.path.join(PASTA_BASE, "saida")

ARQUIVO_ESPELHO = os.path.join(PASTA_ENTRADA, "espelho.json")
ARQUIVO_ANALISADO = os.path.join(PASTA_ENTRADA, "analisado.json")

ARQUIVO_RELATORIO = os.path.join(
    PASTA_SAIDA,
    "auditoria_dados_calculados.txt",
)

ARQUIVO_ANALISADO_CORRIGIDO = os.path.join(
    PASTA_SAIDA,
    "analisado_corrigido.json",
)

ARQUIVO_AJUSTES_APLICADOS = os.path.join(
    PASTA_SAIDA,
    "ajustes_aplicados.json",
)

CAMPOS_IGNORADOS_COMPARACAO = {
    "id",
    "dataSourceId",
    "dataSourceXid",
    "dataSourceName",
}

CAMPOS_PRESERVADOS_EXISTENTE = {
    "id",
    "dataSourceId",
    "dataSourceXid",
    "dataSourceName",
}

CAMPOS_IDENTIDADE_DATASOURCE = {
    "dataSourceId",
    "dataSourceXid",
    "dataSourceName",
}

CAMPOS_TOPOLOGICOS = {
    "script",
    "source",
    "formula",
}

PADRAO_INVERSOR = re.compile(
    r"(?i)(?<![A-Z0-9])"
    r"(Inv(?:ersor)?)([_\-\s]*)(\d+)\.(\d+)"
    r"(?!\d)"
)

PADRAO_SKID_EXPLICITO = re.compile(
    r"(?i)(?<![A-Z0-9])"
    r"(Skid)([_\-\s]*)(\d+)"
    r"(?!\d)"
)

# Exemplo:
# GRA_CAL_Energia Anual 1 (GWh)
PADRAO_NUMERO_CALCULADO = re.compile(
    r"(?i)(\bCAL[_\-\s].*?)(?<![\d.])(\d+)(?=\s*(?:\(|$))"
)


# ============================================================
# MODELOS
# ============================================================

@dataclass(frozen=True)
class Topologia:
    inversores_por_skid: tuple[int, ...]

    @property
    def quantidade_skids(self) -> int:
        return len(self.inversores_por_skid)

    @property
    def quantidade_inversores(self) -> int:
        return sum(self.inversores_por_skid)

    @property
    def posicoes_inversores(self) -> list[tuple[int, int]]:
        return [
            (skid, inversor)
            for skid, quantidade in enumerate(
                self.inversores_por_skid,
                start=1,
            )
            for inversor in range(1, quantidade + 1)
        ]

    @property
    def fisico_para_global_inversor(
        self,
    ) -> dict[tuple[int, int], int]:
        return {
            posicao: global_id
            for global_id, posicao in enumerate(
                self.posicoes_inversores,
                start=1,
            )
        }

    @property
    def global_para_fisico_inversor(
        self,
    ) -> dict[int, tuple[int, int]]:
        return {
            global_id: posicao
            for posicao, global_id
            in self.fisico_para_global_inversor.items()
        }

    @property
    def fisico_para_global_skid(self) -> dict[int, int]:
        return {
            skid: skid
            for skid in range(1, self.quantidade_skids + 1)
        }

    @property
    def global_para_fisico_skid(self) -> dict[int, int]:
        return {
            global_id: skid
            for skid, global_id
            in self.fisico_para_global_skid.items()
        }


@dataclass
class RegistroDatapoint:
    datapoint: dict
    parent_list: Optional[list]
    index: Optional[int]


@dataclass
class PontoLogico:
    datapoint: dict
    nivel: str
    familia: str
    chave_instancia: str
    skid_fisico: Optional[int] = None
    skid_global: Optional[int] = None
    inversor_fisico: Optional[tuple[int, int]] = None
    inversor_global: Optional[int] = None


@dataclass
class Correspondencia:
    espelho: PontoLogico
    analisado: PontoLogico
    origem_modelo: str


@dataclass
class Faltante:
    modelo_espelho: PontoLogico
    nivel: str
    familia: str
    skid_global_esperado: Optional[int] = None
    inversor_global_esperado: Optional[int] = None
    nome_esperado: str = ""
    xid_esperado: str = ""


@dataclass
class ResultadoComparacao:
    correspondencia: Correspondencia
    diferencas_funcionais: list[str]
    revisoes_topologicas: list[str]


# ============================================================
# ENTRADA DA TOPOLOGIA
# ============================================================

def ler_inteiro_positivo(mensagem: str) -> int:
    while True:
        valor = input(mensagem).strip()

        try:
            numero = int(valor)

            if numero <= 0:
                raise ValueError

            return numero

        except ValueError:
            print(
                "Valor inválido. Informe um número inteiro maior que zero."
            )


def perguntar_topologia(rotulo: str) -> Topologia:
    print("\n" + "=" * 76)
    print(f"TOPOLOGIA DO {rotulo.upper()}")
    print("=" * 76)

    quantidade_skids = ler_inteiro_positivo(
        f"Quantos skids existem no {rotulo}? "
    )

    quantidades = []

    for skid in range(1, quantidade_skids + 1):
        quantidade = ler_inteiro_positivo(
            f"Quantos inversores existem no skid {skid} "
            f"do {rotulo}? "
        )
        quantidades.append(quantidade)

    topologia = Topologia(tuple(quantidades))

    print(f"\nTopologia informada para o {rotulo}:")

    for skid, quantidade in enumerate(
        topologia.inversores_por_skid,
        start=1,
    ):
        print(
            f"  Skid global {skid}: "
            f"{quantidade} inversor(es)"
        )

    print(
        f"  Total: {topologia.quantidade_skids} skid(s) e "
        f"{topologia.quantidade_inversores} inversor(es)"
    )

    return topologia


# ============================================================
# JSON
# ============================================================

def converter_constante_especial(valor: str) -> float:
    if valor == "Infinity":
        return float("inf")

    if valor == "-Infinity":
        return float("-inf")

    if valor == "NaN":
        return float("nan")

    raise ValueError(f"Constante JSON desconhecida: {valor}")


def carregar_json(caminho: str) -> Any:
    if not os.path.isfile(caminho):
        raise FileNotFoundError(
            f"Arquivo não encontrado: {os.path.abspath(caminho)}"
        )

    with open(caminho, "r", encoding="utf-8-sig") as arquivo:
        return json.load(
            arquivo,
            parse_constant=converter_constante_especial,
        )


def normalizar_notacao_cientifica_json(texto: str) -> str:
    """
    Mantém a notação científica no padrão dos JSONs do ScadaBR/Scada-LTS.

    Exemplos:
        1.7976931348623157e+308  -> 1.7976931348623157E308
       -1.7976931348623157e+308  -> -1.7976931348623157E308
        1.0e-10                  -> 1.0E-10
    """

    padrao = re.compile(
        r'(?<!["A-Za-z0-9_])'
        r'(-?(?:\d+\.\d+|\d+))[eE]'
        r'([+-]?)'
        r'(\d+)'
        r'(?=\s*[,}\]])'
    )

    def substituir(resultado: re.Match) -> str:
        mantissa = resultado.group(1)
        sinal = resultado.group(2)
        expoente = resultado.group(3)

        if sinal == "+":
            sinal = ""

        return f"{mantissa}E{sinal}{expoente}"

    return padrao.sub(substituir, texto)


def salvar_json(caminho: str, estrutura: Any) -> None:
    texto_json = json.dumps(
        estrutura,
        ensure_ascii=False,
        indent=2,
        allow_nan=True,
    )

    texto_json = normalizar_notacao_cientifica_json(
        texto_json
    )

    with open(caminho, "w", encoding="utf-8") as arquivo:
        arquivo.write(texto_json)
        arquivo.write("\n")


# ============================================================
# EXTRAÇÃO DOS DATAPOINTS
# ============================================================

def parece_datapoint(objeto: dict) -> bool:
    possui_identificacao = (
        "xid" in objeto
        or "name" in objeto
    )

    possui_configuracao = any(
        chave in objeto
        for chave in (
            "pointLocator",
            "loggingType",
            "eventDetectors",
            "textRenderer",
            "purgeType",
            "chartRenderer",
        )
    )

    return possui_identificacao and possui_configuracao


def extrair_registros_datapoints(
    estrutura: Any,
    resultado: Optional[list[RegistroDatapoint]] = None,
    parent_list: Optional[list] = None,
    index: Optional[int] = None,
) -> list[RegistroDatapoint]:
    if resultado is None:
        resultado = []

    if isinstance(estrutura, dict):
        if parece_datapoint(estrutura):
            resultado.append(
                RegistroDatapoint(
                    datapoint=estrutura,
                    parent_list=parent_list,
                    index=index,
                )
            )
            return resultado

        for valor in estrutura.values():
            extrair_registros_datapoints(
                valor,
                resultado,
            )

    elif isinstance(estrutura, list):
        for indice, item in enumerate(estrutura):
            extrair_registros_datapoints(
                item,
                resultado,
                parent_list=estrutura,
                index=indice,
            )

    return resultado


# ============================================================
# FILTRO DO DATASOURCE
# ============================================================

def encontrar_textos_datasource(objeto: Any) -> list[str]:
    textos = []

    if isinstance(objeto, dict):
        for chave, valor in objeto.items():
            if chave in {
                "dataSourceName",
                "dataSource",
                "dataSourceXid",
                "sourceName",
            }:
                textos.append(str(valor))

            if isinstance(valor, (dict, list)):
                textos.extend(
                    encontrar_textos_datasource(valor)
                )

    elif isinstance(objeto, list):
        for item in objeto:
            textos.extend(
                encontrar_textos_datasource(item)
            )

    return textos


def pertence_ao_datasource(
    datapoint: dict,
    nome_datasource: str,
) -> bool:
    procurado = nome_datasource.strip().casefold()

    campos = (
        datapoint.get("dataSourceName"),
        datapoint.get("dataSource"),
        datapoint.get("sourceName"),
    )

    for valor in campos:
        if valor is not None:
            if procurado in str(valor).strip().casefold():
                return True

    return any(
        procurado in texto.strip().casefold()
        for texto in encontrar_textos_datasource(datapoint)
    )


def filtrar_registros_dados_calculados(
    registros: list[RegistroDatapoint],
    rotulo: str,
) -> list[RegistroDatapoint]:
    encontrados = [
        registro
        for registro in registros
        if pertence_ao_datasource(
            registro.datapoint,
            NOME_DATASOURCE,
        )
    ]

    if encontrados:
        return encontrados

    print(
        f"\nAviso ({rotulo}): não foi possível identificar "
        f"o datasource '{NOME_DATASOURCE}'."
    )
    print(
        "Todos os datapoints encontrados nesse arquivo "
        "serão considerados.\n"
    )

    return registros


# ============================================================
# IDENTIFICAÇÃO DOS NÍVEIS
# ============================================================

def texto_identificador(datapoint: dict) -> str:
    return (
        f"{datapoint.get('xid', '')}\n"
        f"{datapoint.get('name', '')}"
    )


def extrair_inversor_fisico(
    datapoint: dict,
) -> Optional[tuple[int, int]]:
    resultado = PADRAO_INVERSOR.search(
        texto_identificador(datapoint)
    )

    if resultado is None:
        return None

    return (
        int(resultado.group(3)),
        int(resultado.group(4)),
    )


def extrair_skid_fisico(
    datapoint: dict,
    topologia: Topologia,
) -> Optional[int]:
    texto = texto_identificador(datapoint)

    explicito = PADRAO_SKID_EXPLICITO.search(texto)

    if explicito is not None:
        numero = int(explicito.group(3))

        if 1 <= numero <= topologia.quantidade_skids:
            return numero

    for resultado in PADRAO_NUMERO_CALCULADO.finditer(texto):
        numero = int(resultado.group(2))

        if 1 <= numero <= topologia.quantidade_skids:
            return numero

    return None


def classificar_nivel(
    datapoint: dict,
    topologia: Topologia,
) -> tuple[
    str,
    Optional[tuple[int, int]],
    Optional[int],
]:
    inversor = extrair_inversor_fisico(datapoint)

    if inversor is not None:
        return "INVERSOR", inversor, inversor[0]

    skid = extrair_skid_fisico(
        datapoint,
        topologia,
    )

    if skid is not None:
        return "SKID", None, skid

    return "USINA", None, None


# ============================================================
# NORMALIZAÇÃO SEMÂNTICA
# ============================================================

def normalizar_prefixo(
    texto: str,
    prefixo: str,
) -> str:
    if not isinstance(texto, str):
        return texto

    prefixo = prefixo.strip()

    if not prefixo:
        return texto

    padrao = re.compile(
        rf"(?i)(?<![A-Z0-9])"
        rf"{re.escape(prefixo)}"
        rf"(?=[_\-\s.]|$)"
    )

    return padrao.sub("{PREFIXO}", texto)


def normalizar_referencias_inversores(
    texto: str,
    topologia: Topologia,
) -> str:
    if not isinstance(texto, str):
        return texto

    mapa = topologia.fisico_para_global_inversor

    def substituir(resultado: re.Match) -> str:
        fisico = (
            int(resultado.group(3)),
            int(resultado.group(4)),
        )

        global_id = mapa.get(fisico)

        if global_id is None:
            return resultado.group(0)

        return (
            f"{resultado.group(1)}"
            f"{resultado.group(2)}GLOBAL_{global_id}"
        )

    return PADRAO_INVERSOR.sub(
        substituir,
        texto,
    )


def normalizar_referencias_skids(
    texto: str,
    topologia: Topologia,
) -> str:
    if not isinstance(texto, str):
        return texto

    mapa = topologia.fisico_para_global_skid

    def substituir(resultado: re.Match) -> str:
        fisico = int(resultado.group(3))
        global_id = mapa.get(fisico)

        if global_id is None:
            return resultado.group(0)

        return (
            f"{resultado.group(1)}"
            f"{resultado.group(2)}GLOBAL_{global_id}"
        )

    return PADRAO_SKID_EXPLICITO.sub(
        substituir,
        texto,
    )


def normalizar_texto_completo(
    texto: str,
    prefixo: str,
    topologia: Topologia,
) -> str:
    texto = normalizar_prefixo(
        texto,
        prefixo,
    )

    texto = normalizar_referencias_inversores(
        texto,
        topologia,
    )

    texto = normalizar_referencias_skids(
        texto,
        topologia,
    )

    return texto


def substituir_instancia_por_placeholder(
    texto: str,
    nivel: str,
    skid_fisico: Optional[int],
) -> str:
    if nivel == "INVERSOR":
        texto = re.sub(
            r"(?i)(?<![A-Z0-9])"
            r"(Inv(?:ersor)?[_\-\s]*)"
            r"GLOBAL_\d+"
            r"(?!\d)",
            r"\1{INVERSOR_GLOBAL}",
            texto,
        )

    if nivel == "SKID":
        texto = re.sub(
            r"(?i)(?<![A-Z0-9])"
            r"(Skid[_\-\s]*)"
            r"GLOBAL_\d+"
            r"(?!\d)",
            r"\1{SKID_GLOBAL}",
            texto,
        )

        if skid_fisico is not None:
            texto = PADRAO_NUMERO_CALCULADO.sub(
                lambda resultado: (
                    f"{resultado.group(1)}{{SKID_GLOBAL}}"
                    if int(resultado.group(2)) == skid_fisico
                    else resultado.group(0)
                ),
                texto,
            )

    return texto


def obter_identificador_base(datapoint: dict) -> str:
    xid = datapoint.get("xid")

    if xid:
        return str(xid)

    return str(datapoint.get("name", ""))


def criar_ponto_logico(
    datapoint: dict,
    prefixo: str,
    topologia: Topologia,
) -> PontoLogico:
    (
        nivel,
        inversor_fisico,
        skid_fisico,
    ) = classificar_nivel(
        datapoint,
        topologia,
    )

    skid_global = None
    inversor_global = None

    if skid_fisico is not None:
        skid_global = (
            topologia
            .fisico_para_global_skid
            .get(skid_fisico)
        )

    if inversor_fisico is not None:
        inversor_global = (
            topologia
            .fisico_para_global_inversor
            .get(inversor_fisico)
        )

        if inversor_global is None:
            raise ValueError(
                "O datapoint referencia o inversor "
                f"{inversor_fisico[0]}.{inversor_fisico[1]}, "
                "mas essa posição não existe na topologia informada: "
                f"{obter_identificador_base(datapoint)}"
            )

    identificador = normalizar_texto_completo(
        obter_identificador_base(datapoint),
        prefixo,
        topologia,
    )

    familia_base = substituir_instancia_por_placeholder(
        identificador,
        nivel,
        skid_fisico,
    )

    familia = f"{nivel}:{familia_base}"

    if nivel == "INVERSOR":
        chave = (
            f"{familia}:GLOBAL_{inversor_global}"
        )

    elif nivel == "SKID":
        chave = (
            f"{familia}:GLOBAL_{skid_global}"
        )

    else:
        chave = familia

    return PontoLogico(
        datapoint=datapoint,
        nivel=nivel,
        familia=familia,
        chave_instancia=chave,
        skid_fisico=skid_fisico,
        skid_global=skid_global,
        inversor_fisico=inversor_fisico,
        inversor_global=inversor_global,
    )


def indexar_pontos(
    datapoints: list[dict],
    prefixo: str,
    topologia: Topologia,
) -> tuple[
    dict[str, PontoLogico],
    dict[str, list[PontoLogico]],
    list[str],
]:
    por_instancia = {}
    por_familia: dict[str, list[PontoLogico]] = defaultdict(list)
    duplicados = []

    for datapoint in datapoints:
        ponto = criar_ponto_logico(
            datapoint,
            prefixo,
            topologia,
        )

        if ponto.chave_instancia in por_instancia:
            duplicados.append(
                ponto.chave_instancia
            )
            continue

        por_instancia[ponto.chave_instancia] = ponto
        por_familia[ponto.familia].append(ponto)

    return por_instancia, por_familia, duplicados


# ============================================================
# TRADUÇÃO ESPELHO -> ANALISADO
# ============================================================

def trocar_prefixo(
    texto: str,
    prefixo_origem: str,
    prefixo_destino: str,
) -> str:
    if not isinstance(texto, str) or not texto:
        return texto

    padrao = re.compile(
        rf"(?i)(?<![A-Z0-9])"
        rf"{re.escape(prefixo_origem)}"
        rf"(?=[_\-\s.]|$)"
    )

    return padrao.sub(
        prefixo_destino,
        texto,
    )


def traduzir_referencias_inversores(
    texto: str,
    topologia_espelho: Topologia,
    topologia_analisado: Topologia,
    modelo: PontoLogico,
    inversor_global_destino: Optional[int],
) -> str:
    mapa_origem = (
        topologia_espelho
        .fisico_para_global_inversor
    )

    mapa_destino = (
        topologia_analisado
        .global_para_fisico_inversor
    )

    def substituir(resultado: re.Match) -> str:
        fisico_origem = (
            int(resultado.group(3)),
            int(resultado.group(4)),
        )

        global_id = mapa_origem.get(
            fisico_origem
        )

        if (
            modelo.nivel == "INVERSOR"
            and modelo.inversor_fisico == fisico_origem
            and inversor_global_destino is not None
        ):
            global_id = inversor_global_destino

        if global_id is None:
            return resultado.group(0)

        fisico_destino = mapa_destino.get(
            global_id
        )

        if fisico_destino is None:
            return resultado.group(0)

        return (
            f"{resultado.group(1)}"
            f"{resultado.group(2)}"
            f"{fisico_destino[0]}.{fisico_destino[1]}"
        )

    return PADRAO_INVERSOR.sub(
        substituir,
        texto,
    )


def traduzir_referencias_skids(
    texto: str,
    topologia_espelho: Topologia,
    topologia_analisado: Topologia,
    modelo: PontoLogico,
    skid_global_destino: Optional[int],
) -> str:
    mapa_origem = (
        topologia_espelho
        .fisico_para_global_skid
    )

    mapa_destino = (
        topologia_analisado
        .global_para_fisico_skid
    )

    def substituir(resultado: re.Match) -> str:
        skid_origem = int(resultado.group(3))
        global_id = mapa_origem.get(
            skid_origem
        )

        if (
            modelo.nivel == "SKID"
            and modelo.skid_fisico == skid_origem
            and skid_global_destino is not None
        ):
            global_id = skid_global_destino

        if global_id is None:
            return resultado.group(0)

        skid_destino = mapa_destino.get(
            global_id
        )

        if skid_destino is None:
            return resultado.group(0)

        return (
            f"{resultado.group(1)}"
            f"{resultado.group(2)}"
            f"{skid_destino}"
        )

    texto = PADRAO_SKID_EXPLICITO.sub(
        substituir,
        texto,
    )

    if (
        modelo.nivel == "SKID"
        and modelo.skid_fisico is not None
        and skid_global_destino is not None
    ):
        skid_destino = mapa_destino.get(
            skid_global_destino
        )

        if skid_destino is not None:
            texto = PADRAO_NUMERO_CALCULADO.sub(
                lambda resultado: (
                    f"{resultado.group(1)}{skid_destino}"
                    if int(resultado.group(2)) == modelo.skid_fisico
                    else resultado.group(0)
                ),
                texto,
            )

    return texto


def traduzir_texto_espelho_para_analisado(
    texto: str,
    prefixo_espelho: str,
    prefixo_analisado: str,
    topologia_espelho: Topologia,
    topologia_analisado: Topologia,
    modelo: PontoLogico,
    skid_global_destino: Optional[int] = None,
    inversor_global_destino: Optional[int] = None,
) -> str:
    texto = trocar_prefixo(
        texto,
        prefixo_espelho,
        prefixo_analisado,
    )

    texto = traduzir_referencias_inversores(
        texto,
        topologia_espelho,
        topologia_analisado,
        modelo,
        inversor_global_destino,
    )

    texto = traduzir_referencias_skids(
        texto,
        topologia_espelho,
        topologia_analisado,
        modelo,
        skid_global_destino,
    )

    return texto


def traduzir_objeto_espelho_para_analisado(
    objeto: Any,
    prefixo_espelho: str,
    prefixo_analisado: str,
    topologia_espelho: Topologia,
    topologia_analisado: Topologia,
    modelo: PontoLogico,
    skid_global_destino: Optional[int] = None,
    inversor_global_destino: Optional[int] = None,
) -> Any:
    if isinstance(objeto, dict):
        convertido = {}

        for chave, valor in objeto.items():
            nova_chave = traduzir_texto_espelho_para_analisado(
                chave,
                prefixo_espelho,
                prefixo_analisado,
                topologia_espelho,
                topologia_analisado,
                modelo,
                skid_global_destino,
                inversor_global_destino,
            )

            convertido[nova_chave] = (
                traduzir_objeto_espelho_para_analisado(
                    valor,
                    prefixo_espelho,
                    prefixo_analisado,
                    topologia_espelho,
                    topologia_analisado,
                    modelo,
                    skid_global_destino,
                    inversor_global_destino,
                )
            )

        return convertido

    if isinstance(objeto, list):
        return [
            traduzir_objeto_espelho_para_analisado(
                item,
                prefixo_espelho,
                prefixo_analisado,
                topologia_espelho,
                topologia_analisado,
                modelo,
                skid_global_destino,
                inversor_global_destino,
            )
            for item in objeto
        ]

    if isinstance(objeto, str):
        return traduzir_texto_espelho_para_analisado(
            objeto,
            prefixo_espelho,
            prefixo_analisado,
            topologia_espelho,
            topologia_analisado,
            modelo,
            skid_global_destino,
            inversor_global_destino,
        )

    return copy.deepcopy(objeto)


def gerar_datapoint_ajustado(
    modelo: PontoLogico,
    prefixo_espelho: str,
    prefixo_analisado: str,
    topologia_espelho: Topologia,
    topologia_analisado: Topologia,
    skid_global_destino: Optional[int] = None,
    inversor_global_destino: Optional[int] = None,
) -> dict:
    return traduzir_objeto_espelho_para_analisado(
        modelo.datapoint,
        prefixo_espelho,
        prefixo_analisado,
        topologia_espelho,
        topologia_analisado,
        modelo,
        skid_global_destino,
        inversor_global_destino,
    )


def gerar_nome_esperado(
    modelo: PontoLogico,
    prefixo_espelho: str,
    prefixo_analisado: str,
    topologia_espelho: Topologia,
    topologia_analisado: Topologia,
    skid_global_esperado: Optional[int] = None,
    inversor_global_esperado: Optional[int] = None,
) -> tuple[str, str]:
    convertido = gerar_datapoint_ajustado(
        modelo,
        prefixo_espelho,
        prefixo_analisado,
        topologia_espelho,
        topologia_analisado,
        skid_global_esperado,
        inversor_global_esperado,
    )

    return (
        str(convertido.get("name", "")),
        str(convertido.get("xid", "")),
    )


# ============================================================
# CORRESPONDÊNCIAS
# ============================================================

def selecionar_modelo(
    modelos: list[PontoLogico],
    nivel: str,
    global_esperado: Optional[int],
) -> PontoLogico:
    if nivel == "INVERSOR":
        for modelo in modelos:
            if modelo.inversor_global == global_esperado:
                return modelo

    if nivel == "SKID":
        for modelo in modelos:
            if modelo.skid_global == global_esperado:
                return modelo

    return sorted(
        modelos,
        key=lambda ponto: (
            ponto.skid_global or 0,
            ponto.inversor_global or 0,
        ),
    )[0]


def construir_auditoria(
    familias_espelho: dict[str, list[PontoLogico]],
    familias_analisado: dict[str, list[PontoLogico]],
    prefixo_espelho: str,
    prefixo_analisado: str,
    topologia_espelho: Topologia,
    topologia_analisado: Topologia,
) -> tuple[
    list[Correspondencia],
    list[Faltante],
    list[PontoLogico],
]:
    correspondencias = []
    faltantes = []
    usados_analisado = set()

    for familia, modelos in familias_espelho.items():
        nivel = modelos[0].nivel
        analisados = familias_analisado.get(
            familia,
            [],
        )

        if nivel == "INVERSOR":
            mapa_analisado = {
                ponto.inversor_global: ponto
                for ponto in analisados
            }

            for global_id in range(
                1,
                topologia_analisado.quantidade_inversores + 1,
            ):
                modelo = selecionar_modelo(
                    modelos,
                    nivel,
                    global_id,
                )

                encontrado = mapa_analisado.get(
                    global_id
                )

                if encontrado is not None:
                    correspondencias.append(
                        Correspondencia(
                            espelho=modelo,
                            analisado=encontrado,
                            origem_modelo=(
                                "mesmo inversor global"
                                if modelo.inversor_global == global_id
                                else "modelo da família"
                            ),
                        )
                    )

                    usados_analisado.add(
                        encontrado.chave_instancia
                    )

                else:
                    nome, xid = gerar_nome_esperado(
                        modelo,
                        prefixo_espelho,
                        prefixo_analisado,
                        topologia_espelho,
                        topologia_analisado,
                        inversor_global_esperado=global_id,
                    )

                    faltantes.append(
                        Faltante(
                            modelo_espelho=modelo,
                            nivel=nivel,
                            familia=familia,
                            inversor_global_esperado=global_id,
                            nome_esperado=nome,
                            xid_esperado=xid,
                        )
                    )

        elif nivel == "SKID":
            mapa_analisado = {
                ponto.skid_global: ponto
                for ponto in analisados
            }

            for global_id in range(
                1,
                topologia_analisado.quantidade_skids + 1,
            ):
                modelo = selecionar_modelo(
                    modelos,
                    nivel,
                    global_id,
                )

                encontrado = mapa_analisado.get(
                    global_id
                )

                if encontrado is not None:
                    correspondencias.append(
                        Correspondencia(
                            espelho=modelo,
                            analisado=encontrado,
                            origem_modelo=(
                                "mesmo skid global"
                                if modelo.skid_global == global_id
                                else "modelo da família de skid"
                            ),
                        )
                    )

                    usados_analisado.add(
                        encontrado.chave_instancia
                    )

                else:
                    nome, xid = gerar_nome_esperado(
                        modelo,
                        prefixo_espelho,
                        prefixo_analisado,
                        topologia_espelho,
                        topologia_analisado,
                        skid_global_esperado=global_id,
                    )

                    faltantes.append(
                        Faltante(
                            modelo_espelho=modelo,
                            nivel=nivel,
                            familia=familia,
                            skid_global_esperado=global_id,
                            nome_esperado=nome,
                            xid_esperado=xid,
                        )
                    )

        else:
            modelo = modelos[0]
            encontrado = (
                analisados[0]
                if analisados
                else None
            )

            if encontrado is not None:
                correspondencias.append(
                    Correspondencia(
                        espelho=modelo,
                        analisado=encontrado,
                        origem_modelo="ponto global da usina",
                    )
                )

                usados_analisado.add(
                    encontrado.chave_instancia
                )

            else:
                nome, xid = gerar_nome_esperado(
                    modelo,
                    prefixo_espelho,
                    prefixo_analisado,
                    topologia_espelho,
                    topologia_analisado,
                )

                faltantes.append(
                    Faltante(
                        modelo_espelho=modelo,
                        nivel=nivel,
                        familia=familia,
                        nome_esperado=nome,
                        xid_esperado=xid,
                    )
                )

    extras = [
        ponto
        for pontos in familias_analisado.values()
        for ponto in pontos
        if ponto.chave_instancia not in usados_analisado
    ]

    return (
        correspondencias,
        faltantes,
        extras,
    )


# ============================================================
# COMPARAÇÃO
# ============================================================

def normalizar_objeto_comparacao(
    objeto: Any,
    prefixo: str,
    topologia: Topologia,
    remover_topologicos: bool,
) -> Any:
    if isinstance(objeto, dict):
        normalizado = {}

        for chave, valor in objeto.items():
            if chave in CAMPOS_IGNORADOS_COMPARACAO:
                continue

            if (
                remover_topologicos
                and chave.casefold() in CAMPOS_TOPOLOGICOS
            ):
                continue

            chave_normalizada = normalizar_texto_completo(
                chave,
                prefixo,
                topologia,
            )

            normalizado[chave_normalizada] = (
                normalizar_objeto_comparacao(
                    valor,
                    prefixo,
                    topologia,
                    remover_topologicos,
                )
            )

        return normalizado

    if isinstance(objeto, list):
        return [
            normalizar_objeto_comparacao(
                item,
                prefixo,
                topologia,
                remover_topologicos,
            )
            for item in objeto
        ]

    if isinstance(objeto, str):
        return normalizar_texto_completo(
            objeto,
            prefixo,
            topologia,
        )

    return objeto


def extrair_campos_topologicos(
    objeto: Any,
    caminho: str = "",
) -> list[tuple[str, Any]]:
    encontrados = []

    if isinstance(objeto, dict):
        for chave, valor in objeto.items():
            local = (
                f"{caminho}.{chave}"
                if caminho
                else chave
            )

            if chave.casefold() in CAMPOS_TOPOLOGICOS:
                encontrados.append(
                    (local, valor)
                )

            encontrados.extend(
                extrair_campos_topologicos(
                    valor,
                    local,
                )
            )

    elif isinstance(objeto, list):
        for indice, item in enumerate(objeto):
            encontrados.extend(
                extrair_campos_topologicos(
                    item,
                    f"{caminho}[{indice}]",
                )
            )

    return encontrados


def formatar_valor(valor: Any) -> str:
    if isinstance(valor, float):
        if math.isinf(valor):
            return (
                "Infinity"
                if valor > 0
                else "-Infinity"
            )

        if math.isnan(valor):
            return "NaN"

    if isinstance(valor, (dict, list)):
        return json.dumps(
            valor,
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )

    return repr(valor)


def comparar_objetos(
    espelho: Any,
    analisado: Any,
    caminho: str = "",
) -> list[str]:
    diferencas = []

    if type(espelho) is not type(analisado):
        diferencas.append(
            f"{caminho}: tipo diferente — "
            f"espelho={type(espelho).__name__}, "
            f"analisado={type(analisado).__name__}"
        )
        return diferencas

    if isinstance(espelho, dict):
        chaves_espelho = set(espelho)
        chaves_analisado = set(analisado)

        for chave in sorted(
            chaves_espelho - chaves_analisado
        ):
            local = (
                f"{caminho}.{chave}"
                if caminho
                else chave
            )

            diferencas.append(
                f"{local}: atributo ausente no analisado — "
                f"esperado={formatar_valor(espelho[chave])}"
            )

        for chave in sorted(
            chaves_analisado - chaves_espelho
        ):
            local = (
                f"{caminho}.{chave}"
                if caminho
                else chave
            )

            diferencas.append(
                f"{local}: atributo existe somente no analisado — "
                f"valor={formatar_valor(analisado[chave])}"
            )

        for chave in sorted(
            chaves_espelho & chaves_analisado
        ):
            local = (
                f"{caminho}.{chave}"
                if caminho
                else chave
            )

            diferencas.extend(
                comparar_objetos(
                    espelho[chave],
                    analisado[chave],
                    local,
                )
            )

        return diferencas

    if isinstance(espelho, list):
        if len(espelho) != len(analisado):
            diferencas.append(
                f"{caminho}: quantidade de itens diferente — "
                f"espelho={len(espelho)}, "
                f"analisado={len(analisado)}"
            )

        for indice in range(
            min(len(espelho), len(analisado))
        ):
            diferencas.extend(
                comparar_objetos(
                    espelho[indice],
                    analisado[indice],
                    f"{caminho}[{indice}]",
                )
            )

        return diferencas

    if isinstance(espelho, float):
        if math.isnan(espelho) and math.isnan(analisado):
            return diferencas

    if espelho != analisado:
        diferencas.append(
            f"{caminho}: valor diferente\n"
            f"         Espelho:   {formatar_valor(espelho)}\n"
            f"         Analisado: {formatar_valor(analisado)}"
        )

    return diferencas


def topologias_identicas(
    espelho: Topologia,
    analisado: Topologia,
) -> bool:
    return (
        espelho.inversores_por_skid
        == analisado.inversores_por_skid
    )


def comparar_correspondencia(
    correspondencia: Correspondencia,
    prefixo_espelho: str,
    prefixo_analisado: str,
    topologia_espelho: Topologia,
    topologia_analisado: Topologia,
) -> ResultadoComparacao:
    nivel = correspondencia.analisado.nivel

    ignorar_scripts = (
        not topologias_identicas(
            topologia_espelho,
            topologia_analisado,
        )
        and nivel in {"SKID", "USINA"}
    )

    espelho_normalizado = normalizar_objeto_comparacao(
        correspondencia.espelho.datapoint,
        prefixo_espelho,
        topologia_espelho,
        ignorar_scripts,
    )

    analisado_normalizado = normalizar_objeto_comparacao(
        correspondencia.analisado.datapoint,
        prefixo_analisado,
        topologia_analisado,
        ignorar_scripts,
    )

    diferencas_funcionais = comparar_objetos(
        espelho_normalizado,
        analisado_normalizado,
    )

    revisoes_topologicas = []

    if ignorar_scripts:
        campos_espelho = extrair_campos_topologicos(
            correspondencia.espelho.datapoint
        )

        campos_analisado = extrair_campos_topologicos(
            correspondencia.analisado.datapoint
        )

        campos_espelho_traduzidos = (
            traduzir_objeto_espelho_para_analisado(
                campos_espelho,
                prefixo_espelho,
                prefixo_analisado,
                topologia_espelho,
                topologia_analisado,
                correspondencia.espelho,
                correspondencia.analisado.skid_global,
                correspondencia.analisado.inversor_global,
            )
        )

        if campos_espelho_traduzidos != campos_analisado:
            revisoes_topologicas.append(
                "Script/fórmula do espelho, após tradução para a "
                "topologia analisada, difere do projeto analisado."
            )

    return ResultadoComparacao(
        correspondencia=correspondencia,
        diferencas_funcionais=diferencas_funcionais,
        revisoes_topologicas=revisoes_topologicas,
    )


# ============================================================
# APLICAÇÃO AUTOMÁTICA DOS AJUSTES
# ============================================================

def remover_ids_recursivamente(objeto: Any) -> Any:
    if isinstance(objeto, dict):
        return {
            chave: remover_ids_recursivamente(valor)
            for chave, valor in objeto.items()
            if chave != "id"
        }

    if isinstance(objeto, list):
        return [
            remover_ids_recursivamente(item)
            for item in objeto
        ]

    return objeto


def identidade_datasource_modelo(
    registros_analisados: list[RegistroDatapoint],
) -> dict[str, Any]:
    for registro in registros_analisados:
        datapoint = registro.datapoint
        identidade = {
            campo: copy.deepcopy(datapoint[campo])
            for campo in CAMPOS_IDENTIDADE_DATASOURCE
            if campo in datapoint
        }

        if identidade:
            return identidade

    return {}


def aplicar_identidade_datasource(
    datapoint: dict,
    identidade: dict[str, Any],
) -> None:
    for campo, valor in identidade.items():
        datapoint[campo] = copy.deepcopy(valor)


def preservar_identidade_existente(
    novo: dict,
    existente: dict,
) -> dict:
    for campo in CAMPOS_PRESERVADOS_EXISTENTE:
        if campo in existente:
            novo[campo] = copy.deepcopy(
                existente[campo]
            )

    return novo


def localizar_container_principal(
    registros_analisados: list[RegistroDatapoint],
) -> list:
    containers = [
        registro.parent_list
        for registro in registros_analisados
        if registro.parent_list is not None
    ]

    if not containers:
        raise ValueError(
            "Não foi possível localizar a lista que contém "
            "os datapoints no JSON analisado."
        )

    contagem = Counter(
        id(container)
        for container in containers
    )

    id_principal = contagem.most_common(1)[0][0]

    for container in containers:
        if id(container) == id_principal:
            return container

    raise ValueError(
        "Não foi possível determinar o container principal "
        "dos datapoints analisados."
    )


def aplicar_ajustes_no_json(
    json_analisado: Any,
    registros_analisados: list[RegistroDatapoint],
    correspondencias_avaliadas: list[ResultadoComparacao],
    faltantes: list[Faltante],
    prefixo_espelho: str,
    prefixo_analisado: str,
    topologia_espelho: Topologia,
    topologia_analisado: Topologia,
) -> dict[str, Any]:
    registro_por_objeto = {
        id(registro.datapoint): registro
        for registro in registros_analisados
    }

    identidade_datasource = identidade_datasource_modelo(
        registros_analisados
    )

    container_principal = localizar_container_principal(
        registros_analisados
    )

    substituidos_funcionais = []
    substituidos_topologicos = []
    adicionados = []
    avisos = []

    # Ajusta pontos existentes que aparecem nas seções:
    # 3. Diferenças funcionais
    # 4. Revisões topológicas de script/fórmula
    for resultado in correspondencias_avaliadas:
        precisa_funcional = bool(
            resultado.diferencas_funcionais
        )

        precisa_topologico = bool(
            resultado.revisoes_topologicas
        )

        if not (
            precisa_funcional
            or precisa_topologico
        ):
            continue

        correspondencia = resultado.correspondencia
        analisado = correspondencia.analisado
        modelo = correspondencia.espelho

        novo_datapoint = gerar_datapoint_ajustado(
            modelo,
            prefixo_espelho,
            prefixo_analisado,
            topologia_espelho,
            topologia_analisado,
            skid_global_destino=analisado.skid_global,
            inversor_global_destino=analisado.inversor_global,
        )

        novo_datapoint = preservar_identidade_existente(
            novo_datapoint,
            analisado.datapoint,
        )

        registro = registro_por_objeto.get(
            id(analisado.datapoint)
        )

        if (
            registro is None
            or registro.parent_list is None
            or registro.index is None
        ):
            avisos.append(
                "Não foi possível substituir automaticamente: "
                + nome_exibicao(analisado.datapoint)
            )
            continue

        registro.parent_list[registro.index] = novo_datapoint

        item_manifesto = {
            "nivel": analisado.nivel,
            "familia": analisado.familia,
            "antes": {
                "name": analisado.datapoint.get("name"),
                "xid": analisado.datapoint.get("xid"),
            },
            "depois": {
                "name": novo_datapoint.get("name"),
                "xid": novo_datapoint.get("xid"),
            },
            "modelo_espelho": {
                "name": modelo.datapoint.get("name"),
                "xid": modelo.datapoint.get("xid"),
            },
        }

        if precisa_funcional:
            item_manifesto["diferencas"] = (
                resultado.diferencas_funcionais
            )
            substituidos_funcionais.append(
                item_manifesto
            )

        if precisa_topologico:
            item_topologico = copy.deepcopy(
                item_manifesto
            )
            item_topologico["revisoes"] = (
                resultado.revisoes_topologicas
            )
            substituidos_topologicos.append(
                item_topologico
            )

    # Adiciona pontos faltantes da seção 1.
    for faltante in faltantes:
        novo_datapoint = gerar_datapoint_ajustado(
            faltante.modelo_espelho,
            prefixo_espelho,
            prefixo_analisado,
            topologia_espelho,
            topologia_analisado,
            skid_global_destino=faltante.skid_global_esperado,
            inversor_global_destino=faltante.inversor_global_esperado,
        )

        novo_datapoint = remover_ids_recursivamente(
            novo_datapoint
        )

        aplicar_identidade_datasource(
            novo_datapoint,
            identidade_datasource,
        )

        container_principal.append(
            novo_datapoint
        )

        adicionados.append(
            {
                "nivel": faltante.nivel,
                "familia": faltante.familia,
                "destino": descrever_destino_faltante(
                    faltante,
                    topologia_analisado,
                ),
                "name": novo_datapoint.get("name"),
                "xid": novo_datapoint.get("xid"),
                "modelo_espelho": {
                    "name": (
                        faltante
                        .modelo_espelho
                        .datapoint
                        .get("name")
                    ),
                    "xid": (
                        faltante
                        .modelo_espelho
                        .datapoint
                        .get("xid")
                    ),
                },
            }
        )

    return {
        "arquivo_gerado": ARQUIVO_ANALISADO_CORRIGIDO,
        "total_adicionados": len(adicionados),
        "total_substituidos_funcionais": len(
            substituidos_funcionais
        ),
        "total_substituidos_topologicos": len(
            substituidos_topologicos
        ),
        "adicionados": adicionados,
        "substituidos_funcionais": substituidos_funcionais,
        "substituidos_topologicos": substituidos_topologicos,
        "avisos": avisos,
    }


# ============================================================
# RELATÓRIO
# ============================================================

def nome_exibicao(datapoint: dict) -> str:
    nome = datapoint.get("name")
    xid = datapoint.get("xid")

    if nome and xid:
        return f"{nome} [{xid}]"

    if nome:
        return str(nome)

    if xid:
        return str(xid)

    return "Datapoint sem identificação"


def descrever_destino_faltante(
    faltante: Faltante,
    topologia_analisado: Topologia,
) -> str:
    if faltante.nivel == "INVERSOR":
        fisico = (
            topologia_analisado
            .global_para_fisico_inversor
            .get(faltante.inversor_global_esperado)
        )

        if fisico is not None:
            return (
                f"Inversor global "
                f"{faltante.inversor_global_esperado} "
                f"(Inv_{fisico[0]}.{fisico[1]})"
            )

    if faltante.nivel == "SKID":
        fisico = (
            topologia_analisado
            .global_para_fisico_skid
            .get(faltante.skid_global_esperado)
        )

        if fisico is not None:
            return (
                f"Skid global "
                f"{faltante.skid_global_esperado} "
                f"(Skid {fisico})"
            )

    return "Usina total"


def escrever_topologia(
    relatorio,
    rotulo: str,
    topologia: Topologia,
) -> None:
    relatorio.write(
        f"{rotulo}: "
        f"{topologia.quantidade_skids} skid(s), "
        f"{topologia.quantidade_inversores} inversor(es)\n"
    )

    for skid, quantidade in enumerate(
        topologia.inversores_por_skid,
        start=1,
    ):
        relatorio.write(
            f"  Skid global {skid}: "
            f"{quantidade} inversor(es)\n"
        )

    relatorio.write(
        "  Mapeamento global dos inversores:\n"
    )

    for global_id, fisico in (
        topologia
        .global_para_fisico_inversor
        .items()
    ):
        relatorio.write(
            f"    Global {global_id} -> "
            f"Inv_{fisico[0]}.{fisico[1]}\n"
        )


def gerar_relatorio(
    indice_espelho: dict[str, PontoLogico],
    indice_analisado: dict[str, PontoLogico],
    duplicados_espelho: list[str],
    duplicados_analisado: list[str],
    correspondencias_avaliadas: list[ResultadoComparacao],
    faltantes: list[Faltante],
    extras: list[PontoLogico],
    prefixo_espelho: str,
    prefixo_analisado: str,
    topologia_espelho: Topologia,
    topologia_analisado: Topologia,
    manifesto: dict[str, Any],
) -> None:
    iguais = [
        resultado
        for resultado in correspondencias_avaliadas
        if not resultado.diferencas_funcionais
        and not resultado.revisoes_topologicas
    ]

    diferentes = [
        resultado
        for resultado in correspondencias_avaliadas
        if resultado.diferencas_funcionais
    ]

    revisoes_topologicas = [
        resultado
        for resultado in correspondencias_avaliadas
        if resultado.revisoes_topologicas
    ]

    with open(
        ARQUIVO_RELATORIO,
        "w",
        encoding="utf-8",
    ) as relatorio:
        relatorio.write("=" * 100 + "\n")
        relatorio.write(
            "AUDITORIA SEMÂNTICA DO DATASOURCE DADOS CALCULADOS\n"
        )
        relatorio.write("=" * 100 + "\n\n")

        relatorio.write(
            f"Arquivo espelho:   {ARQUIVO_ESPELHO}\n"
        )
        relatorio.write(
            f"Arquivo analisado: {ARQUIVO_ANALISADO}\n"
        )
        relatorio.write(
            f"JSON corrigido:    {ARQUIVO_ANALISADO_CORRIGIDO}\n"
        )
        relatorio.write(
            f"Manifesto:         {ARQUIVO_AJUSTES_APLICADOS}\n"
        )
        relatorio.write(
            f"Prefixo espelho:   {prefixo_espelho}\n"
        )
        relatorio.write(
            f"Prefixo analisado: {prefixo_analisado}\n\n"
        )

        relatorio.write("TOPOLOGIAS INFORMADAS\n")
        relatorio.write("-" * 100 + "\n")

        escrever_topologia(
            relatorio,
            "Espelho",
            topologia_espelho,
        )

        relatorio.write("\n")

        escrever_topologia(
            relatorio,
            "Analisado",
            topologia_analisado,
        )

        relatorio.write("\nRESUMO\n")
        relatorio.write("-" * 100 + "\n")
        relatorio.write(
            f"Datapoints no espelho:                "
            f"{len(indice_espelho)}\n"
        )
        relatorio.write(
            f"Datapoints no analisado:              "
            f"{len(indice_analisado)}\n"
        )
        relatorio.write(
            f"Correspondências iguais:              "
            f"{len(iguais)}\n"
        )
        relatorio.write(
            f"Correspondências com diferenças:      "
            f"{len(diferentes)}\n"
        )
        relatorio.write(
            f"Datapoints faltantes adicionados:     "
            f"{len(faltantes)}\n"
        )
        relatorio.write(
            f"Datapoints extras mantidos:           "
            f"{len(extras)}\n"
        )
        relatorio.write(
            f"Revisões topológicas aplicadas:       "
            f"{len(revisoes_topologicas)}\n"
        )
        relatorio.write(
            f"Duplicados no espelho:                "
            f"{len(duplicados_espelho)}\n"
        )
        relatorio.write(
            f"Duplicados no analisado:              "
            f"{len(duplicados_analisado)}\n"
        )
        relatorio.write(
            f"Avisos na geração automática:         "
            f"{len(manifesto.get('avisos', []))}\n"
        )

        relatorio.write("\n" + "=" * 100 + "\n")
        relatorio.write(
            "1. DATAPOINTS FALTANTES ADICIONADOS AO JSON CORRIGIDO\n"
        )
        relatorio.write("=" * 100 + "\n\n")

        if not faltantes:
            relatorio.write(
                "Nenhum datapoint faltante.\n"
            )
        else:
            for numero, faltante in enumerate(
                faltantes,
                start=1,
            ):
                relatorio.write(
                    f"{numero}. [{faltante.nivel}] "
                    f"{descrever_destino_faltante(faltante, topologia_analisado)}\n"
                )
                relatorio.write(
                    f"   Modelo no espelho: "
                    f"{nome_exibicao(faltante.modelo_espelho.datapoint)}\n"
                )
                relatorio.write(
                    f"   Nome criado: {faltante.nome_esperado}\n"
                )
                relatorio.write(
                    f"   XID criado:  {faltante.xid_esperado}\n"
                )
                relatorio.write(
                    f"   Família lógica: {faltante.familia}\n\n"
                )

        relatorio.write("\n" + "=" * 100 + "\n")
        relatorio.write(
            "2. DATAPOINTS EXTRAS MANTIDOS NO JSON\n"
        )
        relatorio.write("=" * 100 + "\n\n")

        if not extras:
            relatorio.write(
                "Nenhum datapoint extra.\n"
            )
        else:
            for numero, ponto in enumerate(
                extras,
                start=1,
            ):
                relatorio.write(
                    f"{numero}. [{ponto.nivel}] "
                    f"{nome_exibicao(ponto.datapoint)}\n"
                )
                relatorio.write(
                    f"   Família lógica: {ponto.familia}\n\n"
                )

        relatorio.write("\n" + "=" * 100 + "\n")
        relatorio.write(
            "3. DIFERENÇAS FUNCIONAIS CORRIGIDAS NO JSON\n"
        )
        relatorio.write("=" * 100 + "\n\n")

        if not diferentes:
            relatorio.write(
                "Nenhuma diferença funcional encontrada.\n"
            )
        else:
            for numero, resultado in enumerate(
                diferentes,
                start=1,
            ):
                correspondencia = resultado.correspondencia

                relatorio.write(
                    f"{numero}. [{correspondencia.analisado.nivel}]\n"
                )
                relatorio.write(
                    f"   Modelo espelho: "
                    f"{nome_exibicao(correspondencia.espelho.datapoint)}\n"
                )
                relatorio.write(
                    f"   Corrigido no analisado: "
                    f"{nome_exibicao(correspondencia.analisado.datapoint)}\n"
                )

                for diferenca in resultado.diferencas_funcionais:
                    relatorio.write(
                        f"      - {diferenca}\n"
                    )

                relatorio.write("\n")

        relatorio.write("\n" + "=" * 100 + "\n")
        relatorio.write(
            "4. REVISÕES TOPOLOGICAS DE SCRIPT/FÓRMULA APLICADAS\n"
        )
        relatorio.write("=" * 100 + "\n\n")

        if not revisoes_topologicas:
            relatorio.write(
                "Nenhuma revisão topológica necessária.\n"
            )
        else:
            for numero, resultado in enumerate(
                revisoes_topologicas,
                start=1,
            ):
                correspondencia = resultado.correspondencia

                relatorio.write(
                    f"{numero}. [{correspondencia.analisado.nivel}]\n"
                )
                relatorio.write(
                    f"   Modelo espelho: "
                    f"{nome_exibicao(correspondencia.espelho.datapoint)}\n"
                )
                relatorio.write(
                    f"   Ajustado no analisado: "
                    f"{nome_exibicao(correspondencia.analisado.datapoint)}\n"
                )

                for revisao in resultado.revisoes_topologicas:
                    relatorio.write(
                        f"      - {revisao}\n"
                    )

                relatorio.write("\n")

        relatorio.write("\n" + "=" * 100 + "\n")
        relatorio.write(
            "5. AVISOS DA GERAÇÃO AUTOMÁTICA\n"
        )
        relatorio.write("=" * 100 + "\n\n")

        avisos = manifesto.get("avisos", [])

        if not avisos:
            relatorio.write(
                "Nenhum aviso. Todos os ajustes previstos foram aplicados.\n"
            )
        else:
            for numero, aviso in enumerate(
                avisos,
                start=1,
            ):
                relatorio.write(
                    f"{numero}. {aviso}\n"
                )


# ============================================================
# EXECUÇÃO PRINCIPAL
# ============================================================

def main() -> None:
    print("=" * 76)
    print(
        "AUDITORIA E CORREÇÃO DO DATASOURCE DADOS CALCULADOS"
    )
    print("=" * 76)

    prefixo_espelho = input(
        "\nPrefixo da usina espelho, exemplo GRA: "
    ).strip()

    prefixo_analisado = input(
        "Prefixo da usina analisada, exemplo CED: "
    ).strip()

    if not prefixo_espelho or not prefixo_analisado:
        print(
            "\nErro: os dois prefixos precisam ser informados."
        )
        sys.exit(1)

    topologia_espelho = perguntar_topologia(
        "espelho"
    )

    topologia_analisado = perguntar_topologia(
        "projeto analisado"
    )

    try:
        os.makedirs(
            PASTA_SAIDA,
            exist_ok=True,
        )

        json_espelho = carregar_json(
            ARQUIVO_ESPELHO
        )

        json_analisado_original = carregar_json(
            ARQUIVO_ANALISADO
        )

        json_analisado_corrigido = copy.deepcopy(
            json_analisado_original
        )

        registros_espelho = (
            filtrar_registros_dados_calculados(
                extrair_registros_datapoints(
                    json_espelho
                ),
                "espelho",
            )
        )

        registros_analisados = (
            filtrar_registros_dados_calculados(
                extrair_registros_datapoints(
                    json_analisado_corrigido
                ),
                "analisado",
            )
        )

        pontos_espelho = [
            registro.datapoint
            for registro in registros_espelho
        ]

        pontos_analisados = [
            registro.datapoint
            for registro in registros_analisados
        ]

        if not pontos_espelho:
            raise ValueError(
                "Nenhum datapoint foi encontrado "
                "no JSON espelho."
            )

        if not pontos_analisados:
            raise ValueError(
                "Nenhum datapoint foi encontrado "
                "no JSON analisado."
            )

        (
            indice_espelho,
            familias_espelho,
            duplicados_espelho,
        ) = indexar_pontos(
            pontos_espelho,
            prefixo_espelho,
            topologia_espelho,
        )

        (
            indice_analisado,
            familias_analisado,
            duplicados_analisado,
        ) = indexar_pontos(
            pontos_analisados,
            prefixo_analisado,
            topologia_analisado,
        )

        (
            correspondencias,
            faltantes,
            extras,
        ) = construir_auditoria(
            familias_espelho,
            familias_analisado,
            prefixo_espelho,
            prefixo_analisado,
            topologia_espelho,
            topologia_analisado,
        )

        correspondencias_avaliadas = [
            comparar_correspondencia(
                correspondencia,
                prefixo_espelho,
                prefixo_analisado,
                topologia_espelho,
                topologia_analisado,
            )
            for correspondencia in correspondencias
        ]

        manifesto = aplicar_ajustes_no_json(
            json_analisado_corrigido,
            registros_analisados,
            correspondencias_avaliadas,
            faltantes,
            prefixo_espelho,
            prefixo_analisado,
            topologia_espelho,
            topologia_analisado,
        )

        salvar_json(
            ARQUIVO_ANALISADO_CORRIGIDO,
            json_analisado_corrigido,
        )

        salvar_json(
            ARQUIVO_AJUSTES_APLICADOS,
            manifesto,
        )

        gerar_relatorio(
            indice_espelho,
            indice_analisado,
            duplicados_espelho,
            duplicados_analisado,
            correspondencias_avaliadas,
            faltantes,
            extras,
            prefixo_espelho,
            prefixo_analisado,
            topologia_espelho,
            topologia_analisado,
            manifesto,
        )

        diferentes = [
            resultado
            for resultado in correspondencias_avaliadas
            if resultado.diferencas_funcionais
        ]

        revisoes = [
            resultado
            for resultado in correspondencias_avaliadas
            if resultado.revisoes_topologicas
        ]

        print("\nAuditoria e correção concluídas!")
        print(
            f"Datapoints adicionados: "
            f"{len(faltantes)}"
        )
        print(
            f"Diferenças funcionais corrigidas: "
            f"{len(diferentes)}"
        )
        print(
            f"Revisões topológicas aplicadas: "
            f"{len(revisoes)}"
        )
        print(
            f"Datapoints extras mantidos: "
            f"{len(extras)}"
        )
        print(
            f"Avisos: "
            f"{len(manifesto.get('avisos', []))}"
        )
        print(
            f"\nJSON corrigido: "
            f"{ARQUIVO_ANALISADO_CORRIGIDO}"
        )
        print(
            f"Manifesto dos ajustes: "
            f"{ARQUIVO_AJUSTES_APLICADOS}"
        )
        print(
            f"Relatório: "
            f"{ARQUIVO_RELATORIO}"
        )

    except (
        FileNotFoundError,
        ValueError,
        json.JSONDecodeError,
    ) as erro:
        print(f"\nErro: {erro}")
        sys.exit(1)

    except KeyboardInterrupt:
        print(
            "\n\nOperação cancelada pelo usuário."
        )
        sys.exit(0)

    except Exception as erro:
        print(
            "\nErro inesperado durante a auditoria:"
        )
        print(erro)
        sys.exit(1)


if __name__ == "__main__":
    main()
