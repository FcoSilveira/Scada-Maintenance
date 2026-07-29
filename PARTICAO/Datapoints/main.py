# -*- coding: utf-8 -*-

"""
PARTICIONADOR / EXCLUSOR DE JSON - OWEN CLOUD
Interface gráfica em Tkinter

Autor: Francisco Silveira

Funções:
- Selecionar o arquivo JSON de entrada.
- Selecionar o arquivo JSON de saída.
- Escolher entre incluir ou excluir correspondências.
- Adicionar, editar e remover condições.
- Processar o arquivo sem alterar a representação textual original.
- Preservar valores como:
    Infinity
    -Infinity
    1.7976931348623157E308
    -1.7976931348623157E308
"""

import json
import os
import re
import tkinter as tk
from dataclasses import dataclass
from tkinter import filedialog, messagebox, ttk


# ==========================================================
# CONFIGURAÇÕES
# ==========================================================

TITULO_APLICACAO = "Particionador / Exclusor de JSON - Owen Cloud"

PASTA_BASE = os.path.dirname(os.path.abspath(__file__))
PASTA_ENTRADA_PADRAO = os.path.join(PASTA_BASE, "entrada")
PASTA_SAIDA_PADRAO = os.path.join(PASTA_BASE, "saida")

ARQUIVO_ENTRADA_PADRAO = os.path.join(
    PASTA_ENTRADA_PADRAO,
    "entrada.json",
)

ARQUIVO_SAIDA_PADRAO = os.path.join(
    PASTA_SAIDA_PADRAO,
    "jsonFiltrado.json",
)

NOME_ARQUIVO_SAIDA_PADRAO = "jsonFiltrado.json"

SUFIXOS_SAIDA_POR_MODO = {
    "incluir": "filtrado_por_caractere",
    "excluir": "removido_por_caractere",
}


def formatar_caminho_interface(caminho: str) -> str:
    return os.path.normpath(caminho)


# ==========================================================
# MODELOS
# ==========================================================

@dataclass(frozen=True)
class ResultadoFiltro:
    datapoints_saida: list[str]
    datapoints_correspondentes: list[str]
    ocorrencias_por_condicao: dict[str, int]


# ==========================================================
# PROCESSAMENTO DO JSON
# ==========================================================

def localizar_inicio_datapoints(texto: str) -> int:
    """Localiza o início do array dataPoints."""

    posicao_chave = texto.find('"dataPoints"')

    if posicao_chave == -1:
        raise ValueError(
            'Não foi encontrada a propriedade "dataPoints" no arquivo.'
        )

    inicio_lista = texto.find("[", posicao_chave)

    if inicio_lista == -1:
        raise ValueError(
            'A propriedade "dataPoints" não possui uma lista válida.'
        )

    return inicio_lista


def extrair_datapoints(
    texto: str,
    inicio_lista: int,
) -> list[str]:
    """
    Extrai os objetos do array dataPoints preservando o texto original.

    Chaves existentes dentro de strings, scripts, descrições e fórmulas
    são ignoradas durante a identificação dos objetos.
    """

    datapoints = []

    nivel_objeto = 0
    inicio_objeto = None

    dentro_string = False
    caractere_escapado = False

    indice = inicio_lista + 1

    while indice < len(texto):
        caractere = texto[indice]

        if dentro_string:
            if caractere_escapado:
                caractere_escapado = False

            elif caractere == "\\":
                caractere_escapado = True

            elif caractere == '"':
                dentro_string = False

            indice += 1
            continue

        if caractere == '"':
            dentro_string = True

        elif caractere == "{":
            if nivel_objeto == 0:
                inicio_linha = texto.rfind("\n", 0, indice) + 1
                margem_original = texto[inicio_linha:indice]

                if margem_original.strip():
                    inicio_objeto = indice
                else:
                    inicio_objeto = inicio_linha

            nivel_objeto += 1

        elif caractere == "}":
            if nivel_objeto > 0:
                nivel_objeto -= 1

                if (
                    nivel_objeto == 0
                    and inicio_objeto is not None
                ):
                    bloco = texto[
                        inicio_objeto:indice + 1
                    ]

                    datapoints.append(bloco)
                    inicio_objeto = None

        elif caractere == "]" and nivel_objeto == 0:
            break

        indice += 1

    if nivel_objeto != 0:
        raise ValueError(
            "A lista dataPoints parece estar incompleta "
            "ou possui chaves desbalanceadas."
        )

    return datapoints


