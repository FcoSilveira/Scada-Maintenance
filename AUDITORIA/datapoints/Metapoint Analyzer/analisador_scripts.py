# -*- coding: utf-8 -*-
from __future__ import annotations
import math
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable
from analisador_json import ScriptEncontrado
from analisador_log import ErroAgrupado
from config import GLOBAIS_JAVASCRIPT, PALAVRAS_RESERVADAS_JS, TOLERANCIA_LINHA

IDENT = re.compile(r'[A-Za-z_$][A-Za-z0-9_$]*')

@dataclass(frozen=True)
class ScriptSanitizado:
    codigo: str
    mapa_linhas: tuple[int, ...]

@dataclass(frozen=True)
class Candidato:
    status: str
    confianca: int
    tipo_erro: str
    variavel: str
    linha_log: int
    ocorrencias_log: int
    script: ScriptEncontrado
    linhas_uso: tuple[int, ...]
    motivo: str

@dataclass(frozen=True)
class ResultadoAnalise:
    candidatos: tuple[Candidato, ...]
    total_confirmado: int
    total_provavel: int
    total_possivel: int

def remover_comentarios_e_strings(script: str) -> ScriptSanitizado:
    out: list[str] = []
    mapa: list[int] = []
    i = 0; linha = 1; estado = 'codigo'; delim = ''
    while i < len(script):
        c = script[i]; p = script[i+1] if i+1 < len(script) else ''
        if estado == 'codigo':
            if c == '/' and p == '/':
                out += [' ',' ']; mapa += [linha,linha]; i += 2; estado = 'linha'; continue
            if c == '/' and p == '*':
                out += [' ',' ']; mapa += [linha,linha]; i += 2; estado = 'bloco'; continue
            if c in {'"', "'", '`'}:
                delim = c; out.append(' '); mapa.append(linha); i += 1; estado = 'string'; continue
            out.append(c); mapa.append(linha)
            if c == '\n': linha += 1
            i += 1; continue
        if estado == 'linha':
            if c == '\n': out.append('\n'); mapa.append(linha); linha += 1; estado = 'codigo'
            else: out.append(' '); mapa.append(linha)
            i += 1; continue
        if estado == 'bloco':
            if c == '*' and p == '/':
                out += [' ',' ']; mapa += [linha,linha]; i += 2; estado = 'codigo'; continue
            if c == '\n': out.append('\n'); mapa.append(linha); linha += 1
            else: out.append(' '); mapa.append(linha)
            i += 1; continue
        if estado == 'string':
            if c == '\\':
                out.append(' '); mapa.append(linha); i += 1
                if i < len(script):
                    if script[i] == '\n': out.append('\n'); mapa.append(linha); linha += 1
                    else: out.append(' '); mapa.append(linha)
                    i += 1
                continue
            if c == delim:
                out.append(' '); mapa.append(linha); i += 1; estado = 'codigo'; continue
            if c == '\n': out.append('\n'); mapa.append(linha); linha += 1
            else: out.append(' '); mapa.append(linha)
            i += 1
    return ScriptSanitizado(''.join(out), tuple(mapa))

def _propriedade(codigo: str, inicio: int) -> bool:
    i = inicio - 1
    while i >= 0 and codigo[i].isspace(): i -= 1
    return i >= 0 and codigo[i] == '.'

def localizar_usos(s: ScriptSanitizado, variavel: str) -> tuple[int, ...]:
    linhas = set()
    for m in IDENT.finditer(s.codigo):
        if m.group() == variavel and not _propriedade(s.codigo, m.start()):
            linhas.add(s.mapa_linhas[m.start()])
    return tuple(sorted(linhas))

def declaradas(codigo: str) -> set[str]:
    d = {m.group(1) for m in re.finditer(r'\b(?:var|let|const)\s+([A-Za-z_$][A-Za-z0-9_$]*)', codigo)}
    for m in re.finditer(r'\bfunction(?:\s+[A-Za-z_$][A-Za-z0-9_$]*)?\s*\((?P<p>[^)]*)\)', codigo):
        for p in m.group('p').split(','):
            t = p.strip().split('=',1)[0].strip()
            if IDENT.fullmatch(t): d.add(t)
    for m in re.finditer(r'(?:\((?P<p>[^)]*)\)|(?P<s>[A-Za-z_$][A-Za-z0-9_$]*))\s*=>', codigo):
        if m.group('s'): d.add(m.group('s'))
        else:
            for p in (m.group('p') or '').split(','):
                t = p.strip().split('=',1)[0].strip()
                if IDENT.fullmatch(t): d.add(t)
    d.update(m.group(1) for m in re.finditer(r'\bcatch\s*\(\s*([A-Za-z_$][A-Za-z0-9_$]*)\s*\)', codigo))
    return d

