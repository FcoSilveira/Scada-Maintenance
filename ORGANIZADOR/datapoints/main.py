# -*- coding: utf-8 -*-

"""
ORGANIZADOR DE DATAPOINTS JSON - OWEN CLOUD

Autor: Francisco Silveira

Entrada:
    ./entrada/entrada.json

Saída:
    ./saida/saida.json

Critérios de organização:

1. Tipo do datapoint:
   ALM, MED, STA, CTE, CAL, VIR, CMD

2. Offset:
   Do menor para o maior.

3. Bit:
   Do menor para o maior quando vários datapoints utilizarem
   o mesmo offset.

4. XID:
   Ordem alfabética quando tipo, offset e bit forem iguais.

Importante:

O programa não converte os datapoints para objetos Python.
Os blocos são preservados como texto para evitar alterações em valores como:

"discardHighLimit":1.7976931348623157E308,
"discardLowLimit":-1.7976931348623157E308,
"""

import os
import re
import sys


# ==========================================================
# CONFIGURAÇÕES
# ==========================================================

ARQUIVO_ENTRADA = "./entrada/entrada.json"
ARQUIVO_SAIDA = "./saida/saida.json"

ORDEM_TIPOS = {
    "ALM": 0,
    "MED": 1,
    "STA": 2,
    "CTE": 3,
    "CAL": 4,
    "VIR": 5,
    "CMD": 6,
}

TIPO_DESCONHECIDO = 999
VALOR_AUSENTE = float("inf")

os.makedirs("./saida", exist_ok=True)


# ==========================================================
# FUNÇÕES DE LEITURA
# ==========================================================

def localizar_array_datapoints(texto):
    """
    Localiza o início do array dataPoints.

    Retorna a posição do caractere '['.
    """

    posicao_chave = texto.find('"dataPoints"')

    if posicao_chave == -1:
        raise ValueError(
            'Não foi encontrada a propriedade "dataPoints".'
        )

    inicio_array = texto.find("[", posicao_chave)

    if inicio_array == -1:
        raise ValueError(
            'Não foi encontrado o início do array "dataPoints".'
        )

    return inicio_array


def extrair_datapoints(texto, inicio_array):
    """
    Extrai individualmente cada objeto do array dataPoints.

    A função considera:
    - objetos aninhados;
    - arrays;
    - strings;
    - caracteres escapados;
    - scripts contendo chaves;
    - descrições contendo símbolos JSON.

    Cada datapoint é mantido exatamente como texto.
    """

    datapoints = []

    nivel_objeto = 0
    inicio_objeto = None

    dentro_string = False
    caractere_escapado = False

    indice = inicio_array + 1

    while indice < len(texto):
        caractere = texto[indice]

        # --------------------------------------------------
        # Conteúdo dentro de strings
        # --------------------------------------------------

        if dentro_string:

            if caractere_escapado:
                caractere_escapado = False

            elif caractere == "\\":
                caractere_escapado = True

            elif caractere == '"':
                dentro_string = False

            indice += 1
            continue

        # --------------------------------------------------
        # Conteúdo fora de strings
        # --------------------------------------------------

        if caractere == '"':
            dentro_string = True

        elif caractere == "{":

            if nivel_objeto == 0:
                inicio_objeto = indice

            nivel_objeto += 1

        elif caractere == "}":

            if nivel_objeto > 0:
                nivel_objeto -= 1

                if nivel_objeto == 0 and inicio_objeto is not None:
                    bloco = texto[inicio_objeto:indice + 1]
                    datapoints.append(bloco)
                    inicio_objeto = None

        elif caractere == "]" and nivel_objeto == 0:
            # Fim do array dataPoints
            break

        indice += 1

    return datapoints


# ==========================================================
# EXTRAÇÃO DOS CAMPOS
# ==========================================================

def extrair_string(bloco, propriedade):
    """
    Extrai uma propriedade textual simples do datapoint.

    Exemplo:
        "xid":"USN_DJBT1_STA_Número de Manobras"
    """

    padrao = rf'"{re.escape(propriedade)}"\s*:\s*"((?:\\.|[^"\\])*)"'

    resultado = re.search(
        padrao,
        bloco,
        flags=re.IGNORECASE | re.DOTALL
    )

    if resultado:
        return resultado.group(1)

    return ""


