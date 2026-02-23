# 🧪 Guia de Testes - App Boletos

## Preparação para Testes

### 1. Criar Dados de Teste no Admin

```bash
# Acesse http://127.0.0.1:8000/admin/
# Login com seu usuário
```

#### Criar Ramo de Atuação
1. Vá em `Ramos de Atuação`
2. Clique em "Adicionar"
3. Preencha:
   - Nome: "Indústria"
   - Descrição: "Empresas industriais"
   - Ativo: ✓
4. Salve

#### Criar Clientes
1. Vá em `Clientes`
2. Clique em "Adicionar"
3. Preencha:
   - Nome: "Empresa XYZ LTDA"
   - CPF/CNPJ: "12.345.678/0001-90"
   - Email: "contato@empresa.com"
   - Telefone: "(81) 99999-9999"
   - Ramo de Atuação: "Indústria"
   - Endereço: "Rua ABC, 123, Recife, PE"
   - Ativo: ✓
4. Salve

Repita para 2-3 clientes diferentes.

#### Criar Boletos
1. Vá em `Boletos`
2. Clique em "Adicionar"
3. Preencha:
   - Cliente: "Empresa XYZ LTDA"
   - Número do Boleto: "001/2026"
   - Descrição: "Serviço Profissional Fevereiro"
   - Valor: "1500.00"
   - Data de Vencimento: "13/02/2026"
   - Vendedor: Seu usuário
   - Status: "ABERTO"
   - Observações: "Boleto para teste"
4. Salve

Crie 3-4 boletos com diferentes datas de vencimento:
- Um com vencimento hoje
- Um com vencimento em 5 dias
- Um com vencimento vencido
- Um com vencimento em 30 dias

---

## 🧪 Testes de Interface

### 1. Teste de Listagem de Boletos

**URL**: http://127.0.0.1:8000/boletos/

**Verificar:**
- [ ] Tabela com boletos carregou
- [ ] Cards de estatísticas aparecem (Abertos, Pendentes, Pagos, Vencidos)
- [ ] Filtros funcionam (Status, Cliente, Vendedor)
- [ ] Paginação aparece (se houver muitos boletos)
- [ ] Cores das datas estão corretas (vermelho para vencido, amarelo para próximo)

### 2. Teste de Detalhes do Boleto

**URL**: http://127.0.0.1:8000/boletos/boleto/1/

**Verificar:**
- [ ] Informações do boleto carregaram
- [ ] Cliente é um link funcional
- [ ] Data de vencimento e dias até vencimento aparecem
- [ ] Botões de ação aparecem (Editar, Voltar)
- [ ] Se status for diferente de PAGO, botão "Registrar Pagamento" aparece

### 3. Teste de Criação de Boleto

**URL**: http://127.0.0.1:8000/boletos/boleto/novo/

**Verificar:**
- [ ] Formulário carregou
- [ ] Validação: tente selecionar cliente em lista negra
  - Deve aparecer erro: "Cliente está na lista negra"
- [ ] Preencha com cliente válido e valores
- [ ] Salve e verifique redirecionamento para detalhes

### 4. Teste de Edição de Boleto

**URL**: http://127.0.0.1:8000/boletos/boleto/1/editar/

**Verificar:**
- [ ] Formulário pré-preenchido
- [ ] Modificar campos e salvar
- [ ] Mensagem de sucesso aparece
- [ ] Dados foram atualizados

### 5. Teste de Registro de Pagamento

**URL**: http://127.0.0.1:8000/boletos/boleto/1/pagamento/

**Verificar:**
- [ ] Resumo do boleto aparece
- [ ] Tentar submeter sem comprovante = erro
- [ ] Anexar arquivo (PDF, imagem, etc)
- [ ] Selecionar status "PAGO"
- [ ] Data de pagamento (defaulta para hoje)
- [ ] Salvar e verificar:
  - Status mudou para PAGO
  - Comprovante foi anexado
  - Redirecionou para detalhes

