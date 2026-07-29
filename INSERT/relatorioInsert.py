# -*- coding: utf-8 -*-
"""
Auditoria de Escritas - Owen Cloud
Autor: Francisco Silveira

Arquivos esperados na mesma pasta do script:
    - escritas.csv
    - entrada.json

Saídas geradas:
    - relatorio_escritas.xlsx
    - jsonAnalise.json

O CSV deve possuir as colunas:
    xid;data_hora

O JSON deve possuir a estrutura:
{
    "dataPoints": [ ... ]
}
"""

import json
import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import PatternFill, Font

# ==========================
# CONFIGURAÇÕES
# ==========================

ARQUIVO_CSV = "./entrada/escritas.csv"
ARQUIVO_JSON = "./entrada/entrada.json"

ARQUIVO_RELATORIO = "./saida/relatorio_escritas.xlsx"
ARQUIVO_JSON_ANALISE = "./saida/jsonAnalise.json"

# Quantidade máxima esperada de escritas em 10 minutos
LIMITE = 2

# ==========================
# LEITURA DO CSV
# ==========================

print("Lendo CSV de escritas...")

df = pd.read_csv(
    ARQUIVO_CSV,
    sep=';',
    encoding='utf-8'
)

df.columns = df.columns.str.strip()

if 'xid' not in df.columns:
    raise Exception("O CSV precisa possuir a coluna 'xid'.")

# ==========================
# CONTAGEM DE ESCRITAS
# ==========================

print("Contando escritas por XID...")

contagem = (
    df.groupby("xid")
      .size()
      .reset_index(name="Quantidade")
)

contagem["Status"] = contagem["Quantidade"].apply(
    lambda x: "OK" if x <= LIMITE else "VERIFICAR"
)

contagem = contagem.sort_values(
    by="Quantidade",
    ascending=False
)

# Dicionário para consulta rápida
contagem_dict = dict(zip(contagem["xid"], contagem["Quantidade"]))

# ==========================
# LEITURA DO JSON
# ==========================

print("Lendo entrada.json...")

with open(ARQUIVO_JSON, "r", encoding="utf-8") as f:
    dados_json = json.load(f)

data_points = dados_json.get("dataPoints", [])

# ==========================
# PROCESSAMENTO
# ==========================

todos = []
necessitam_analise = []
json_saida = {"dataPoints": []}

total_dp = len(data_points)
binarios_ignorados = 0
problemas = 0
ok = 0

print("Analisando datapoints...")

for ponto in data_points:
    xid = ponto.get("xid", "")

    point_locator = ponto.get("pointLocator", {})

    tipo = (
        point_locator.get("modbusDataType")
        or point_locator.get("dataType")
        or "DESCONHECIDO"
    )

    qtd = contagem_dict.get(xid, 0)

    logging = ponto.get("loggingType", "")

    if qtd <= LIMITE:
        status = "OK"
        motivo = "Periodicidade normal"
        ok += 1

    else:
        if str(tipo).upper() == "BINARY":
            status = "BINÁRIO"
            motivo = "Ignorado automaticamente"
            binarios_ignorados += 1

        else:
            status = "VERIFICAR"
            motivo = f"Escreveu {qtd} vezes (esperado <= {LIMITE})"
            problemas += 1

            necessitam_analise.append({
                "DataSource": ponto.get("dataSourceXid", ""),
                "XID": xid,
                "Tipo": tipo,
                "Logging": logging,
                "Quantidade": qtd,
                "Status": status
})

            # Adiciona o datapoint completo ao JSON de análise
            json_saida["dataPoints"].append(ponto)

    todos.append({
        "DataSource": ponto.get("dataSourceXid", ""),
        "XID": xid,
        "Tipo": tipo,
        "Logging": logging,
        "Quantidade": qtd,
        "Status": status
    })

# ==========================
# DATAFRAMES
# ==========================

df_todos = pd.DataFrame(todos)

if not df_todos.empty:
    df_todos = df_todos.sort_values(
        by="Quantidade",
        ascending=False
    )

df_analise = pd.DataFrame(necessitam_analise)

if not df_analise.empty:
    df_analise = df_analise.sort_values(
        by="Quantidade",
        ascending=False
    )

