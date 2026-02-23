# 🏗️ ARQUITETURA - APP DE COMPRAS

## 📦 ESTRUTURA DOS COMPONENTES

```
compras/
├── management/
│   └── commands/
│       └── import_compras_excel.py      ← Comando de importação
├── services/
│   ├── compras_service.py               ← Service existente
│   └── statistics_service.py            ← Service novo de estatísticas
├── models.py                            ← (Sem alterações)
├── views.py                             ← (Melhorado com filtros)
├── templates/
│   └── compras/
│       └── compra_list.html             ← (Redesenhado)
└── urls.py                              ← (Sem alterações)
```

---

## 🔄 FLUXO DE DADOS

### IMPORTAÇÃO
```
COMPRAS_PROCESSADO2.XLSX
        ↓
import_compras_excel (Command)
        ↓
Validação de dados
        ↓
Normalização de nomes
        ↓
Obter/Criar Fornecedores
        ↓
Obter/Criar Produtos
        ↓
Criar Compras & Itens
        ↓
Django ORM (Database)
        ↓
✅ Resultado: 184 compras, 1026 itens
```

### EXIBIÇÃO
```
User acessa /compras/
        ↓
CompraListView (Django)
        ↓
get_queryset() + get_context_data()
        ↓
Filtros aplicados (opcional)
        ↓
ComprasStatisticsService (cálculos)
        ↓
Contexto renderizado
        ↓
compra_list.html (Bootstrap)
        ↓
✅ Dashboard visual completo
```

---

## 📊 MANAGEMENT COMMAND: import_compras_excel.py

### Responsabilidades
1. **Leitura** do arquivo XLSX com pandas
2. **Validação** de colunas obrigatórias
3. **Normalização** de nomes (fornecedores/produtos)
4. **Deduplicação** automática
5. **Tratamento de erros** com modo skip
6. **Transação atômica** (tudo ou nada)
7. **Relatório detalhado** ao final

### Métodos Principais
```python
def handle(self, *args, **options)
    └─ Ponto de entrada do comando

def _get_or_create_fornecedor(nome: str) -> tuple
    └─ Cria ou obtém fornecedor existente

def _get_or_create_produto(descricao: str) -> tuple
    └─ Cria ou obtém produto existente

def _exibir_relatorio(stats: dict)
    └─ Formata e exibe relatório final
```

### Fluxo Interno
```
1. Ler arquivo XLSX
2. Para cada grupo de (fornecedor, data):
   a. Obter/criar fornecedor
   b. Criar compra
   c. Para cada item:
      - Obter/criar produto
      - Criar ItemCompra
      - Acumular valor_total
   d. Salvar compra com total calculado
3. Exibir relatório com estatísticas
```

---

## 📈 SERVICE: statistics_service.py

### Arquitetura

```
ComprasStatisticsService (classe estática)
├── obter_estatisticas_gerais()
│   └─ Count + Sum queryset
├── obter_top_fornecedores(limit)
│   └─ Annotate + Order_by
├── obter_produtos_mais_comprados(limit)
│   └─ Values + Count queryset
├── obter_compras_por_centro_custo()
│   └─ Filter + Loop choices
├── obter_compras_por_periodo(dias)
│   └─ Filter + Date trunc
├── obter_tendencias()
│   └─ Compare mês atual vs anterior
└── obter_fornecedores_por_categoria()
    └─ Segmenta por volume
```

### Queries Otimizadas
Cada função utiliza:
- ✅ `select_related` quando necessário
- ✅ `prefetch_related` para relacionamentos
- ✅ `annotate` para cálculos de banco
- ✅ `filter` eficiente com índices

### Exemplos de Uso

```python
# Total investido
stats = ComprasStatisticsService.obter_estatisticas_gerais()
total = stats['total_valor']  # Decimal

# Ranking
top = ComprasStatisticsService.obter_top_fornecedores(10)
# [{'nome': 'ASTRALED', 'total_valor': 90441.36, ...}, ...]

# Análise
tend = ComprasStatisticsService.obter_tendencias()
# {'gasto_mes_atual': 0.00, 'variacao_percentual': 0.0, 'tendencia': 'ESTÁVEL'}
```

---

## 🎨 VIEW: CompraListView

### Responsabilidades
1. Recuperar compras com otimização
2. Aplicar filtros
3. Preparar contexto com estatísticas
4. Renderizar template

### Filtros Implementados
```python
# Por fornecedor (text icontains)
if fornecedor:
    qs = qs.filter(fornecedor__nome__icontains=fornecedor)

# Por centro de custo (exact)
if centro:
    qs = qs.filter(centro_custo=centro)

# Por data (range)
if data_inicio:
    qs = qs.filter(data_compra__gte=data_inicio)
if data_fim:
    qs = qs.filter(data_compra__lte=data_fim)
```

