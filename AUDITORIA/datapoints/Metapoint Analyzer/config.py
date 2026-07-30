# -*- coding: utf-8 -*-
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ARQUIVO_LOG_PADRAO = BASE_DIR / 'entrada' / 'mango.log'
ARQUIVO_JSON_PADRAO = BASE_DIR / 'entrada' / 'entrada.json'
ARQUIVO_RELATORIO = BASE_DIR / 'saida' / 'relatorio_datapoints.txt'
ARQUIVO_DATAPOINTS_CONFIRMADOS = BASE_DIR / 'saida' / 'datapoints_confirmados.json'
ARQUIVO_LOG_APLICACAO = BASE_DIR / 'logs' / 'analisador.log'

CAMPOS_SCRIPT_CONHECIDOS = {
    'script', 'scriptText', 'expression', 'formula', 'javascript', 'code',
    'updateScript', 'conditionScript', 'activeScript', 'inactiveScript',
    'resultScript',
}

PALAVRAS_RESERVADAS_JS = {
    'await','break','case','catch','class','const','continue','debugger','default',
    'delete','do','else','enum','export','extends','false','finally','for',
    'function','if','implements','import','in','instanceof','interface','let',
    'new','null','package','private','protected','public','return','static',
    'super','switch','this','throw','true','try','typeof','var','void','while',
    'with','yield',
}

GLOBAIS_JAVASCRIPT = {
    'Array','ArrayBuffer','BigInt','Boolean','DataView','Date','decodeURI',
    'decodeURIComponent','encodeURI','encodeURIComponent','Error','escape','eval',
    'EvalError','Float32Array','Float64Array','Function','Infinity','Int16Array',
    'Int32Array','Int8Array','Intl','isFinite','isNaN','JSON','Map','Math','NaN',
    'Number','Object','parseFloat','parseInt','Promise','Proxy','RangeError',
    'ReferenceError','Reflect','RegExp','Set','String','Symbol','SyntaxError',
    'TypeError','Uint16Array','Uint32Array','Uint8Array','Uint8ClampedArray',
    'undefined','unescape','URIError','WeakMap','WeakSet',
}

INDICADORES_JAVASCRIPT = (
    'return ', 'function ', '=>', 'var ', 'let ', 'const ', 'if ', 'if(',
    'for ', 'for(', 'while ', 'while(', 'switch ', 'switch(', 'Math.',
    '.value', ';',
)
TOLERANCIA_LINHA = 2