---

## 👥 Testes de Clientes

### 6. Teste de Listagem de Clientes

**URL**: http://127.0.0.1:8000/boletos/clientes/

**Verificar:**
- [ ] Tabela com clientes carregou
- [ ] Busca por nome funciona
- [ ] Filtro por ramo de atuação funciona
- [ ] Indicadores de lista negra aparecem
- [ ] Botões de ação funcionam (Ver, Editar)

### 7. Teste de Detalhes do Cliente

**URL**: http://127.0.0.1:8000/boletos/cliente/1/

**Verificar:**
- [ ] Informações pessoais carregaram
- [ ] Tabela de boletos mostra todos
- [ ] Total em aberto está correto
- [ ] Se houver controle de fiado:
  - Limite aparece
  - Saldo utilizado aparece
  - Percentual de barra de progresso
- [ ] Botões de ação aparecem

### 8. Teste de Criação de Cliente

**URL**: http://127.0.0.1:8000/boletos/cliente/novo/

**Verificar:**
- [ ] Validação CPF/CNPJ único
- [ ] Tentar com CPF existente = erro
- [ ] Preencher corretamente e salvar
- [ ] Redirecionamento para detalhes

### 9. Teste de Lista Negra

**URL**: http://127.0.0.1:8000/boletos/cliente/1/

**Na página de detalhes:**
- [ ] Clique em "Adicionar à Lista Negra"
- [ ] Preencha motivo
- [ ] Confirme
- [ ] Badge vermelho aparece
- [ ] Clique em "Remover de Lista Negra"
- [ ] Badge some

**URL**: http://127.0.0.1:8000/boletos/lista-negra/

- [ ] Cliente aparece na tabela de bloqueados
- [ ] Motivo aparece
- [ ] Responsável (seu usuário) aparece
- [ ] Clique em remover e verifique

---

## 💳 Testes de Fiado

### 10. Teste de Controle de Fiado

**URL**: http://127.0.0.1:8000/boletos/fiados/

**Verificar:**
- [ ] Tabela com controles de fiado carregou
- [ ] Limite, saldo utilizado, disponível aparecem
- [ ] Barra de progresso mostra percentual
- [ ] Cores corretas (verde < 50%, amarelo 50-80%, vermelho > 80%)

### 11. Teste de Edição de Fiado

**URL**: http://127.0.0.1:8000/boletos/fiado/1/editar/

**Verificar:**
- [ ] Limite de crédito: aumente para "5000.00"
- [ ] Saldo fiado: altere para "2000.00"
- [ ] Status: selecione "ATIVO"
- [ ] Salve
- [ ] Volte e verifique valores atualizados
- [ ] Percentual na tabela atualizou (40%)

### 12. Teste de Validações de Fiado

No Django shell:
```python
python manage.py shell
```

```python
from boletos.models import Cliente, ControleFiado
from boletos.services.boletos_service import ControleFiadoService
from decimal import Decimal

cliente = Cliente.objects.first()

# Estabelecer limite
controle = ControleFiadoService.estabelecer_limite(cliente, Decimal("1000.00"))

# Tentar adicionar acima do limite
try:
    ControleFiadoService.adicionar_fiado(cliente, Decimal("1500.00"))
except ValueError as e:
    print(f"✅ Erro capturado: {e}")

# Adicionar dentro do limite
ControleFiadoService.adicionar_fiado(cliente, Decimal("600.00"))

# Verificar saldo
print(f"Saldo fiado: {controle.saldo_fiado}")
print(f"Disponível: {controle.saldo_disponivel}")

# Pagar parcialmente
ControleFiadoService.pagar_fiado(cliente, Decimal("200.00"))
print(f"Após pagamento: {controle.saldo_fiado}")
```

---

## 🚫 Testes de Validações

### 13. Teste: Cliente em Lista Negra

