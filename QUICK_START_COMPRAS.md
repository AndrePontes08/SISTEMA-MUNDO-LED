# 🚀 QUICK START - APP DE COMPRAS

## 1️⃣ INÍCIO RÁPIDO

Acesse a página de compras:
```
http://localhost:8000/compras/
```

Você verá:
- 📊 Dashboard com 4 cards de estatísticas
- 📈 Widget de tendências do mês
- ⭐ Top 5 fornecedores
- 📋 Tabela completa de compras
- 🔍 Filtros avançados

---

## 2️⃣ USANDO OS FILTROS

### Buscar por Fornecedor
```
Campo: "Fornecedor"
Tipo: Texto livre
Exemplo: "ASTRALED" ou "LED"
```

### Filtrar por Centro de Custo
```
Campo: "Centro de Custo"
Opções: FM, ML, PESSOAL, FM/ML, OUTROS
```

### Filtrar por Data
```
Campos: "Data Início" e "Data Fim"
Formato: YYYY-MM-DD
Exemplo: 2019-07-01 até 2019-12-31
```

### Paginação
```
Botão: "Itens por página"
Opções: 20, 40 ou 60
Clique automático aplica filtro
```

---

## 3️⃣ INTERPRETANDO O DASHBOARD

### Total de Compras
Número total de registros de compra no sistema (184)

### Valor Total
Soma de todos os valores das compras: **R$ 1.026.962,30**

### Ticket Médio
Valor médio por compra: **R$ 5.581,32**  
Cálculo: Total ÷ Quantidade de Compras

### Quantidade de Fornecedores
Fornecedores únicos cadastrados: **79**

---

## 4️⃣ LENDO AS TENDÊNCIAS

Exemplo:
```
Mês Atual: R$ 10.000
Mês Anterior: R$ 8.000
Variação: +25.0% (ALTA)
```

**Interpretação:**
- Mês atual teve 25% mais gasto que o anterior
- Tendência está em alta ↗️
- Observar se é planejado ou anômalo

---

## 5️⃣ RANKING DE FORNECEDORES

Mostra os 5 maiores fornecedores por volume financeiro:

```
1. ASTRALED
   R$ 90.441,36 | 7 compras

2. SORTELUZ
   R$ 88.424,21 | 13 compras

3. LAU
   R$ 63.575,00 | 9 compras

...
```

**Uso:** Identificar parceiros estratégicos e volumes principais

---

## 6️⃣ TRABALHANDO COM A TABELA

### Colunas Disponíveis
- **ID**: Número único da compra
- **Data**: Quando foi realizada (formato DD/MM/YYYY)
- **Fornecedor**: Nome do fornecedor
- **Centro**: Centro de custo (FM, ML, etc)
- **Itens**: Quantidade de produtos nesta compra
- **Total**: Valor total da compra
- **Ações**: Botões para visualizar/editar

### Ações
- 👁️ **Visualizar**: Ver detalhes completos
- ✏️ **Editar**: Modificar compra

---

## 7️⃣ ADICIONANDO NOVA COMPRA

Clique em **➕ Nova Compra** no canto superior direito.

Você será levado para um formulário onde pode:
1. Selecionar fornecedor (ou criar novo)
2. Escolher centro de custo
3. Adicionar itens (produtos, quantidades, preços)
4. Upload de documentos (nota fiscal, boleto, etc)
5. Adicionar observações

---

## 8️⃣ EXEMPLOS DE FILTROS

### Encontrar compras de LED
```
Fornecedor: "LED"
Data: (deixar em branco)
Centro: (deixar em branco)
Resultado: Todas as compras de fornecedores com "LED" no nome
```

### Compras de FM em julho de 2019
```
Fornecedor: (deixar em branco)
Centro: FM
Data Início: 2019-07-01
Data Fim: 2019-07-31
Resultado: Apenas compras do centro FM neste período
```

### Top 60 fornecedores do mês
```
Filtros: (deixar vazios)
Paginação: 60 itens por página
Resultado: Ver até 60 compras por vez
```

---

## 9️⃣ CONSULTANDO DADOS PROGRAMATICAMENTE

### Em views.py ou scripts Django
```python
from compras.services.statistics_service import ComprasStatisticsService

# Obter tudo
stats = ComprasStatisticsService.obter_estatisticas_gerais()
print(f"Total: {stats['total_valor']}")

# Top fornecedores
top = ComprasStatisticsService.obter_top_fornecedores(10)

# Tendências
tend = ComprasStatisticsService.obter_tendencias()

# Compras por período
periodo = ComprasStatisticsService.obter_compras_por_periodo(dias=30)
```

---

## 🔟 BOAS PRÁTICAS

✅ **Use filtros** ao procurar por períodos específicos  
✅ **Revise tendências** mensalmente para planejamento  
✅ **Monitore top fornecedores** para negociações  
✅ **Mantenha dados limpos** evitando duplicatas  
✅ **Documente decisões** nos campos de observação  
✅ **Faça backup regular** do banco de dados  

---

## 🆘 TROUBLESHOOTING

### Filtros não funcionam?
→ Clique em "Filtrar" ou deixe a página carregar

### Valores muito altos/baixos?
→ Verifique se não há zeros faltantes no XLSX

### Quero ver mais linhas?
→ Use o seletor "Itens por página" (20/40/60)

### Preciso de um relatório em PDF?
→ Use a função de impressão do navegador (Ctrl+P)

---

## 📞 SUPORTE

Se encontrar problemas:
1. Verifique se o servidor está rodando (`python manage.py runserver`)
2. Limpe o cache do navegador (Ctrl+Shift+Delete)
3. Verifique logs do Django para mensagens de erro
4. Contacte o desenvolvedor se o problema persistir

---

**Status**: Ready for Production ✨  
**Última atualização**: 13 de fevereiro de 2026
