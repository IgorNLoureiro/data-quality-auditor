import argparse
import subprocess
import sys
from pathlib import Path


CHECKS_DIR = Path("checks/generated")


def main():

    parser = argparse.ArgumentParser(
        description="Executa os checks Soda gerados."
    )

    parser.add_argument(
        "--table",
        help=(
            "Executa somente o YAML informado. "
            "Exemplo: dbo_customers.yml"
        ),
    )

    args = parser.parse_args()

    if not CHECKS_DIR.exists():
        print(
            "Diretório de checks não existe:"
            f" {CHECKS_DIR}"
        )

        sys.exit(1)

    if args.table:

        files = [
            CHECKS_DIR / args.table
        ]

    else:

        files = sorted(
            CHECKS_DIR.glob("*.yml")
        )

    if not files:

        print(
            "Nenhum arquivo YAML encontrado."
        )

        sys.exit(1)

    failed = []

    print("=" * 70)
    print("SODA - DATA QUALITY SCAN")
    print("=" * 70)

    for file in files:

        if not file.exists():

            print(
                f"\nArquivo não encontrado: {file}"
            )

            failed.append(file)

            continue

        print()
        print("-" * 70)
        print(f"Executando: {file.name}")
        print("-" * 70)

        result = subprocess.run(
            [
                "soda",
                "scan",
                "-d",
                "sqlserver",
                "-c",
                "configuration.yml",
                str(file),
            ]
        )

        if result.returncode != 0:
            failed.append(file)

    print()
    print("=" * 70)
    print("RESULTADO FINAL")
    print("=" * 70)

    if failed:

        print(
            f"\n❌ {len(failed)} arquivo(s) apresentou/apresentaram falha:"
        )

        for file in failed:
            print(f"   - {file.name}")

        sys.exit(1)

    print(
        f"\n✅ {len(files)} tabela(s) processada(s) com sucesso."
    )


if __name__ == "__main__":
    main()