percentual = (problemas / total_dp * 100) if total_dp > 0 else 0

df_resumo = pd.DataFrame({
    "Métrica": [
        "Datapoints no JSON",
        "Funcionando normalmente",
        "Binários ignorados",
        "Necessitam análise",
        "Percentual problemático (%)"
    ],
    "Valor": [
        total_dp,
        ok,
        binarios_ignorados,
        problemas,
        round(percentual, 2)
    ]
})

# ==========================
# EXPORTA EXCEL
# ==========================

print("Gerando relatório Excel...")

with pd.ExcelWriter(ARQUIVO_RELATORIO, engine="openpyxl") as writer:
    df_resumo.to_excel(writer, sheet_name="Resumo", index=False)
    df_todos.to_excel(writer, sheet_name="Todos", index=False)
    df_analise.to_excel(writer, sheet_name="Necessitam Analise", index=False)

# ==========================
# FORMATAÇÃO E CORES (TURBO & AJUSTADO)
# ==========================

wb = load_workbook(ARQUIVO_RELATORIO)

verde = PatternFill("solid", fgColor="C6EFCE")
amarelo = PatternFill("solid", fgColor="FFEB9C")
vermelho = PatternFill("solid", fgColor="FFC7CE")

for ws in wb.worksheets:
    # Negrito no cabeçalho
    for cell in ws[1]:
        cell.font = Font(bold=True)

    if ws.title == "Resumo":
        ws.column_dimensions["A"].width = 40
        ws.column_dimensions["B"].width = 18
    else:
        # Define larguras das colunas
        ws.column_dimensions["A"].width = 30   # DataSource
        ws.column_dimensions["B"].width = 70   # XID
        ws.column_dimensions["C"].width = 22   # Tipo
        ws.column_dimensions["D"].width = 18   # Logging
        ws.column_dimensions["E"].width = 12   # Quantidade
        ws.column_dimensions["F"].width = 15   # Status

        # Pinta as linhas de forma otimizada e direta
        col_status = 6
        max_col = ws.max_column

        for row in range(2, ws.max_row + 1):
            status = ws.cell(row, col_status).value

            if status == "OK":
                fill_atual = verde
            elif status == "BINÁRIO":
                fill_atual = amarelo
            elif status == "VERIFICAR":
                fill_atual = vermelho
            else:
                continue

            for col in range(1, max_col + 1):
                ws.cell(row, col).fill = fill_atual

wb.save(ARQUIVO_RELATORIO)

# ==========================
# EXPORTA JSON
# ==========================

print("Gerando jsonAnalise.json...")

class ScadaJSONEncoder(json.JSONEncoder):
    def iterencode(self, o, _one_shot=False):
        float_map = {
            1.7976931348623157e+308: "1.7976931348623157E308",
            -1.7976931348623157e+308: "-1.7976931348623157E308"
        }
        
        for chunk in super().iterencode(o, _one_shot):
            if chunk.strip().endswith(('e+308', 'e+308,', 'e+308]', 'e+308}')):
                clean_chunk = chunk.strip().rstrip(',]}')
                try:
                    if float(clean_chunk) in float_map:
                        chunk = chunk.replace(clean_chunk, float_map[float(clean_chunk)])
                except ValueError:
                    pass
            yield chunk

with open(ARQUIVO_JSON_ANALISE, "w", encoding="utf-8") as f:
    for chunk in ScadaJSONEncoder(ensure_ascii=False, indent=3).iterencode(json_saida):
        f.write(chunk)

# ==========================
# RESUMO FINAL
# ==========================

print("\n" + "="*50)
print("        AUDITORIA DE ESCRITAS OWEN CLOUD")
print("="*50)
print(f"Datapoints no JSON.............: {total_dp}")
print(f"Funcionando normalmente.......: {ok}")
print(f"Binários ignorados............: {binarios_ignorados}")
print(f"Necessitam análise............: {problemas}")
print(f"Percentual problemático.......: {percentual:.2f}%")
print("="*50)
print(f"Relatório Excel...............: {ARQUIVO_RELATORIO}")
print(f"JSON para análise.............: {ARQUIVO_JSON_ANALISE}")
print("="*50)
print("Fim da auditoria.")
