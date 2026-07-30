# -*- coding: utf-8 -*-
from __future__ import annotations
import argparse
import logging
import sys
from pathlib import Path
from analisador_json import analisar_json
from analisador_log import analisar_log
from analisador_scripts import analisar_scripts
from config import (
    ARQUIVO_DATAPOINTS_CONFIRMADOS,
    ARQUIVO_JSON_PADRAO,
    ARQUIVO_LOG_APLICACAO,
    ARQUIVO_LOG_PADRAO,
    ARQUIVO_RELATORIO,
)
from gerador_json import gerar_json_confirmados
from gerador_relatorio import gerar_relatorio

def configurar_logging() -> None:
    ARQUIVO_LOG_APLICACAO.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(name)s | %(message)s', handlers=[logging.FileHandler(ARQUIVO_LOG_APLICACAO, encoding='utf-8')])

def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description='Localiza scripts candidatos a produzir ReferenceError no Scada-LTS.')
    p.add_argument('--log', dest='arquivo_log', type=Path, default=ARQUIVO_LOG_PADRAO)
    p.add_argument('--json', dest='arquivo_json', type=Path, default=ARQUIVO_JSON_PADRAO)
    return p

def main() -> int:
    configurar_logging(); logg = logging.getLogger(__name__); args = parser().parse_args()
    arquivo_log = args.arquivo_log.resolve(); arquivo_json = args.arquivo_json.resolve(); relatorio = ARQUIVO_RELATORIO.resolve(); json_confirmados = ARQUIVO_DATAPOINTS_CONFIRMADOS.resolve()
    print('ANALISADOR DE SCRIPTS SCADA-LTS\n')
    try:
        if not arquivo_log.is_file(): raise FileNotFoundError(f'Arquivo de log não encontrado: {arquivo_log}')
        if not arquivo_json.is_file(): raise FileNotFoundError(f'Arquivo JSON não encontrado: {arquivo_json}')
        print('[1/5] Lendo log'); print('[2/5] Extraindo erros'); rlog = analisar_log(arquivo_log)
        print('[3/5] Lendo JSON'); rjson = analisar_json(arquivo_json)
        print('[4/5] Analisando scripts'); ran = analisar_scripts(rjson.scripts, rlog.erros_agrupados)
        print('[5/5] Gerando relatório'); gerar_relatorio(relatorio, rlog, rjson, ran); quantidade_confirmados_exportados = gerar_json_confirmados(json_confirmados, ran)
        print(f'\nQuantidade de erros: {rlog.total_reference_errors}')
        print(f'Quantidade de scripts: {len(rjson.scripts)}')
        print(f'Quantidade de candidatos: {len(ran.candidatos)}')
        print(f'Quantidade de confirmados: {ran.total_confirmado}')
        print(f'Datapoints confirmados reunidos no JSON: {quantidade_confirmados_exportados}')
        print(f'Caminho completo do TXT: {relatorio}')
        print(f'Caminho completo do JSON: {json_confirmados}')
        return 0
    except Exception as erro:
        logg.exception('Falha durante o processamento.')
        print(f'\nErro: {erro}', file=sys.stderr)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
