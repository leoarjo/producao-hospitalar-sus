"""
Carregamento dos CSVs do DATASUS no banco de dados PostgreSQL (IESB).

Os arquivos PRN do TabNet têm formato semiestruturado:
  - Linhas de cabeçalho/metadados até a linha com "Município"
  - Linhas de dados (municípios)
  - Linha de total ao final
  - Rodapé de texto livre

Este script:
  1. Detecta automaticamente o cabeçalho real
  2. Remove as linhas de metadados e rodapé
  3. Faz o melt (wide → long)
  4. Unifica as duas métricas em uma única tabela normalizada
  5. Insere no PostgreSQL (sobrescrevendo dados anteriores)
"""

import os
import re
import sys
import logging
from io import StringIO
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

# ─── Caminhos e conexão ───────────────────────────────────────────────────────
BASE = Path(__file__).parent.parent
PASTA_DADOS = BASE / "dados"

# Carrega .env se existir (desenvolvimento local)
_env_file = BASE / ".env"
if _env_file.exists():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

# Credenciais PostgreSQL via variáveis de ambiente
PG_HOST = os.environ.get("PG_HOST", "")
PG_USER = os.environ.get("PG_USER", "")
PG_PASS = os.environ.get("PG_PASS", "")
PG_DB   = os.environ.get("PG_DB",   "")
PG_PORT = int(os.environ.get("PG_PORT", "5432"))

DB_URL = f"postgresql+psycopg2://{PG_USER}:{PG_PASS}@{PG_HOST}:{PG_PORT}/{PG_DB}"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


# ─── Parser do formato PRN do TabNet ─────────────────────────────────────────

def _limpar_valor(val: str) -> float:
    """Converte strings numéricas no estilo TabNet ('1.234,56' ou '-') para float."""
    v = str(val).strip().strip('"')
    if v in ("", "-", "..."):
        return 0.0
    # Remove separador de milhar e troca vírgula decimal por ponto
    v = v.replace(".", "").replace(",", ".")
    try:
        return float(v)
    except ValueError:
        return 0.0


def parse_tabnet_prn(filepath: Path, encoding: str = "latin1") -> pd.DataFrame:
    """
    Lê um arquivo PRN do TabNet e retorna um DataFrame no formato wide
    (cada coluna é um subgrupo de procedimento, cada linha é um município).
    """
    with open(filepath, encoding=encoding, errors="replace") as f:
        linhas = f.readlines()

    # ── Encontra o índice da linha de cabeçalho ──────────────────────────────
    idx_header = None
    for i, linha in enumerate(linhas):
        # O cabeçalho real começa com a coluna "Município" (com ou sem aspas)
        celula_zero = linha.split(";")[0].strip().strip('"')
        if celula_zero.lower() in ("município", "municipio"):
            idx_header = i
            break

    if idx_header is None:
        raise ValueError(
            f"Cabeçalho 'Município' não encontrado em {filepath.name}. "
            "Verifique se o arquivo foi gerado corretamente pelo robô."
        )

    log.info("Cabeçalho encontrado na linha %d de %s", idx_header + 1, filepath.name)

    # ── Seleciona apenas linhas de dados (até linha em branco ou "Total") ─────
    linhas_dados = []
    for linha in linhas[idx_header:]:
        stripped = linha.strip()
        if not stripped:
            # Linha em branco → início do rodapé
            break
        linhas_dados.append(stripped)

    conteudo = "\n".join(linhas_dados)

    # ── Lê com pandas ─────────────────────────────────────────────────────────
    df = pd.read_csv(
        StringIO(conteudo),
        sep=";",
        encoding="utf-8",
        quotechar='"',
        dtype=str,
    )

    # Remove coluna vazia gerada pelo ";" final (se houver)
    df = df.loc[:, ~df.columns.str.match(r"^Unnamed")]

    # ── Remove linha de Total ─────────────────────────────────────────────────
    primeira_col = df.columns[0]
    df = df[~df[primeira_col].str.strip().str.strip('"').str.lower().isin(["total", ""])]
    df = df.dropna(subset=[primeira_col])

    # ── Separa código e nome do município ─────────────────────────────────────
    # Formato típico: "110001 Alta Floresta D'Oeste"
    df[primeira_col] = df[primeira_col].str.strip().str.strip('"')
    df.insert(0, "municipio_codigo", df[primeira_col].str.extract(r"^(\d+)")[0].fillna(""))
    df.insert(1, "municipio_nome",   df[primeira_col].str.replace(r"^\d+\s*", "", regex=True).str.strip())
    df.drop(columns=[primeira_col], inplace=True)

    log.info(
        "  %d municípios × %d colunas lidas de %s",
        len(df),
        len(df.columns) - 2,
        filepath.name,
    )
    return df


def wide_para_long(df: pd.DataFrame, nome_metrica: str) -> pd.DataFrame:
    """
    Converte o DataFrame wide (municípios × subgrupos) para formato long.
    Exclui a coluna "Total" gerada pelo TabNet (evita dupla contagem).
    Retorna colunas: municipio_codigo, municipio_nome, subgrupo_proced, <nome_metrica>
    """
    id_vars = ["municipio_codigo", "municipio_nome"]

    # Exclui colunas de total geradas pelo TabNet (ex.: "Total", "total")
    value_vars = [
        c for c in df.columns
        if c not in id_vars and c.strip().strip('"').lower() != "total"
    ]

    df_long = df.melt(
        id_vars=id_vars,
        value_vars=value_vars,
        var_name="subgrupo_proced",
        value_name=nome_metrica,
    )

    df_long["subgrupo_proced"] = df_long["subgrupo_proced"].str.strip().str.strip('"')
    df_long[nome_metrica] = df_long[nome_metrica].apply(_limpar_valor)

    return df_long


