# Analisador de Scripts Scada-LTS

Projeto em Python para localizar Meta Data Points e outros elementos com scripts JavaScript potencialmente responsáveis por erros `ReferenceError` registrados no `mango.log`.

## Instalação

```bash
python -m pip install -r requirements.txt
```

## Execução

```bash
python app.py
```

ou:

```bash
python app.py --log entrada/mango.log --json entrada/entrada.json
```

## Entrada

```text
entrada/mango.log
entrada/entrada.json
```

## Saída

```text
saida/relatorio_datapoints.txt
```


## Datapoints confirmados

Os datapoints classificados como `CONFIRMADO` são reunidos em:

```text
saida/datapoints_confirmados.json
```

O arquivo é formatado com indentação padronizada e preserva integralmente:

```json
"discardHighLimit": 1.7976931348623157E308,
"discardLowLimit": -1.7976931348623157E308
```
