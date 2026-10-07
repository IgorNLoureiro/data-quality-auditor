import argparse
import os
import shutil
from pathlib import Path

import pyodbc
import yaml
from dotenv import load_dotenv

# ============================================================
# CONFIGURAÇÃO
# ============================================================

load_dotenv()

HOST = os.getenv("SQLSERVER_HOST")
PORT = os.getenv("SQLSERVER_PORT", "1433")
DATABASE = os.getenv("SQLSERVER_DATABASE")
USER = os.getenv("SQLSERVER_USER")
PASSWORD = os.getenv("SQLSERVER_PASSWORD")
SCHEMA = os.getenv("SQLSERVER_SCHEMA", "dbo")

OUTPUT_DIR = Path("checks/generated")

TEXT_TYPES = {
    "varchar",
    "nvarchar",
    "char",
    "nchar",
    "text",
    "ntext",
}


# ============================================================
# VALIDAÇÃO DAS VARIÁVEIS
# ============================================================

def validate_environment():
    """
    Verifica se todas as variáveis necessárias existem.
    """

    required = {
        "SQLSERVER_HOST": HOST,
        "SQLSERVER_DATABASE": DATABASE,
        "SQLSERVER_USER": USER,
        "SQLSERVER_PASSWORD": PASSWORD,
        "SQLSERVER_SCHEMA": SCHEMA,
    }

    missing = [
        name
        for name, value in required.items()
        if not value
    ]

    if missing:
        raise RuntimeError(
            "Variáveis de ambiente ausentes: "
            + ", ".join(missing)
        )


# ============================================================
# CONEXÃO
# ============================================================

def get_connection():
    """
    Cria uma conexão com o SQL Server.
    """

    connection_string = (
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={HOST},{PORT};"
        f"DATABASE={DATABASE};"
        f"UID={USER};"
        f"PWD={PASSWORD};"
        "Encrypt=yes;"
        "TrustServerCertificate=yes;"
    )

    return pyodbc.connect(connection_string)


# ============================================================
# METADATA
# ============================================================

def get_columns(connection):
    """
    Obtém todas as tabelas e colunas do schema configurado.
    """

    query = """
        SELECT
            TABLE_SCHEMA,
            TABLE_NAME,
            COLUMN_NAME,
            DATA_TYPE,
            ORDINAL_POSITION
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = ?
        ORDER BY
            TABLE_NAME,
            ORDINAL_POSITION;
    """

    cursor = connection.cursor()
    cursor.execute(query, SCHEMA)

    tables = {}

    for row in cursor.fetchall():

        table_key = (
            row.TABLE_SCHEMA,
            row.TABLE_NAME,
        )

        tables.setdefault(
            table_key,
            [],
        ).append(
            {
                "name": row.COLUMN_NAME,
                "data_type": row.DATA_TYPE.lower(),
                "ordinal": row.ORDINAL_POSITION,
            }
        )

    return tables


# ============================================================
# IDENTIFICADORES SQL SERVER
# ============================================================

def quote_identifier(value):
    """
    Escapa um identificador para SQL Server.

    Exemplo:

        customer -> [customer]
    """

    return "[" + value.replace("]", "]]") + "]"


# ============================================================
# SQL PARA DUPLICIDADE DE LINHAS
# ============================================================

def build_duplicate_row_condition(columns):
    """
    Cria uma condição SQL que identifica linhas
    completamente duplicadas.

    Exemplo:

        col1
        col2
        col3

    será transformado conceitualmente em:

        EXISTS (
            SELECT 1
            FROM tabela t2
            WHERE
                t2.col1 = col1
                AND t2.col2 = col2
                AND t2.col3 = col3
            GROUP BY ...
            HAVING COUNT(*) > 1
        )

    A comparação trata NULL explicitamente para que duas
    linhas com NULL na mesma posição também sejam consideradas
    iguais.
    """

    comparisons = []

    for column in columns:

        col = quote_identifier(column["name"])

        comparisons.append(
            f"""
            (
                t2.{col} = t1.{col}
                OR (
                    t2.{col} IS NULL
                    AND t1.{col} IS NULL
                )
            )
            """.strip()
        )

    return "\nAND ".join(comparisons)


def build_duplicate_rows_sql(schema, table, columns):
    """
    Gera a consulta SQL usada pelo Soda para encontrar
    linhas completamente duplicadas.
    """

    quoted_schema = quote_identifier(schema)
    quoted_table = quote_identifier(table)

    conditions = build_duplicate_row_condition(
        columns
    )

    return f"""
        SELECT 1
        FROM {quoted_schema}.{quoted_table} t1
        WHERE EXISTS (
            SELECT 1
            FROM {quoted_schema}.{quoted_table} t2
            WHERE
                {conditions}
            GROUP BY
                {", ".join(
                    "t2." + quote_identifier(c["name"])
                    for c in columns
                )}
            HAVING COUNT(*) > 1
        )
    """.strip()


# ============================================================
# CHECK DE NULL
# ============================================================