1. Adicione cliente à lista negra
2. Vá para criar novo boleto
3. Selecione cliente bloqueado
4. Envie o formulário
5. **Esperado:** Erro "Cliente está na lista negra"

### 14. Teste: Comprovante Obrigatório

1. Vá para registrar pagamento de um boleto
2. Selecione status "PAGO"
3. Deixe comprovante em branco
4. Envie o formulário
5. **Esperado:** Erro "Comprovante é obrigatório"

### 15. Teste: Saldo de Fiado

1. Crie cliente com limite de 500
2. Tente adicionar 600 em fiado
3. **Esperado:** Erro "Saldo insuficiente"

---

## 🔧 Testes no Django Admin

### 16. Teste Admin de Boletos

**URL**: http://127.0.0.1:8000/admin/boletos/boleto/

**Verificar:**
- [ ] Lista de boletos com filtros laterais
- [ ] Status colorido (verde, vermelho, etc)
- [ ] Busca por número funciona
- [ ] Clique em um boleto
- [ ] Parcelas aparecem em inline
- [ ] Comprovante pode ser visto/baixado
- [ ] Campo de auditoria readonly

### 17. Teste Admin de Cliente

**URL**: http://127.0.0.1:8000/admin/boletos/cliente/

**Verificar:**
- [ ] Indicador de lista negra na coluna
- [ ] Busca por nome normalizado funciona
- [ ] Filtro por ramo de atuação
- [ ] Clique em cliente
- [ ] Informações carregaram correto

### 18. Teste Admin de Controle de Fiado

**URL**: http://127.0.0.1:8000/admin/boletos/controlefiado/

**Verificar:**
- [ ] Limite, saldo utilizado, disponível aparecem
- [ ] Percentual de utilização mostra correto
- [ ] Status colorido

---

## 📊 Testes de Filtros e Buscas

### 19. Teste Filtro de Boletos por Status

1. Vá para http://127.0.0.1:8000/boletos/
2. Clique em "Status" → "PAGO"
3. **Esperado:** Apenas boletos pagos aparecem

### 20. Teste Busca de Clientes

1. Vá para http://127.0.0.1:8000/boletos/clientes/
2. Busque por "empresa" (parcial)
3. **Esperado:** Clientes com "empresa" no nome aparecem
4. Tente buscar por CPF parcial
5. **Esperado:** Cliente encontrado

---

## 📈 Testes de Performance

### 21. Teste de Paginação

1. Crie 50+ boletos
2. Vá para listagem
3. **Esperado:** Mostra apenas 20 por página
4. Clique "Próxima"
5. **Esperado:** Próxima página carrega

---

## ✨ Checklist Final

- [ ] Todos os 21 testes passaram
- [ ] Não há erros 500
- [ ] Não há erros 404
- [ ] Mensagens de sucesso aparecem
- [ ] Validações funcionam
- [ ] Admin integrado corretamente
- [ ] Permissões estão funcionando
- [ ] Interface é responsiva
- [ ] Logout funciona (corrigido no início)

---

## 🐛 Casos de Erro Comuns

### Erro: "No reverse match found"
- **Causa:** URL não está registrada
- **Solução:** Verifique `boletos/urls.py`

### Erro: "Client is in blacklist"
- **Causa:** Esperado! Cliente está em lista negra
- **Solução:** Remova da lista negra para testar

### Erro: "Comprovante obrigatório"
- **Causa:** Esperado! Status é PAGO mas sem arquivo
- **Solução:** Anexe comprovante

### Erro: "Insufficient balance"
- **Causa:** Tentando adicionar fiado acima do limite
- **Solução:** Aumente o limite ou reduza valor

---

## 📞 Suporte

Se encontrar problemas:
1. Verifique o console do Django (terminal)
2. Verifique o browser (DevTools)
3. Confira as logs de erro 500
4. Verifique as permissões do usuário

---

**Bom teste!** 🚀