def extrair_numero(bloco, propriedade):
    """
    Extrai uma propriedade numérica inteira ou decimal.

    Exemplos:
        "offset":32016
        "bit":3
        "offset":32016.0
    """

    padrao = (
        rf'"{re.escape(propriedade)}"\s*:\s*'
        rf'(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)'
    )

    resultado = re.search(
        padrao,
        bloco,
        flags=re.IGNORECASE
    )

    if not resultado:
        return None

    valor_texto = resultado.group(1)

    try:
        return float(valor_texto)

    except ValueError:
        return None


def identificar_tipo(xid, nome):
    """
    Identifica o tipo através do XID ou do nome.

    Exemplo:
        USN_DJBT1_STA_Número de Manobras

    O tipo STA será identificado pelo padrão delimitado por "_".
    """

    textos = [xid, nome]

    for texto in textos:

        texto_maiusculo = texto.upper()

        for tipo in ORDEM_TIPOS:

            padrao = rf'(^|_){tipo}(_|$)'

            if re.search(padrao, texto_maiusculo):
                return tipo

    return "DESCONHECIDO"


def obter_metadados(bloco, indice_original):
    """
    Obtém os campos utilizados para a ordenação.
    """

    xid = extrair_string(bloco, "xid")
    nome = extrair_string(bloco, "name")

    tipo = identificar_tipo(xid, nome)

    offset = extrair_numero(bloco, "offset")
    bit = extrair_numero(bloco, "bit")

    return {
        "bloco": bloco,
        "indice_original": indice_original,
        "xid": xid,
        "nome": nome,
        "tipo": tipo,
        "offset": offset,
        "bit": bit,
    }


# ==========================================================
# ORDENAÇÃO
# ==========================================================

def chave_ordenacao(datapoint):
    """
    Define a prioridade de organização:

    1. Tipo;
    2. Offset;
    3. Bit;
    4. XID;
    5. Posição original.
    """

    tipo = datapoint["tipo"]
    offset = datapoint["offset"]
    bit = datapoint["bit"]
    xid = datapoint["xid"]

    ordem_tipo = ORDEM_TIPOS.get(
        tipo,
        TIPO_DESCONHECIDO
    )

    offset_ordenacao = (
        offset
        if offset is not None
        else VALOR_AUSENTE
    )

    bit_ordenacao = (
        bit
        if bit is not None
        else VALOR_AUSENTE
    )

    return (
        ordem_tipo,
        offset_ordenacao,
        bit_ordenacao,
        xid.casefold(),
        datapoint["indice_original"],
    )


# ==========================================================
# FORMATAÇÃO DO ARQUIVO
# ==========================================================

def ajustar_margem_esquerda(bloco, quantidade_espacos=6):
    """
    Ajusta somente a margem esquerda do datapoint.

    O conteúdo e os valores internos não são modificados.
    """

    linhas = bloco.strip().splitlines()

    if not linhas:
        return bloco

    indentacoes = []

    for linha in linhas:

        if linha.strip():
            indentacao = len(linha) - len(linha.lstrip())
            indentacoes.append(indentacao)

    menor_indentacao = min(indentacoes) if indentacoes else 0
    prefixo = " " * quantidade_espacos

    linhas_ajustadas = []

    for linha in linhas:

        if linha.strip():
            linha_sem_margem = linha[menor_indentacao:]
            linhas_ajustadas.append(prefixo + linha_sem_margem)

        else:
            linhas_ajustadas.append("")

    return "\n".join(linhas_ajustadas)


def gravar_json(datapoints_ordenados):
    """
    Grava o arquivo sem serialização JSON.

    Isso preserva exatamente valores como:

    1.7976931348623157E308
    -1.7976931348623157E308
    Infinity
    -Infinity
    """

    with open(
        ARQUIVO_SAIDA,
        "w",
        encoding="utf-8",
        newline="\n"
    ) as arquivo:

        arquivo.write("{\n")
        arquivo.write('   "dataPoints":[\n')

        total = len(datapoints_ordenados)

        for indice, datapoint in enumerate(datapoints_ordenados):

            bloco = ajustar_margem_esquerda(
                datapoint["bloco"],
                quantidade_espacos=6
            )

            arquivo.write(bloco)

            if indice < total - 1:
                arquivo.write(",")

            arquivo.write("\n")

        arquivo.write("   ]\n")
        arquivo.write("}\n")