# ─── DDL da tabela ────────────────────────────────────────────────────────────

DDL_PRODUCAO = """
CREATE TABLE IF NOT EXISTS producao_hospitalar (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    municipio_codigo    TEXT    NOT NULL,
    municipio_nome      TEXT    NOT NULL,
    subgrupo_proced     TEXT    NOT NULL,
    quantidade_aprovada REAL    NOT NULL DEFAULT 0,
    valor_aprovado      REAL    NOT NULL DEFAULT 0
);
"""

DDL_INDICES = [
    "CREATE INDEX IF NOT EXISTS idx_municipio  ON producao_hospitalar (municipio_codigo);",
    "CREATE INDEX IF NOT EXISTS idx_subgrupo   ON producao_hospitalar (subgrupo_proced);",
]


# ─── Conexão com fallback ────────────────────────────────────────────────────

SQLITE_PATH = Path(__file__).parent / "producao_hospitalar.db"


def _conectar_banco():
    """
    Tenta conectar ao PostgreSQL do IESB.
    Se a rede não estiver disponível (ex.: fora do campus/VPN),
    cai automaticamente para SQLite local.
    """
    import socket

    def _pg_acessivel() -> bool:
        try:
            s = socket.create_connection((PG_HOST, PG_PORT), timeout=5)
            s.close()
            return True
        except OSError:
            return False

    if _pg_acessivel():
        log.info("PostgreSQL acessivel — conectando a %s/%s", PG_HOST, PG_DB)
        return create_engine(DB_URL)
    else:
        log.warning(
            "PostgreSQL em %s nao acessivel (fora da rede IESB/VPN).", PG_HOST
        )
        log.warning("Usando SQLite local como fallback: %s", SQLITE_PATH)
        return create_engine(f"sqlite:///{SQLITE_PATH}")


# ─── Main ─────────────────────────────────────────────────────────────────────

CSV_FINAL = PASTA_DADOS / "producao_hospitalar.csv"


def main():
    log.info("=" * 60)
    log.info("Carregador de Dados - SIH/SUS -> CSV processado")
    log.info("Saida: %s", CSV_FINAL)
    log.info("=" * 60)

    # ── Verifica arquivos de entrada ──────────────────────────────────────────
    arq_qtd = PASTA_DADOS / "quantidade_aprovada.csv"
    arq_val = PASTA_DADOS / "valor_aprovado.csv"

    for arq in (arq_qtd, arq_val):
        if not arq.exists():
            log.error("Arquivo nao encontrado: %s", arq)
            log.error("Execute o robo primeiro com 'executar_robo.bat'")
            sys.exit(1)

    # ── Parseia os dois CSVs ──────────────────────────────────────────────────
    log.info("\n[1/4] Lendo quantidade_aprovada.csv...")
    df_qtd_wide = parse_tabnet_prn(arq_qtd)
    df_qtd = wide_para_long(df_qtd_wide, "quantidade_aprovada")

    log.info("\n[2/4] Lendo valor_aprovado.csv...")
    df_val_wide = parse_tabnet_prn(arq_val)
    df_val = wide_para_long(df_val_wide, "valor_aprovado")

    # ── Une os dois DataFrames ────────────────────────────────────────────────
    log.info("\n[3/4] Unindo as duas metricas...")
    chave = ["municipio_codigo", "municipio_nome", "subgrupo_proced"]
    df_final = pd.merge(df_qtd, df_val, on=chave, how="outer").fillna(0)

    df_final = df_final[
        (df_final["quantidade_aprovada"] != 0) | (df_final["valor_aprovado"] != 0)
    ].reset_index(drop=True)

    log.info(
        "  Total de registros: %d  (%d subgrupos unicos)",
        len(df_final),
        df_final["subgrupo_proced"].nunique(),
    )

    # ── Salva CSV processado ──────────────────────────────────────────────────
    log.info("\n[4/4] Salvando CSV processado...")
    df_final.to_csv(CSV_FINAL, index=False, sep=";", decimal=",", encoding="utf-8-sig")
    log.info("  Salvo: %s (%.1f MB)", CSV_FINAL, CSV_FINAL.stat().st_size / 1e6)

    # ── Tenta também carregar no PostgreSQL/SQLite se disponível ──────────────
    try:
        engine = _conectar_banco()
        with engine.connect() as conn:
            conn.execute(text("DROP TABLE IF EXISTS producao_hospitalar"))
            conn.execute(text(DDL_PRODUCAO))
            for ddl in DDL_INDICES:
                conn.execute(text(ddl))
            conn.commit()
        df_final.to_sql("producao_hospitalar", engine,
                        if_exists="append", index=False, chunksize=5000)
        log.info("  Banco de dados tambem atualizado.")
    except Exception as e:
        log.warning("  Banco indisponivel (%s) — apenas CSV foi salvo.", e)

    log.info("\n" + "=" * 60)
    log.info("Pronto! Suba o arquivo abaixo para o GitHub:")
    log.info("  dados/producao_hospitalar.csv")
    log.info("Execute 'executar_app.bat' para iniciar o Streamlit.")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