def nome_saida_por_entrada(
    caminho_entrada: str,
    modo: str,
) -> str:
    """Sugere um nome de saida baseado no arquivo de entrada."""

    pasta = os.path.dirname(os.path.abspath(caminho_entrada))
    nome_base = os.path.splitext(os.path.basename(caminho_entrada))[0]
    sufixo = SUFIXOS_SAIDA_POR_MODO.get(
        modo,
        SUFIXOS_SAIDA_POR_MODO["incluir"],
    )

    return formatar_caminho_interface(
        os.path.join(
            pasta,
            f"{nome_base}_{sufixo}.json",
        )
    )

def normalizar_objeto_para_validacao(bloco: str) -> str:
    bloco_validacao = bloco.rstrip()

    if bloco_validacao.endswith(","):
        bloco_validacao = bloco_validacao[:-1].rstrip()

    return bloco_validacao


def extrair_xid_do_bloco(bloco: str) -> str:
    resultado = re.search(
        r'"xid"\s*:\s*"((?:\\.|[^"\\])*)"',
        bloco,
    )

    if not resultado:
        return "(xid nao encontrado)"

    xid_bruto = resultado.group(1)

    try:
        return json.loads(f'"{xid_bruto}"')
    except json.JSONDecodeError:
        return xid_bruto


def validar_blocos_json(blocos: list[str]) -> list[tuple[int, str, str]]:
    invalidos = []

    for indice, bloco in enumerate(blocos, start=1):
        try:
            json.loads(normalizar_objeto_para_validacao(bloco))
        except json.JSONDecodeError as erro:
            invalidos.append(
                (
                    indice,
                    extrair_xid_do_bloco(bloco),
                    str(erro),
                )
            )

    return invalidos


def encontrar_condicoes_no_bloco(
    bloco: str,
    condicoes: list[str],
    diferenciar_maiusculas: bool,
) -> list[str]:
    """Retorna as condições encontradas em um datapoint."""

    if diferenciar_maiusculas:
        return [
            condicao
            for condicao in condicoes
            if condicao in bloco
        ]

    bloco_comparacao = bloco.casefold()

    return [
        condicao
        for condicao in condicoes
        if condicao.casefold() in bloco_comparacao
    ]


def filtrar_datapoints(
    datapoints: list[str],
    condicoes: list[str],
    modo: str,
    diferenciar_maiusculas: bool,
) -> ResultadoFiltro:
    """
    Aplica as condições utilizando a regra OU.

    modo="incluir":
        Mantém somente os datapoints correspondentes.

    modo="excluir":
        Mantém somente os datapoints não correspondentes.
    """

    datapoints_saida = []
    datapoints_correspondentes = []

    ocorrencias_por_condicao = {
        condicao: 0
        for condicao in condicoes
    }

    for bloco in datapoints:
        condicoes_encontradas = encontrar_condicoes_no_bloco(
            bloco,
            condicoes,
            diferenciar_maiusculas,
        )

        corresponde = bool(condicoes_encontradas)

        if corresponde:
            datapoints_correspondentes.append(bloco)

            for condicao in condicoes_encontradas:
                ocorrencias_por_condicao[condicao] += 1

        if modo == "incluir" and corresponde:
            datapoints_saida.append(bloco)

        elif modo == "excluir" and not corresponde:
            datapoints_saida.append(bloco)

    return ResultadoFiltro(
        datapoints_saida=datapoints_saida,
        datapoints_correspondentes=datapoints_correspondentes,
        ocorrencias_por_condicao=ocorrencias_por_condicao,
    )