### Contexto Disponível no Template
```python
{
    'compras': QuerySet,           # Paginado
    'centros_custo': list,         # Choices
    'stats': dict,                 # Estatísticas gerais
    'top_fornecedores': QuerySet,  # Top 5
    'tendencias': dict,            # Análise mês
    'compras_por_centro': dict,    # Breakdown
    'is_paginated': bool,
    'page_obj': Page,
}
```

---

## 📄 TEMPLATE: compra_list.html

### Sections
```html
1. Header (Título + Botão Nova Compra)
2. Dashboard (4 cards de stats)
3. Tendências (Mês atual vs anterior)
4. Filtros (Form com 4 campos)
5. Top Fornecedores (Cards com top 5)
6. Tabela de Compras (Responsive)
7. Paginação (Modern card-based)
```

### Dados Dinâmicos
- Stats renderizados em Python
- Filtros mantêm estado via querystring
- Tabela atualiza conforme filtros
- Paginação com auto-submit

---

## 🔐 VALIDAÇÕES

### Na Importação
```
✅ Arquivo existe?
✅ Colunas obrigatórias presentes?
✅ Dados não vazios?
✅ Valores numéricos válidos?
✅ Quantidade > 0?
✅ Preço >= 0?
```

### No Banco de Dados
```
✅ ForeignKey constraints
✅ Unique constraints em nome_normalizado
✅ Min/Max validators em Decimal fields
✅ Index em campos de busca
```

### No Template
```
✅ CSRF protection em forms
✅ Escaping de valores HTML
✅ Breadcrumb navigation
✅ Form validation
```

---

## 🚀 PERFORMANCE

### Database Queries
```python
# Otimizado
qs = Compra.objects.select_related("fornecedor").prefetch_related("itens")

# Evitar N+1
- Use prefetch_related para relacionamentos M2M
- Use select_related para ForeignKey
- Use only() para campos específicos
```

### Indexação
Índices criados em:
- `data_compra`
- `centro_custo`
- `fornecedor`
- `nome_normalizado` (búsca)

### Paginação
Padrão: 20 itens (opções: 40, 60)
Evita carregar todas as linhas ao mesmo tempo

---

## 🛡️ SEGURANÇA

### Access Control
```python
class ComprasAccessMixin(GroupRequiredMixin):
    required_groups = ("admin/gestor", "compras/estoque")
```

### Validação de Entrada
- Todos os filtros são sanitizados
- QueryStrings escapados no template
- CSRF tokens em todos os forms

### Integridade de Dados
- Transação atômica na importação
- Constraints no banco de dados
- Backup regular recomendado

---

## 📊 RELATÓRIOS DISPONÍVEIS

### Dashboard
- Total de compras
- Valor total investido
- Ticket médio
- Quantidade de fornecedores

### Análises
- Top fornecedores
- Tendências (mês atual vs anterior)
- Breakdown por centro de custo
- Produtos mais comprados

### Exportação
Recomendações:
- Use Ctrl+P para imprimir como PDF
- Copie a tabela para Excel
- Use ferramentas de BI externas

---

## 🔧 EXTENSIBILIDADE

### Para Adicionar Nova Métrica
```python
# Em statistics_service.py
@staticmethod
def nova_metrica():
    return (
        Compra.objects
        .aggregate(...)
        .values()
    )

# No template
{{ nova_metrica }}
```

### Para Novo Filtro
```python
# Em views.py get_queryset()
novo_filtro = self.request.GET.get("novo_filtro")
if novo_filtro:
    qs = qs.filter(campo=novo_filtro)

# No template form
<input name="novo_filtro" ...>
```

---

## 📚 DEPENDÊNCIAS

```
Django>=6.0
pandas>=1.3.0
openpyxl>=3.0
```

### Verificar versões
```bash
pip show django pandas openpyxl
```

---

## 🧪 TESTES RECOMENDADOS

```python
# test_import.py
def test_import_comando_valida():
    """Testa se comando executa sem erros"""
    call_command('import_compras_excel', skip_errors=True)
    assert Compra.objects.count() == 184

# test_statistics.py
def test_obter_estatisticas():
    """Testa cálculos de estatísticas"""
    stats = ComprasStatisticsService.obter_estatisticas_gerais()
    assert stats['total_compras'] > 0
    assert stats['total_valor'] > 0
```

---

## 📝 DOCUMENTAÇÃO RELACIONADA

- `RESUMO_IMPORTACAO_COMPRAS.md` - Overview do projeto
- `QUICK_START_COMPRAS.md` - Guia do usuário
- `IMPORTACAO_COMPRAS_RELATORIO.md` - Detalhes técnicos

---

*Documentação de Arquitetura - 13 de fevereiro de 2026*
