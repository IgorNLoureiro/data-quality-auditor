# Soda Data Quality Checks para SQL Server

Projeto em Python que **gera automaticamente checks de qualidade de dados** (formato SodaCL) a partir da estrutura das tabelas de um banco SQL Server e depois **executa esses checks** usando o [Soda Core](https://docs.soda.io/).

Você aponta o projeto para um banco, ele lê as tabelas e colunas do schema configurado, cria um arquivo de checks por tabela e roda tudo, mostrando o que passou e o que falhou.

---

## O que o projeto verifica

Para cada tabela encontrada no schema, são gerados três tipos de check:

| Check | Aplicado em | O que faz |
|---|---|---|
| **Valores nulos** | Todas as colunas | Falha se existir qualquer `NULL` (`missing_count(coluna) = 0`) |
| **Valores vazios** | Apenas colunas de texto (`varchar`, `nvarchar`, `char`, `nchar`, `text`, `ntext`) | Falha se existir texto vazio ou só com espaços (`''`). `NULL` não é tratado aqui, porque já tem o check acima |
| **Linhas duplicadas** | Tabela inteira | Falha se existir alguma linha completamente idêntica a outra (considerando `NULL` igual a `NULL`) |

Um check com `FAILED` **não é erro do programa**: significa que o Soda encontrou um dado fora do esperado na tabela.

---

## Estrutura do projeto

```
.
├── checks/
│   └── generated/          # YAMLs gerados (não vai para o git)
├── scripts/
│   ├── generate_checks.py  # Lê o banco e gera os checks
│   └── run_checks.py       # Executa os checks com o Soda
├── configuration.yml       # Conexão do Soda com o SQL Server
├── requirements.txt
├── .env                    # Suas credenciais (não vai para o git)
├── .env.example            # Modelo do .env
└── .gitignore
```

---

## Como funciona

1. **`generate_checks.py`** conecta no SQL Server, consulta o `INFORMATION_SCHEMA.COLUMNS` do schema configurado e escreve um arquivo `.yml` por tabela em `checks/generated/` (por exemplo, `dbo_Funcionarios.yml`). A pasta é apagada e recriada a cada execução, porque os arquivos são derivados do banco atual.
2. **`run_checks.py`** percorre os arquivos de `checks/generated/` e chama o comando `soda scan` para cada um, usando o `configuration.yml` para conectar.
3. O Soda imprime o resumo com cada check como `PASSED` ou `FAILED`. Se algum arquivo tiver falhas, o script termina com código de erro (útil para pipelines).

O schema vem do `configuration.yml` (variável `SQLSERVER_SCHEMA`). Por isso o cabeçalho dos checks usa só o nome da tabela (`checks for Funcionarios:`), sem o `dbo.`.

---

## Pré-requisitos

- **Python 3.10 ou superior**
- **ODBC Driver 18 for SQL Server** instalado na máquina ([download da Microsoft](https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server))
- Acesso a um banco **SQL Server** (usuário, senha, host e porta)

---

## Instalação

### 1. Clone o repositório

```powershell
git clone <url-do-repositorio>
cd <pasta-do-projeto>
```

### 2. Crie e ative um ambiente virtual

Windows (PowerShell):

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

Linux/macOS:

```bash
python -m venv venv
source venv/bin/activate
```

O prompt deve passar a mostrar `(venv)`.

### 3. Instale as dependências

```powershell
pip install -r requirements.txt
```

O `requirements.txt` do projeto:

```
soda-core-sqlserver==3.5.6
setuptools
pyodbc
python-dotenv
pyyaml
```

> **Atenção à versão do Soda.** Este projeto usa a **Soda v3** (comando `soda scan`). O pacote da v3 se chama `soda-core-sqlserver`. Não use `soda-sqlserver`, que é a **v4** e tem comandos diferentes. O `setuptools` é necessário porque a Soda v3 depende do `distutils`, removido do Python 3.12 em diante.

### 4. Configure as credenciais

Copie o modelo e preencha com os dados do seu banco:

```powershell
copy .env.example .env
```

Conteúdo do `.env`:

```
SQLSERVER_HOST=localhost
SQLSERVER_PORT=1433
SQLSERVER_DATABASE=seu_banco
SQLSERVER_USER=seu_usuario
SQLSERVER_PASSWORD=sua_senha
SQLSERVER_SCHEMA=dbo
```


O arquivo `configuration.yml` não precisa de edição: ele lê essas mesmas variáveis.

```yaml
data_source sqlserver:
  type: sqlserver

  host: ${SQLSERVER_HOST}
  port: ${SQLSERVER_PORT}

  username: ${SQLSERVER_USER}
  password: ${SQLSERVER_PASSWORD}

  database: ${SQLSERVER_DATABASE}
  schema: ${SQLSERVER_SCHEMA}

  driver: ODBC Driver 18 for SQL Server

  encrypt: true
  trust_server_certificate: true
```

Na Soda v3, o `${NOME}` é lido das **variáveis de ambiente**. Não use prefixo `env.`. Como o `soda scan` roda em um processo separado, as variáveis precisam estar disponíveis no ambiente quando o `run_checks.py` executa (carregadas do `.env` pelo próprio script ou definidas na sessão).

Para definir manualmente na sessão do PowerShell:

```powershell
$env:SQLSERVER_HOST = "localhost"
$env:SQLSERVER_PORT = "1433"
$env:SQLSERVER_DATABASE = "seu_banco"
$env:SQLSERVER_USER = "seu_usuario"
$env:SQLSERVER_PASSWORD = "sua_senha"
$env:SQLSERVER_SCHEMA = "dbo"
```

---

## Como usar

### 1. (Opcional) Ver o que seria gerado

```powershell
python scripts/generate_checks.py --dry-run
```

Mostra, para cada tabela, quantas colunas foram encontradas e quantos checks seriam criados. Nenhum arquivo é escrito.

### 2. Gerar os checks

```powershell
python scripts/generate_checks.py
```

Os arquivos aparecem em `checks/generated/`, um por tabela (`<schema>_<tabela>.yml`).

### 3. Executar os checks

Todas as tabelas:

```powershell
python scripts/run_checks.py
```

Somente uma tabela:

```powershell
python scripts/run_checks.py --table dbo_Funcionarios.yml
```

---

## Lendo o resultado

Exemplo de saída:

```
13/16 checks PASSED
3/16 checks FAILED:
  Departamento não pode estar vazio [FAILED]
    check_value: 1
  Não podem existir linhas completamente duplicadas [FAILED]
    value: 2
  missing_count(Idade) = 0 [FAILED]
    check_value: 1
```

- **`missing_count(Idade) = 0` com `check_value: 1`**: existe 1 linha com `Idade` nula.
- **`Departamento não pode estar vazio` com `check_value: 1`**: existe 1 linha com `Departamento` vazio ou só com espaços.
- **Linhas duplicadas com `value: 2`**: o valor é a quantidade de linhas que têm uma cópia idêntica. 2 normalmente indica 1 par de registros iguais.

Para ver as linhas problemáticas no SQL Server:

```sql
SELECT * FROM dbo.Funcionarios WHERE Idade IS NULL;

SELECT * FROM dbo.Funcionarios
WHERE Departamento IS NOT NULL AND LTRIM(RTRIM(Departamento)) = '';

SELECT Nome, Sobrenome, Idade, Cpf, Fone, Cep, Departamento, Funcao, COUNT(*) AS qtd
FROM dbo.Funcionarios
GROUP BY Nome, Sobrenome, Idade, Cpf, Fone, Cep, Departamento, Funcao
HAVING COUNT(*) > 1;
```

---

## Problemas comuns

| Mensagem | Causa | Solução |
|---|---|---|
| `Soda v3 commands are not supported (Soda v4 was run)` | Soda v4 instalada | Troque `soda-sqlserver` por `soda-core-sqlserver` no `requirements.txt` e reinstale em um venv limpo |
| `No module named 'distutils'` | Python 3.12+ sem `distutils` | `pip install setuptools` |
| `Python não foi encontrado` | Atalho da Microsoft Store no lugar do Python | Use `py -m venv venv` ou instale o Python pelo python.org |
| `'env' is undefined` | `${env.VARIAVEL}` no `configuration.yml` | Use `${VARIAVEL}`, sem o `env.` |
| `Variáveis de ambiente ausentes` | `.env` não existe ou está incompleto | Copie o `.env.example` e preencha todos os campos |
| `Data source not found` ou erro de conexão | Variáveis não chegaram ao `soda scan` ou dados incorretos | Confira o `.env` e se o SQL Server aceita conexão no host e na porta informados |
| `YAML syntax error` com `[` | Valor começando com `[` sem aspas no YAML gerado | O `fail condition` dos checks de vazio deve ficar entre aspas duplas (o gerador já faz isso) |
| `FROM dbo.dbo.Tabela` na query | Schema duplicado no cabeçalho dos checks | O cabeçalho deve ser `checks for Tabela:`, sem o schema |
| `ODBC Driver 18 ... not found` | Driver não instalado | Instale o ODBC Driver 18 for SQL Server |

---

## Próximos passos

Ideias para evoluir o projeto:

- Checks de regra de negócio (por exemplo, `Idade` entre 14 e 100, CPF com 11 dígitos)
- Checks de chave única em colunas específicas
- Checks de frescor de dados em colunas de data
- Rodar os checks automaticamente em um pipeline (CI)

---

## Tecnologias

- Python
- [Soda Core 3.5.6](https://docs.soda.io/soda-core/overview-main.html)
- SQL Server + pyodbc
- python-dotenv e PyYAML