def ajustar_indentacao_bloco(
    bloco: str,
    espacos: int = 6,
) -> str:
    """
    Ajusta somente a margem esquerda do bloco.

    O conteúdo interno permanece textual.
    """

    linhas = bloco.strip().splitlines()

    if not linhas:
        return bloco

    indentacoes = [
        len(linha) - len(linha.lstrip())
        for linha in linhas
        if linha.strip()
    ]

    menor_indentacao = min(indentacoes) if indentacoes else 0
    prefixo = " " * espacos

    linhas_ajustadas = []

    for linha in linhas:
        if linha.strip():
            linha_sem_margem = linha[menor_indentacao:]
            linhas_ajustadas.append(prefixo + linha_sem_margem)
        else:
            linhas_ajustadas.append("")

    return "\n".join(linhas_ajustadas)


def gravar_json_saida(
    caminho: str,
    datapoints: list[str],
) -> None:
    """
    Grava o JSON preservando os blocos textuais originais.

    Nao reindenta os datapoints, para que buscas textuais do arquivo
    original continuem funcionando no arquivo de saida.
    """

    pasta_saida = os.path.dirname(os.path.abspath(caminho))

    os.makedirs(
        pasta_saida,
        exist_ok=True,
    )

    linhas = [
        "{\n",
        '   "dataPoints":[\n',
    ]

    for indice, bloco in enumerate(datapoints):
        bloco_preservado = normalizar_objeto_para_validacao(bloco)

        linhas.append(bloco_preservado)

        if indice < len(datapoints) - 1:
            linhas.append(",")

        linhas.append("\n")

    linhas.append("   ]\n")
    linhas.append("}\n")

    texto_saida = "".join(linhas)

    json.loads(texto_saida)

    with open(
        caminho,
        "w",
        encoding="utf-8",
        newline="\n",
    ) as arquivo:
        arquivo.write(texto_saida)


# ==========================================================
# INTERFACE GRÁFICA
# ==========================================================