def _confianca(dist: int, ocorr: int, contexto: bool, habilitado: str) -> int:
    linha = math.exp(-0.50 * dist)
    recorr = 1.0 - math.exp(-0.18 * max(ocorr, 1))
    ctx = 1.0 if contexto else 0.62
    base = 0.58*linha + 0.24*ctx + 0.18*recorr
    if habilitado == 'NÃO': base *= 0.78
    return max(0, min(100, round(base*100)))

def _status(dist: int, contexto: bool) -> str:
    if dist <= TOLERANCIA_LINHA and contexto: return 'CONFIRMADO'
    if dist <= 6 or contexto: return 'PROVÁVEL'
    return 'POSSÍVEL'

def _motivo(dist: int, contexto: bool, linhas: tuple[int, ...]) -> str:
    p = [
        'A variável é usada como identificador independente.',
        'Não foi encontrada declaração com var, let, const, parâmetro de função, arrow function ou catch.',
        'A variável não existe no contexto disponível do elemento.',
    ]
    if dist == 0: p.append('O uso ocorre exatamente na linha indicada pelo log.')
    elif dist <= TOLERANCIA_LINHA: p.append(f'O uso está a {dist} linha(s) da linha indicada pelo log, dentro da tolerância de ±{TOLERANCIA_LINHA}.')
    else: p.append(f'O uso mais próximo está a {dist} linha(s) da linha indicada pelo log.')
    if not contexto: p.append('A estrutura de contexto não pôde ser determinada completamente.')
    p.append('Linhas de uso identificadas: ' + ', '.join(map(str, linhas)) + '.')
    return ' '.join(p)

def criar_indice(scripts: Iterable[ScriptEncontrado], vars_: set[str]):
    idx = defaultdict(list)
    for script in scripts:
        san = remover_comentarios_e_strings(script.script)
        tokens = {m.group() for m in IDENT.finditer(san.codigo) if not _propriedade(san.codigo, m.start())}
        for v in tokens & vars_:
            linhas = localizar_usos(san, v)
            if linhas: idx[v].append((script, san, linhas))
    return idx

def analisar_scripts(scripts: tuple[ScriptEncontrado, ...], erros: tuple[ErroAgrupado, ...]) -> ResultadoAnalise:
    idx = criar_indice(scripts, {e.variavel for e in erros})
    candidatos: list[Candidato] = []
    for erro in erros:
        if erro.variavel in PALAVRAS_RESERVADAS_JS or erro.variavel in GLOBAIS_JAVASCRIPT:
            continue
        for script, san, linhas in idx.get(erro.variavel, []):
            if erro.variavel in declaradas(san.codigo) or erro.variavel in script.contexto:
                continue
            reval = localizar_usos(remover_comentarios_e_strings(script.script), erro.variavel)
            if not reval: continue
            dist = min(abs(l-erro.linha_script) for l in reval)
            conf = _confianca(dist, erro.quantidade, script.contexto_determinado, script.habilitado)
            status = _status(dist, script.contexto_determinado)
            candidatos.append(Candidato(status, conf, erro.tipo_erro, erro.variavel, erro.linha_script, erro.quantidade, script, reval, _motivo(dist, script.contexto_determinado, reval)))
    # Deduplicação principal: variável + linha do log + XID.
    # Na ausência de XID, utiliza o caminho do datapoint.
    deduplicados: dict[tuple[str, int, str], Candidato] = {}
    prioridade = {'CONFIRMADO': 0, 'PROVÁVEL': 1, 'POSSÍVEL': 2}
    for candidato in candidatos:
        identificador = candidato.script.xid.strip() or candidato.script.caminho_datapoint
        chave = (candidato.variavel, candidato.linha_log, identificador)
        atual = deduplicados.get(chave)
        if atual is None or (
            prioridade[candidato.status], -candidato.confianca
        ) < (
            prioridade[atual.status], -atual.confianca
        ):
            deduplicados[chave] = candidato

    candidatos = list(deduplicados.values())
    candidatos.sort(key=lambda c: (
        c.variavel.casefold(),
        c.linha_log,
        prioridade[c.status],
        -c.confianca,
        (c.script.xid or c.script.caminho_datapoint).casefold(),
    ))
    return ResultadoAnalise(tuple(candidatos), sum(c.status=='CONFIRMADO' for c in candidatos), sum(c.status=='PROVÁVEL' for c in candidatos), sum(c.status=='POSSÍVEL' for c in candidatos))
