# Importador PDF Caixa (Softcom) - Integracao Incremental

## O que foi adicionado
- Novo app: `importadores`
- Rotas novas (isoladas): `importadores/caixa/...`
- Novo card no dashboard inicial com "Resultado do Dia"
- Sem alterar regras antigas de compras, estoque, contas ou financeiro

## Rotas
- Importar PDF: `/importadores/caixa/importar/`
- Historico: `/importadores/caixa/importacoes/`
- Detalhe importacao: `/importadores/caixa/importacoes/<id>/`

## Fluxo
1. Upload manual do PDF "Relatorio Caixa Analitico".
2. Parser extrai:
   - data do relatorio
   - unidade (MATRIZ/FILIAL -> LOJA_1/LOJA_2)
   - total de vendas em "Totalizacao do Caixa > Vendas > TOTAL"
   - itens vendidos (codigo mercadoria e quantidade)
3. Importacao persiste dados com idempotencia por `hash + data + unidade`.
4. Baixa de estoque por unidade:
   - busca produto por `Produto.sku = codigo_mercadoria`
   - decrementa `ProdutoEstoqueUnidade`
   - cria `EstoqueMovimento` de saida com observacao de VENDA PDF
   - registra trilha em `MovimentoVendaEstoque` (tipo VENDA)
5. Dashboard calcula:
   - `resultado = vendas_pdf - saidas_financeiro_confirmadas`

## Configuracao obrigatoria para resultado por unidade
No admin, configurar:
- `UnidadeContaFinanceiraConfig`:
  - `LOJA_1` -> Conta bancaria correspondente
  - `LOJA_2` -> Conta bancaria correspondente

Sem esse mapeamento, saidas da unidade ficam `0,00` no card.

## Dependencia de parser PDF
Foi adicionado em `requirements.txt`:
- `pypdf>=4.2.0`

Se o ambiente ainda nao tiver essa lib, execute instalacao de dependencias no deploy.

## Modelos novos (apenas adicao)
- `UnidadeContaFinanceiraConfig`
- `CaixaRelatorioImportacao`
- `CaixaRelatorioItem`
- `CaixaImportacaoInconsistencia`
- `MovimentoVendaEstoque`

## Observacoes de compatibilidade
- Nenhum model/rota existente foi renomeado.
- Nenhum campo antigo foi removido ou alterado.
- A funcionalidade nova e plugavel; falhas de item nao derrubam importacao inteira.