# ==========================================================
# RELATÓRIO
# ==========================================================

def exibir_resumo(datapoints):
    """
    Exibe a quantidade encontrada por tipo.
    """

    contagem = {
        tipo: 0
        for tipo in ORDEM_TIPOS
    }

    desconhecidos = 0
    sem_offset = 0
    sem_bit = 0

    for datapoint in datapoints:

        tipo = datapoint["tipo"]

        if tipo in contagem:
            contagem[tipo] += 1
        else:
            desconhecidos += 1

        if datapoint["offset"] is None:
            sem_offset += 1

        if datapoint["bit"] is None:
            sem_bit += 1

    print()
    print("=" * 70)
    print("RESULTADO")
    print("=" * 70)
    print(f"Total de datapoints........: {len(datapoints)}")

    print()
    print("Datapoints por tipo:")

    for tipo in ORDEM_TIPOS:
        print(f"  {tipo}....................: {contagem[tipo]}")

    print(f"  DESCONHECIDO..............: {desconhecidos}")

    print()
    print(f"Datapoints sem offset......: {sem_offset}")
    print(f"Datapoints sem bit.........: {sem_bit}")

    print()
    print("Ordem aplicada:")
    print("  Tipo → Offset → Bit → XID")

    print()
    print("Arquivo gerado:")
    print(f"  {ARQUIVO_SAIDA}")
    print("=" * 70)


# ==========================================================
# EXECUÇÃO PRINCIPAL
# ==========================================================

def main():

    print("=" * 70)
    print("ORGANIZADOR DE DATAPOINTS JSON - OWEN CLOUD")
    print("=" * 70)
    print()

    # ------------------------------------------------------
    # Verifica arquivo
    # ------------------------------------------------------

    if not os.path.isfile(ARQUIVO_ENTRADA):
        raise FileNotFoundError(
            f"Arquivo de entrada não encontrado: {ARQUIVO_ENTRADA}"
        )

    # ------------------------------------------------------
    # Lê arquivo original
    # ------------------------------------------------------

    print("Lendo arquivo de entrada...")

    with open(
        ARQUIVO_ENTRADA,
        "r",
        encoding="utf-8"
    ) as arquivo:

        texto = arquivo.read()

    # ------------------------------------------------------
    # Extrai datapoints
    # ------------------------------------------------------

    print("Localizando o array dataPoints...")

    inicio_array = localizar_array_datapoints(texto)

    print("Extraindo datapoints...")

    blocos = extrair_datapoints(
        texto,
        inicio_array
    )

    if not blocos:
        raise ValueError(
            "Nenhum datapoint foi encontrado no arquivo."
        )

    print(f"Datapoints encontrados: {len(blocos)}")

    # ------------------------------------------------------
    # Obtém metadados
    # ------------------------------------------------------

    print("Identificando tipos, offsets e bits...")

    datapoints = []

    for indice, bloco in enumerate(blocos):

        metadados = obter_metadados(
            bloco,
            indice
        )

        datapoints.append(metadados)

    # ------------------------------------------------------
    # Ordena
    # ------------------------------------------------------

    print("Organizando datapoints...")

    datapoints_ordenados = sorted(
        datapoints,
        key=chave_ordenacao
    )

    # ------------------------------------------------------
    # Grava saída
    # ------------------------------------------------------

    print("Gravando arquivo organizado...")

    gravar_json(datapoints_ordenados)

    print("JSON organizado com sucesso.")

    exibir_resumo(datapoints_ordenados)


if __name__ == "__main__":

    try:
        main()

    except FileNotFoundError as erro:
        print()
        print(f"ERRO: {erro}")
        sys.exit(1)

    except ValueError as erro:
        print()
        print(f"ERRO: {erro}")
        sys.exit(1)

    except Exception as erro:
        print()
        print("Ocorreu um erro inesperado:")
        print(erro)
        sys.exit(1)