"""
Robô de extração de dados do DATASUS - TabNet
Produção Hospitalar (SIH/SUS) - Dados Detalhados de AIH (SP)
Abrangência: Brasil - Município | Jan/2024 a Jan/2026

Utiliza Playwright (mais robusto que Selenium para este caso):
  - Gerencia automaticamente esperas de carregamento
  - Não requer ChromeDriver manual
  - Suporte nativo a múltiplas abas/janelas
"""

import os
import sys
import time
import logging
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# ─── Configurações ────────────────────────────────────────────────────────────
URL_TABNET = "http://tabnet.datasus.gov.br/cgi/deftohtm.exe?sih/cnv/spabr.def"
PASTA_DADOS = Path(__file__).parent.parent / "dados"
PASTA_DADOS.mkdir(parents=True, exist_ok=True)

# Meses desejados: todos de 2024, todos de 2025, e Jan/2026 (total = 25 meses)
MESES_ALVO = ["2024", "2025", "jan/2026", "Jan/2026", "jan2026", "Jan2026"]

# Timeout máximo para o TabNet processar a consulta (3 minutos)
TIMEOUT_TABNET_MS = 180_000

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


# ─── Funções auxiliares ───────────────────────────────────────────────────────

def selecionar_periodos(page) -> int:
    """
    Seleciona todos os períodos de Jan/2024 a Jan/2026 no select #A.
    Retorna a quantidade de opções selecionadas.
    """
    count = page.evaluate(
        """
        (mesesAlvo) => {
            const sel = document.getElementById('A');
            if (!sel) return 0;
            let total = 0;
            for (const opt of sel.options) {
                const txt = opt.text.trim().toLowerCase();
                // Seleciona qualquer opção que contenha "2024", "2025" ou "jan/2026"
                const match = mesesAlvo.some(m => txt.includes(m.toLowerCase()));
                opt.selected = match;
                if (match) total++;
            }
            return total;
        }
        """,
        MESES_ALVO,
    )
    return count


def extrair_dataset(page, context, conteudo_label: str, nome_arquivo: str) -> Path:
    """
    Navega no TabNet, configura os filtros e extrai um dataset em formato PRN (CSV).

    Parâmetros
    ----------
    page          : página Playwright ativa (formulário TabNet)
    context       : contexto do browser (para capturar nova aba)
    conteudo_label: texto exato da opção no select Conteúdo/Incremento
    nome_arquivo  : nome do arquivo CSV de saída (salvo em PASTA_DADOS)

    Retorna o caminho do arquivo salvo.
    """
    log.info("Acessando TabNet: %s", URL_TABNET)
    page.goto(URL_TABNET)
    page.wait_for_load_state("domcontentloaded")
    time.sleep(2)  # pausa breve para JS finalizar renderização

    # ── 1. Linha: Município ──────────────────────────────────────────────────
    log.info("Configurando Linha = Município")
    page.select_option("#L", label="Município")
    time.sleep(0.5)

    # ── 2. Coluna: Subgrupo proced. ──────────────────────────────────────────
    log.info("Configurando Coluna = Subgrupo proced.")
    page.select_option("#C", label="Subgrupo proced.")
    time.sleep(0.5)

    # ── 3. Conteúdo ──────────────────────────────────────────────────────────
    log.info("Configurando Conteúdo = %s", conteudo_label)
    # Zera toda seleção antes
    page.evaluate(
        """
        const sel = document.getElementById('I');
        if (sel) for (const opt of sel.options) opt.selected = false;
        """
    )
    page.select_option("#I", label=conteudo_label)
    time.sleep(0.5)

    # ── 4. Período Jan/2024 a Jan/2026 (25 meses) ────────────────────────────
    log.info("Selecionando períodos Jan/2024 → Jan/2026")
    qtd = selecionar_periodos(page)
    log.info("%d períodos selecionados", qtd)
    if qtd == 0:
        raise RuntimeError(
            "Nenhum período foi selecionado. Verifique os textos das opções no TabNet."
        )

    # ── 5. Exibir linhas zeradas ─────────────────────────────────────────────
    log.info("Ativando exibição de linhas zeradas")
    checkbox = page.locator('input[name="zeradas"]')
    if checkbox.count() > 0 and not checkbox.is_checked():
        checkbox.check()

    # ── 6. Formato de saída: PRN (separado por ";") ──────────────────────────
    log.info("Selecionando formato PRN (CSV)")
    page.click('input[name="formato"][value="prn"]')
    time.sleep(0.3)

    # ── 7. Clicar em "Mostra" e aguardar nova aba ────────────────────────────
    log.info("Clicando em Mostra — aguardando o TabNet processar (até 3 min)...")
    with context.expect_page(timeout=TIMEOUT_TABNET_MS) as new_page_info:
        page.click('input[name="mostre"]')

    nova_pagina = new_page_info.value
    log.info("Nova aba aberta. Aguardando carregamento do resultado...")

    try:
        nova_pagina.wait_for_load_state("domcontentloaded", timeout=TIMEOUT_TABNET_MS)
        nova_pagina.wait_for_selector("pre", timeout=TIMEOUT_TABNET_MS)
    except PlaywrightTimeoutError:
        raise RuntimeError(
            "O TabNet excedeu o tempo máximo de resposta. "
            "Tente novamente mais tarde ou reduza o período de consulta."
        )

    # ── 8. Extrair texto e salvar CSV ─────────────────────────────────────────
    log.info("Extraindo texto da tag <pre>")
    texto_csv = nova_pagina.inner_text("pre")

    caminho_arquivo = PASTA_DADOS / nome_arquivo
    with open(caminho_arquivo, "w", encoding="latin1", errors="replace") as f:
        f.write(texto_csv)

    log.info("Arquivo salvo: %s (%d bytes)", caminho_arquivo, caminho_arquivo.stat().st_size)
    nova_pagina.close()
    return caminho_arquivo


# ─── Ponto de entrada ─────────────────────────────────────────────────────────

def main():
    log.info("=" * 60)
    log.info("Robô DATASUS - Produção Hospitalar SIH/SUS")
    log.info("Período: Jan/2024 a Jan/2026 | Abrangência: Brasil/Município")
    log.info("=" * 60)

    with sync_playwright() as p:
        # headless=False: mantém o browser visível para acompanhar
        browser = p.chromium.launch(headless=False, slow_mo=200)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="pt-BR",
        )
        page = context.new_page()

        try:
            # ── Dataset 1: Quantidade Aprovada ──────────────────────────────
            log.info("\n[1/2] Extraindo Quantidade Aprovada...")
            extrair_dataset(
                page, context,
                conteudo_label="Quantidade aprovada",
                nome_arquivo="quantidade_aprovada.csv",
            )

            # ── Dataset 2: Valor Aprovado ────────────────────────────────────
            log.info("\n[2/2] Extraindo Valor Aprovado...")
            extrair_dataset(
                page, context,
                conteudo_label="Valor aprovado",
                nome_arquivo="valor_aprovado.csv",
            )

        except Exception as exc:
            log.error("Erro durante a extração: %s", exc)
            raise
        finally:
            browser.close()
            log.info("\nNavegador fechado.")

    log.info("\n%s", "=" * 60)
    log.info("Extração concluída com sucesso!")
    log.info("Arquivos salvos em: %s", PASTA_DADOS)
    log.info("  - quantidade_aprovada.csv")
    log.info("  - valor_aprovado.csv")
    log.info("Execute 'carregar_dados.bat' para inserir os dados no banco.")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