def build_missing_checks(columns):
    """
    Gera um check de NULL para TODAS as colunas.
    """

    checks = []

    for column in columns:

        name = column["name"]

        checks.append(
            f"  - missing_count({name}) = 0"
        )

    return checks


# ============================================================
# CHECK DE VAZIO
# ============================================================

def build_empty_checks(columns):
    """
    Gera checks de string vazia/branca apenas para
    colunas textuais.

    NULL não é tratado aqui porque existe um check
    específico para NULL.
    """

    checks = []

    for column in columns:

        if column["data_type"] not in TEXT_TYPES:
            continue

        name = column["name"]

        condition = (
            f"{quote_identifier(name)} IS NOT NULL "
            f"AND LTRIM(RTRIM({quote_identifier(name)})) = ''"
        )

        checks.append(
            "  - failed rows:"
        )

        checks.append(
            f"      name: {name} não pode estar vazio"
        )

        checks.append(
            f'      fail condition: "{condition}"'
        )

    return checks


# ============================================================
# CHECK DE LINHA DUPLICADA
# ============================================================

def build_duplicate_row_check(schema, table, columns):
    """
    Cria o check Soda que procura linhas inteiras duplicadas.
    """

    sql = build_duplicate_rows_sql(
        schema,
        table,
        columns,
    )

    return [
        "  - failed rows:",
        "      name: Não podem existir linhas completamente duplicadas",
        "      fail query: |",
        *[
            f"        {line}"
            for line in sql.splitlines()
        ],
    ]


# ============================================================
# GERA YAML
# ============================================================

def generate_yaml(schema, table, columns):
    """
    Gera o arquivo SodaCL completo de uma tabela.
    """

    lines = []

    dataset = table

    lines.append(
        f"checks for {dataset}:"
    )

    lines.append("")

    # --------------------------------------------------------
    # NULL
    # --------------------------------------------------------

    lines.extend(
        build_missing_checks(columns)
    )

    lines.append("")

    # --------------------------------------------------------
    # VAZIOS
    # --------------------------------------------------------

    empty_checks = build_empty_checks(columns)

    if empty_checks:
        lines.extend(empty_checks)
        lines.append("")

    # --------------------------------------------------------
    # LINHAS DUPLICADAS
    # --------------------------------------------------------

    lines.extend(
        build_duplicate_row_check(
            schema,
            table,
            columns,
        )
    )

    lines.append("")

    return "\n".join(lines)


# ============================================================
# LIMPEZA DOS ARQUIVOS GERADOS
# ============================================================

def clean_output_directory():
    """
    Remove completamente a pasta de checks gerados.

    Como os arquivos são derivados exclusivamente do metadata
    atual do banco, é seguro recriá-los a cada execução.
    """

    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


# ============================================================
# DRY RUN
# ============================================================

def print_dry_run(schema, table, columns):
    """
    Mostra no terminal quais checks seriam gerados.
    """

    print()
    print("=" * 70)
    print(f"TABELA: {schema}.{table}")
    print("=" * 70)

    print(
        f"Colunas encontradas: {len(columns)}"
    )

    print("\nChecks:")

    print(
        f"  - NULL: {len(columns)} colunas"
    )

    text_columns = [
        c for c in columns
        if c["data_type"] in TEXT_TYPES
    ]

    print(
        f"  - vazio: {len(text_columns)} colunas"
    )

    print(
        "  - linhas duplicadas: 1 check"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Gera checks SodaCL automaticamente "
            "para SQL Server."
        )
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Mostra os checks sem criar os arquivos.",
    )

    args = parser.parse_args()

    print()
    print("=" * 70)
    print("SODA - DATA QUALITY CHECK GENERATOR")
    print("=" * 70)

    validate_environment()

    print("\nConectando ao SQL Server...")

    connection = get_connection()

    try:

        print("Lendo metadata...")

        tables = get_columns(
            connection
        )

        print(
            f"Tabelas encontradas: {len(tables)}"
        )

        if args.dry_run:

            for (schema, table), columns in tables.items():

                print_dry_run(
                    schema,
                    table,
                    columns,
                )

            print()
            print(
                "DRY RUN concluído. Nenhum arquivo foi criado."
            )

            return

        clean_output_directory()

        generated = 0

        for (schema, table), columns in tables.items():

            content = generate_yaml(
                schema,
                table,
                columns,
            )

            filename = (
                f"{schema}_{table}.yml"
            )

            output_file = (
                OUTPUT_DIR / filename
            )

            output_file.write_text(
                content,
                encoding="utf-8",
            )

            generated += 1

            print(
                f"  ✓ {schema}.{table} "
                f"({len(columns)} colunas)"
            )

        print()
        print("=" * 70)
        print("GERAÇÃO CONCLUÍDA")
        print("=" * 70)

        print(
            f"Tabelas processadas: {generated}"
        )

        print(
            f"Diretório: {OUTPUT_DIR}"
        )

    finally:

        connection.close()


if __name__ == "__main__":
    main()