class AplicacaoParticionador(tk.Tk):
    def __init__(self) -> None:
        super().__init__()

        self.title(TITULO_APLICACAO)
        self.geometry("920x720")
        self.minsize(820, 650)

        self.arquivo_entrada = tk.StringVar(
            value=formatar_caminho_interface(ARQUIVO_ENTRADA_PADRAO)
        )

        self.modo = tk.StringVar(
            value="incluir"
        )

        self.saida_automatica = True
        self.arquivo_saida = tk.StringVar(
            value=nome_saida_por_entrada(
                self.arquivo_entrada.get(),
                self.modo.get(),
            )
        )

        self.diferenciar_maiusculas = tk.BooleanVar(
            value=True
        )

        self.condicao_digitada = tk.StringVar()
        self.status = tk.StringVar(
            value="Aguardando configuração."
        )

        self.criar_estilos()
        self.criar_interface()

        self.bind("<Return>", self.adicionar_condicao_por_enter)
        self.protocol("WM_DELETE_WINDOW", self.fechar_aplicacao)

    def criar_estilos(self) -> None:
        estilo = ttk.Style(self)

        try:
            estilo.theme_use("vista")
        except tk.TclError:
            pass

        estilo.configure(
            "Titulo.TLabel",
            font=("Segoe UI", 18, "bold"),
        )

        estilo.configure(
            "Subtitulo.TLabel",
            font=("Segoe UI", 10),
        )

        estilo.configure(
            "Secao.TLabelframe.Label",
            font=("Segoe UI", 10, "bold"),
        )

        estilo.configure(
            "Acao.TButton",
            font=("Segoe UI", 10, "bold"),
            padding=(14, 8),
        )

        estilo.configure(
            "Status.TLabel",
            font=("Segoe UI", 9),
        )

    def criar_interface(self) -> None:
        container = ttk.Frame(
            self,
            padding=18,
        )

        container.pack(
            fill="both",
            expand=True,
        )

        ttk.Label(
            container,
            text="Particionador / Exclusor de JSON",
            style="Titulo.TLabel",
        ).pack(anchor="w")

        ttk.Label(
            container,
            text=(
                "Filtre datapoints do Scada sem alterar a representação "
                "textual original do arquivo."
            ),
            style="Subtitulo.TLabel",
        ).pack(
            anchor="w",
            pady=(0, 16),
        )

        self.criar_secao_arquivos(container)
        self.criar_secao_modo(container)
        self.criar_secao_condicoes(container)
        self.criar_secao_acoes(container)
        self.criar_barra_status(container)

    def criar_secao_arquivos(
        self,
        container: ttk.Frame,
    ) -> None:
        quadro = ttk.LabelFrame(
            container,
            text="Arquivos",
            padding=12,
            style="Secao.TLabelframe",
        )

        quadro.pack(
            fill="x",
            pady=(0, 12),
        )

        quadro.columnconfigure(
            1,
            weight=1,
        )

        ttk.Label(
            quadro,
            text="Arquivo de entrada:",
        ).grid(
            row=0,
            column=0,
            sticky="w",
            padx=(0, 8),
            pady=5,
        )

        ttk.Entry(
            quadro,
            textvariable=self.arquivo_entrada,
        ).grid(
            row=0,
            column=1,
            sticky="ew",
            pady=5,
        )

        ttk.Button(
            quadro,
            text="Selecionar...",
            command=self.selecionar_arquivo_entrada,
        ).grid(
            row=0,
            column=2,
            padx=(8, 0),
            pady=5,
        )

        ttk.Label(
            quadro,
            text="Arquivo de saída:",
        ).grid(
            row=1,
            column=0,
            sticky="w",
            padx=(0, 8),
            pady=5,
        )

        ttk.Entry(
            quadro,
            textvariable=self.arquivo_saida,
        ).grid(
            row=1,
            column=1,
            sticky="ew",
            pady=5,
        )

        ttk.Button(
            quadro,
            text="Selecionar...",
            command=self.selecionar_arquivo_saida,
        ).grid(
            row=1,
            column=2,
            padx=(8, 0),
            pady=5,
        )

    def criar_secao_modo(
        self,
        container: ttk.Frame,
    ) -> None:
        quadro = ttk.LabelFrame(
            container,
            text="Modo de operação",
            padding=12,
            style="Secao.TLabelframe",
        )

        quadro.pack(
            fill="x",
            pady=(0, 12),
        )

        ttk.Radiobutton(
            quadro,
            text=(
                "Incluir correspondentes — mantém somente "
                "os datapoints encontrados"
            ),
            variable=self.modo,
            value="incluir",
            command=self.atualizar_saida_automatica_por_modo,
        ).pack(
            anchor="w",
            pady=3,
        )

        ttk.Radiobutton(
            quadro,
            text=(
                "Excluir correspondentes — mantém todos, "
                "exceto os datapoints encontrados"
            ),
            variable=self.modo,
            value="excluir",
            command=self.atualizar_saida_automatica_por_modo,
        ).pack(
            anchor="w",
            pady=3,
        )

        ttk.Checkbutton(
            quadro,
            text="Diferenciar letras maiúsculas e minúsculas",
            variable=self.diferenciar_maiusculas,
        ).pack(
            anchor="w",
            pady=(8, 0),
        )

    def criar_secao_condicoes(
        self,
        container: ttk.Frame,
    ) -> None:
        quadro = ttk.LabelFrame(
            container,
            text="Condições de pesquisa",
            padding=12,
            style="Secao.TLabelframe",
        )

        quadro.pack(
            fill="both",
            expand=True,
            pady=(0, 12),
        )

        quadro.columnconfigure(
            0,
            weight=1,
        )

        quadro.rowconfigure(
            1,
            weight=1,
        )

        barra_entrada = ttk.Frame(quadro)

        barra_entrada.grid(
            row=0,
            column=0,
            sticky="ew",
            pady=(0, 10),
        )

        barra_entrada.columnconfigure(
            0,
            weight=1,
        )

        self.campo_condicao = ttk.Entry(
            barra_entrada,
            textvariable=self.condicao_digitada,
        )

        self.campo_condicao.grid(
            row=0,
            column=0,
            sticky="ew",
        )

        ttk.Button(
            barra_entrada,
            text="Adicionar",
            command=self.adicionar_condicao,
        ).grid(
            row=0,
            column=1,
            padx=(8, 0),
        )

        area_lista = ttk.Frame(quadro)

        area_lista.grid(
            row=1,
            column=0,
            sticky="nsew",
        )

        area_lista.columnconfigure(
            0,
            weight=1,
        )

        area_lista.rowconfigure(
            0,
            weight=1,
        )

        self.lista_condicoes = tk.Listbox(
            area_lista,
            selectmode=tk.SINGLE,
            activestyle="dotbox",
            font=("Segoe UI", 10),
            exportselection=False,
        )

        self.lista_condicoes.grid(
            row=0,
            column=0,
            sticky="nsew",
        )

        barra_rolagem = ttk.Scrollbar(
            area_lista,
            orient="vertical",
            command=self.lista_condicoes.yview,
        )

        barra_rolagem.grid(
            row=0,
            column=1,
            sticky="ns",
        )

        self.lista_condicoes.configure(
            yscrollcommand=barra_rolagem.set
        )

        botoes_lista = ttk.Frame(quadro)

        botoes_lista.grid(
            row=2,
            column=0,
            sticky="w",
            pady=(10, 0),
        )

        ttk.Button(
            botoes_lista,
            text="Editar selecionada",
            command=self.editar_condicao,
        ).pack(
            side="left",
        )

        ttk.Button(
            botoes_lista,
            text="Remover selecionada",
            command=self.remover_condicao,
        ).pack(
            side="left",
            padx=(8, 0),
        )

        ttk.Button(
            botoes_lista,
            text="Limpar todas",
            command=self.limpar_condicoes,
        ).pack(
            side="left",
            padx=(8, 0),
        )

        self.lista_condicoes.bind(
            "<Double-Button-1>",
            lambda _evento: self.editar_condicao(),
        )

    def criar_secao_acoes(
        self,
        container: ttk.Frame,
    ) -> None:
        quadro = ttk.Frame(container)

        quadro.pack(
            fill="x",
            pady=(0, 10),
        )

        ttk.Button(
            quadro,
            text="Processar JSON",
            command=self.processar,
            width=18,
        ).pack(
            side="right",
        )

        ttk.Button(
            quadro,
            text="Abrir pasta de saída",
            command=self.abrir_pasta_saida,
        ).pack(
            side="right",
            padx=(0, 8),
        )

    def criar_barra_status(
        self,
        container: ttk.Frame,
    ) -> None:
        separador = ttk.Separator(
            container,
            orient="horizontal",
        )

        separador.pack(
            fill="x",
            pady=(0, 8),
        )

        ttk.Label(
            container,
            textvariable=self.status,
            style="Status.TLabel",
        ).pack(
            anchor="w",
        )

    def atualizar_saida_automatica_por_modo(self) -> None:
        entrada = self.arquivo_entrada.get().strip()

        if not entrada:
            return

        if (
            not self.saida_automatica
            and self.arquivo_saida.get().strip()
        ):
            return

        self.saida_automatica = True
        self.arquivo_saida.set(
            nome_saida_por_entrada(
                entrada,
                self.modo.get(),
            )
        )

    def selecionar_arquivo_entrada(self) -> None:
        caminho = filedialog.askopenfilename(
            title="Selecionar JSON de entrada",
            initialdir=PASTA_ENTRADA_PADRAO,
            filetypes=[
                ("Arquivos JSON", "*.json"),
                ("Todos os arquivos", "*.*"),
            ],
        )

        if caminho:
            self.arquivo_entrada.set(
                formatar_caminho_interface(caminho)
            )
            self.saida_automatica = True
            self.atualizar_saida_automatica_por_modo()

    def selecionar_arquivo_saida(self) -> None:
        entrada = self.arquivo_entrada.get().strip()

        if entrada:
            saida_sugerida = nome_saida_por_entrada(
                entrada,
                self.modo.get(),
            )
            pasta_inicial = os.path.dirname(saida_sugerida)
            arquivo_inicial = os.path.basename(saida_sugerida)
        else:
            pasta_inicial = PASTA_SAIDA_PADRAO
            arquivo_inicial = NOME_ARQUIVO_SAIDA_PADRAO

        caminho = filedialog.asksaveasfilename(
            title="Selecionar arquivo de saída",
            initialdir=pasta_inicial,
            initialfile=arquivo_inicial,
            defaultextension=".json",
            filetypes=[
                ("Arquivos JSON", "*.json"),
                ("Todos os arquivos", "*.*"),
            ],
        )

        if caminho:
            self.saida_automatica = False
            self.arquivo_saida.set(
                formatar_caminho_interface(caminho)
            )

    def adicionar_condicao_por_enter(
        self,
        _evento=None,
    ) -> None:
        if self.campo_condicao.focus_get() == self.campo_condicao:
            self.adicionar_condicao()

    def obter_condicoes(self) -> list[str]:
        return list(
            self.lista_condicoes.get(
                0,
                tk.END,
            )
        )

    def adicionar_condicao(self) -> None:
        condicao = self.condicao_digitada.get().strip()

        if not condicao:
            messagebox.showwarning(
                TITULO_APLICACAO,
                "Digite uma condição antes de adicionar.",
                parent=self,
            )
            self.campo_condicao.focus_set()
            return

        condicoes = self.obter_condicoes()

        if condicao in condicoes:
            messagebox.showwarning(
                TITULO_APLICACAO,
                "Essa condição já foi adicionada.",
                parent=self,
            )
            return

        self.lista_condicoes.insert(
            tk.END,
            condicao,
        )

        self.condicao_digitada.set("")
        self.campo_condicao.focus_set()

        self.status.set(
            f'Condição "{condicao}" adicionada.'
        )

    def editar_condicao(self) -> None:
        selecao = self.lista_condicoes.curselection()

        if not selecao:
            messagebox.showwarning(
                TITULO_APLICACAO,
                "Selecione uma condição para editar.",
                parent=self,
            )
            return

        indice = selecao[0]
        valor_atual = self.lista_condicoes.get(indice)

        janela = tk.Toplevel(self)
        janela.title("Editar condição")
        janela.resizable(False, False)
        janela.transient(self)
        janela.grab_set()

        janela.columnconfigure(
            0,
            weight=1,
        )

        ttk.Label(
            janela,
            text="Novo valor da condição:",
        ).grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="w",
            padx=14,
            pady=(14, 6),
        )

        variavel = tk.StringVar(
            value=valor_atual
        )

        campo = ttk.Entry(
            janela,
            textvariable=variavel,
            width=48,
        )

        campo.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=14,
        )

        def confirmar() -> None:
            novo_valor = variavel.get().strip()

            if not novo_valor:
                messagebox.showwarning(
                    "Editar condição",
                    "A condição não pode ficar vazia.",
                    parent=janela,
                )
                return

            condicoes = self.obter_condicoes()

            if (
                novo_valor in condicoes
                and novo_valor != valor_atual
            ):
                messagebox.showwarning(
                    "Editar condição",
                    "Essa condição já existe.",
                    parent=janela,
                )
                return

            self.lista_condicoes.delete(indice)
            self.lista_condicoes.insert(
                indice,
                novo_valor,
            )

            self.lista_condicoes.selection_set(indice)

            self.status.set(
                f'Condição alterada para "{novo_valor}".'
            )

            janela.destroy()

        ttk.Button(
            janela,
            text="Cancelar",
            command=janela.destroy,
        ).grid(
            row=2,
            column=0,
            sticky="e",
            padx=(14, 4),
            pady=14,
        )

        ttk.Button(
            janela,
            text="Salvar",
            command=confirmar,
        ).grid(
            row=2,
            column=1,
            sticky="w",
            padx=(4, 14),
            pady=14,
        )

        campo.bind(
            "<Return>",
            lambda _evento: confirmar(),
        )

        janela.update_idletasks()

        largura = janela.winfo_width()
        altura = janela.winfo_height()

        x = self.winfo_x() + (
            self.winfo_width() - largura
        ) // 2

        y = self.winfo_y() + (
            self.winfo_height() - altura
        ) // 2

        janela.geometry(
            f"+{max(x, 0)}+{max(y, 0)}"
        )

        campo.select_range(
            0,
            tk.END,
        )

        campo.focus_set()

    def remover_condicao(self) -> None:
        selecao = self.lista_condicoes.curselection()

        if not selecao:
            messagebox.showwarning(
                TITULO_APLICACAO,
                "Selecione uma condição para remover.",
                parent=self,
            )
            return

        indice = selecao[0]
        condicao = self.lista_condicoes.get(indice)

        confirmar = messagebox.askyesno(
            TITULO_APLICACAO,
            f'Deseja remover a condição "{condicao}"?',
            parent=self,
        )

        if confirmar:
            self.lista_condicoes.delete(indice)

            self.status.set(
                f'Condição "{condicao}" removida.'
            )

    def limpar_condicoes(self) -> None:
        if self.lista_condicoes.size() == 0:
            return

        confirmar = messagebox.askyesno(
            TITULO_APLICACAO,
            "Deseja remover todas as condições cadastradas?",
            parent=self,
        )

        if confirmar:
            self.lista_condicoes.delete(
                0,
                tk.END,
            )

            self.status.set(
                "Todas as condições foram removidas."
            )

    def validar_dados(self) -> tuple[str, str, list[str]]:
        entrada = self.arquivo_entrada.get().strip()
        saida = self.arquivo_saida.get().strip()
        condicoes = self.obter_condicoes()

        if not entrada:
            raise ValueError(
                "Selecione o arquivo JSON de entrada."
            )

        if not os.path.isfile(entrada):
            raise FileNotFoundError(
                f"Arquivo de entrada não encontrado:\n{entrada}"
            )

        if not saida:
            raise ValueError(
                "Selecione o arquivo JSON de saída."
            )

        if not condicoes:
            raise ValueError(
                "Adicione pelo menos uma condição de pesquisa."
            )

        if os.path.abspath(entrada) == os.path.abspath(saida):
            raise ValueError(
                "O arquivo de saída não pode ser o mesmo "
                "arquivo de entrada."
            )

        return entrada, saida, condicoes

    def processar(self) -> None:
        try:
            entrada, saida, condicoes = self.validar_dados()
            modo_atual = self.modo.get()

            self.status.set(
                "Lendo e processando o arquivo..."
            )

            self.update_idletasks()

            with open(
                entrada,
                "r",
                encoding="utf-8-sig",
            ) as arquivo:
                texto_json = arquivo.read()

            inicio_data_points = localizar_inicio_datapoints(
                texto_json
            )

            datapoints = extrair_datapoints(
                texto_json,
                inicio_data_points,
            )

            if not datapoints:
                raise ValueError(
                    "Nenhum datapoint foi encontrado "
                    "dentro da lista dataPoints."
                )

            resultado = filtrar_datapoints(
                datapoints,
                condicoes,
                modo_atual,
                self.diferenciar_maiusculas.get(),
            )

            invalidos = validar_blocos_json(
                resultado.datapoints_saida
            )

            if invalidos:
                indice, xid, erro = invalidos[0]
                rotulo_datapoint = (
                    "mantido"
                    if modo_atual == "excluir"
                    else "filtrado"
                )

                raise ValueError(
                    "O arquivo de saida nao foi gerado porque "
                    f"pelo menos um datapoint {rotulo_datapoint} nao e um "
                    "objeto JSON valido.\n\n"
                    f"Datapoint {rotulo_datapoint} numero: {indice}\n"
                    f"XID: {xid}\n"
                    f"Erro: {erro}"
                )

            gravar_json_saida(
                saida,
                resultado.datapoints_saida,
            )

            total = len(datapoints)
            correspondentes = len(
                resultado.datapoints_correspondentes
            )

            gravados = len(
                resultado.datapoints_saida
            )

            removidos = total - gravados

            percentual = (
                gravados / total * 100
                if total
                else 0
            )

            modo_texto = (
                "Incluir correspondentes"
                if modo_atual == "incluir"
                else "Excluir correspondentes"
            )

            linhas_condicoes = []

            for condicao in condicoes:
                quantidade = (
                    resultado
                    .ocorrencias_por_condicao[
                        condicao
                    ]
                )

                linhas_condicoes.append(
                    f"• {condicao}: {quantidade}"
                )

            resumo = (
                f"Modo: {modo_texto}\n\n"
                f"Datapoints analisados: {total}\n"
                f"Datapoints correspondentes: {correspondentes}\n"
                f"Datapoints gravados: {gravados}\n"
                f"Datapoints removidos: {removidos}\n"
                f"Percentual mantido: {percentual:.2f}%\n\n"
                "Ocorrências por condição:\n"
                + "\n".join(linhas_condicoes)
                + f"\n\nArquivo gerado:\n{saida}"
            )

            self.status.set(
                f"Processamento concluído. "
                f"{gravados} datapoints gravados."
            )

            messagebox.showinfo(
                "Processamento concluído",
                resumo,
                parent=self,
            )

        except (
            FileNotFoundError,
            ValueError,
            OSError,
        ) as erro:
            self.status.set(
                "Falha no processamento."
            )

            messagebox.showerror(
                "Erro",
                str(erro),
                parent=self,
            )

        except Exception as erro:
            self.status.set(
                "Ocorreu um erro inesperado."
            )

            messagebox.showerror(
                "Erro inesperado",
                f"Ocorreu um erro inesperado:\n\n{erro}",
                parent=self,
            )

    def abrir_pasta_saida(self) -> None:
        caminho_saida = self.arquivo_saida.get().strip()

        if caminho_saida:
            pasta = os.path.dirname(
                os.path.abspath(caminho_saida)
            )
        else:
            pasta = PASTA_SAIDA_PADRAO

        os.makedirs(
            pasta,
            exist_ok=True,
        )

        try:
            os.startfile(pasta)

        except AttributeError:
            messagebox.showinfo(
                TITULO_APLICACAO,
                f"Pasta de saída:\n{pasta}",
                parent=self,
            )

        except OSError as erro:
            messagebox.showerror(
                TITULO_APLICACAO,
                f"Não foi possível abrir a pasta:\n{erro}",
                parent=self,
            )

    def fechar_aplicacao(self) -> None:
        confirmar = messagebox.askyesno(
            TITULO_APLICACAO,
            "Deseja fechar a aplicação?",
            parent=self,
        )

        if confirmar:
            self.destroy()


def main() -> None:
    os.makedirs(
        PASTA_ENTRADA_PADRAO,
        exist_ok=True,
    )

    os.makedirs(
        PASTA_SAIDA_PADRAO,
        exist_ok=True,
    )

    aplicacao = AplicacaoParticionador()
    aplicacao.mainloop()


if __name__ == "__main__":
    main()
