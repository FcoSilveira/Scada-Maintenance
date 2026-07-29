# Auditoria de Escritas - Owen Cloud

Este projeto executa uma auditoria de escritas de datapoints no formato Owen Cloud. Ele analisa um arquivo CSV de escritas e um arquivo JSON de configuração, gera um relatório Excel e um JSON para análise dos registros que ultrapassam o limite esperado.

## Estrutura do projeto

- `relatorioInsert.py`: script principal que realiza a leitura, análise e exportação dos resultados.
- `entrada/entrada.json`: arquivo JSON de entrada com a lista de datapoints (`dataPoints`).
- `entrada/escritas.csv`: arquivo CSV com os registros de escritas esperados.
- `saida/`: pasta de saída onde são gerados os arquivos:
  - `relatorio_escritas.xlsx`
  - `jsonAnalise.json`
- `consulta.txt`: arquivo auxiliar com uma consulta SQL de exemplo (não é usado pelo script).

## Requisitos

- Python 3.8+ recomendado
- Dependências do Python listadas em `requirements.txt`

## Como funciona o script

1. O script lê `entrada/escritas.csv` usando pandas.
2. Ele valida se a coluna `xid` está presente no CSV.
3. Conta quantas vezes cada `xid` aparece no CSV.
4. Lê `entrada/entrada.json` e obtém a lista de `dataPoints`.
5. Para cada datapoint, compara a quantidade de escritas ao valor máximo esperado (`LIMITE = 2`).
6. Define o `Status` do datapoint:
   - `OK`: se a quantidade estiver dentro do limite.
   - `BINÁRIO`: se ultrapassar o limite, mas o datapoint for do tipo `BINARY`.
   - `VERIFICAR`: se ultrapassar o limite e não for `BINARY`.
7. Gera um arquivo Excel com três abas:
   - `Resumo`
   - `Todos`
   - `Necessitam Analise`
8. Gera o arquivo `saida/jsonAnalise.json` com os datapoints que precisam de análise.
9. Exibe um resumo final no terminal.

## Passo a passo para usar

1. Instale o Python 3.8+.
2. Abra o terminal na pasta do projeto (`INSERT`).
3. Instale as dependências:

```bash
python -m pip install -r ./docs/requirements.txt
```

4. Verifique se os arquivos estão em:
   - `entrada/escritas.csv`
   - `entrada/entrada.json`

5. Execute o script:

```bash
python relatorioInsert.py
```

6. Após a execução, verifique os arquivos de saída em `saida/`:
   - `relatorio_escritas.xlsx`
   - `jsonAnalise.json`

## Observações

- O CSV deve usar ponto e vírgula (`;`) como separador de campo.
- O CSV deve conter, no mínimo, a coluna `xid`.
- O limite de escritas por datapoint é configurado pela variável `LIMITE` no script.
- Datapoints do tipo `BINARY` com escrita acima do limite são ignorados automaticamente e marcados como `BINÁRIO`.

## Dependências

Veja `requirements.txt` para os pacotes Python usados pelo script.
