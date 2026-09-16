# -*- coding: utf-8 -*-
"""
Backup dos arquivos de dado brutos (não código, por isso nunca entram no
Git -- ver .gitignore) que alimentam o dashboard: DADOS*.xlsx, BASE
CADASTRO*.xlsx, perdas*.xls(x), faturamento.csv, itens a vencer*.xls(x),
regionais.csv.

Diferente do monitor-precos (banco SQLite reescrito a cada 30min pelo
robô), esses arquivos ficam parados a maior parte do tempo -- o Gabriel
só substitui na mão de vez em quando. Ainda assim, é a única cópia (só
existe nessa pasta, nada versionado), então vale ter uma cópia de
segurança separada mesmo com risco menor de sync "nunca fechar".

Uso manual:
    python backup_dados.py

Mantém só os 5 backups mais recentes (cada rodada pode passar de 140MB
no total, guardar 10 como o monitor-precos ficaria pesado demais)."""
from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

MANTER_ULTIMAS_RODADAS = 5

PASTA_PROJETO = Path(__file__).resolve().parent
PASTA_BACKUPS = PASTA_PROJETO.parent / "BACKUPS DB" / "PERDAS"

PADROES_ARQUIVOS = [
    "DADOS*.xlsx",
    "BASE CADASTRO*.xlsx",
    "perdas*.xls",
    "perdas*.xlsx",
    "faturamento.csv",
    "*itens*a*vencer*.xls*",
    "regionais.csv",
]


def _arquivos_para_copiar() -> list[Path]:
    encontrados: list[Path] = []
    for padrao in PADROES_ARQUIVOS:
        encontrados.extend(sorted(PASTA_PROJETO.glob(padrao)))
    return encontrados


def _limpar_rodadas_antigas():
    # cada rodada é uma subpasta com o carimbo de data/hora -- mantém só
    # as N mais recentes, apaga o resto inteiro.
    rodadas = sorted(
        (p for p in PASTA_BACKUPS.iterdir() if p.is_dir()),
        key=lambda p: p.stat().st_mtime, reverse=True,
    )
    for antiga in rodadas[MANTER_ULTIMAS_RODADAS:]:
        shutil.rmtree(antiga)
        print(f"removida rodada antiga: {antiga.name}")


def main():
    arquivos = _arquivos_para_copiar()
    if not arquivos:
        print("Nenhum arquivo de dado encontrado (nenhum dos padrões esperados na pasta) -- nada pra copiar.")
        return 1

    carimbo = datetime.now().strftime("%Y-%m-%d_%Hh%M")
    destino_rodada = PASTA_BACKUPS / carimbo
    destino_rodada.mkdir(parents=True, exist_ok=True)

    total_mb = 0.0
    for origem in arquivos:
        destino = destino_rodada / origem.name
        shutil.copy2(origem, destino)
        tamanho_mb = destino.stat().st_size / (1024 * 1024)
        total_mb += tamanho_mb
        print(f"  {origem.name} ({tamanho_mb:.1f} MB)")

    print(f"\nBackup criado em: {destino_rodada} ({total_mb:.1f} MB total, {len(arquivos)} arquivo(s))")
    _limpar_rodadas_antigas()
    return 0


if __name__ == "__main__":
    sys.exit(main())
