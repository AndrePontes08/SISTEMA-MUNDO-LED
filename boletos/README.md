# App Boletos 📋

Sistema completo e profissional para **controle de boletos, clientes, lista negra e crédito em fiado** com escalabilidade e boas práticas de desenvolvimento.

## 🎯 Funcionalidades Principais

### 1. **Controle de Boletos** 💰
- ✅ Criação e gerenciamento de boletos
- ✅ Rastreamento de vencimentos com alertas
- ✅ Registro de pagamentos com comprovantes
- ✅ Status automático (ABERTO, PAGO, VENCIDO, PENDENTE, CANCELADO)
- ✅ Filtros por cliente, vendedor e status
- ✅ Divisão em parcelas para boletos

### 2. **Gestão de Clientes** 👥
- ✅ Cadastro completo de clientes
- ✅ Categorização por ramo de atuação
- ✅ Histórico de boletos por cliente
- ✅ Informações de contato centralizadas
- ✅ Status ativo/inativo

### 3. **Lista Negra** 🚫
- ✅ Sistema de bloqueio de clientes
- ✅ Motivo de bloqueio registrado
- ✅ Auditoria (quem bloqueou e quando)
- ✅ Impede emissão de novos boletos
- ✅ Desbloqueio simples

### 4. **Controle de Fiado** 💳
- ✅ Limite de crédito por cliente
- ✅ Rastreamento de saldo utilizado
- ✅ Percentual de utilização visual
- ✅ Status de bloqueio de crédito
- ✅ Validação automática de saldo disponível

### 5. **Ramo de Atuação** 🏢
- ✅ Categorização de empresas/clientes
- ✅ Análise de quais ramos mais devem
- ✅ Filtros por segmento

## 🏗️ Arquitetura

```
boletos/
├── models.py              # Modelos de dados
├── views.py               # Views e lógica de apresentação
├── forms.py               # Formulários e validações
├── urls.py                # Rotas da aplicação
├── admin.py               # Interface administrativa
├── services/
│   └── boletos_service.py # Lógica de negócio e cálculos
├── migrations/            # Migrações do banco de dados
├── templates/boletos/
│   ├── boleto_list.html
│   ├── boleto_detail.html
│   ├── boleto_form.html
│   ├── boleto_pagamento.html
│   ├── cliente_list.html
│   ├── cliente_detail.html
│   ├── cliente_form.html
│   ├── lista_negra.html
│   ├── controle_fiado_list.html
│   └── controle_fiado_form.html
```

## 📊 Modelos de Dados

### Cliente
```python
Cliente(
    nome,                  # Nome da empresa/pessoa
    cpf_cnpj,            # Identificador único
    ramo_atuacao,        # Categoria de negócio
    email, telefone,     # Contato
    endereco,
    ativo                # Status
)
```

### Boleto
```python
Boleto(
    numero_boleto,       # Identificador único
    cliente,             # FK para Cliente
    valor,               # Valor a receber
    data_vencimento,     # Data limite
    data_pagamento,      # Quando foi pago
    vendedor,            # Responsável
    status,              # ABERTO, PAGO, VENCIDO, etc
    comprovante,         # Anexo do comprovante
)
```

### ClienteListaNegra
```python
ClienteListaNegra(
    cliente,             # FK para Cliente (OneToOne)
    motivo,              # Razão do bloqueio
    data_bloqueio,       # Quando foi bloqueado
    responsavel,         # Quem bloqueou
    ativo                # Status do bloqueio
)
```

### ControleFiado
```python
ControleFiado(
    cliente,             # FK para Cliente (OneToOne)
    limite_credito,      # Limite concedido
    saldo_fiado,         # Quanto está sendo usado
    status,              # ATIVO, BLOQUEADO, PAGO
)
```

### ParcelaBoleto
```python
ParcelaBoleto(
    boleto,              # FK para Boleto
    numero_parcela,      # Qual parcela
    valor,               # Valor da parcela
    data_vencimento,     # Vencimento
    status,              # Status individual
)
```

## 🔍 Services (Lógica de Negócio)

### BoletoService
```python
BoletoService.criar_boleto()           # Cria novo boleto
BoletoService.registrar_pagamento()    # Registra pagamento
BoletoService.verificar_vencimentos_em_atraso()
BoletoService.listar_boletos_criticos()  # Próximos a vencer
BoletoService.obter_total_em_aberto()
BoletoService.obter_estatisticas()
```

### ClienteService
```python
ClienteService.adicionar_lista_negra()  # Bloqueia cliente
ClienteService.remover_lista_negra()    # Desbloqueia
ClienteService.obter_clientes_em_lista_negra()
```

### ControleFiadoService
```python
ControleFiadoService.adicionar_fiado()     # Adiciona valor
ControleFiadoService.pagar_fiado()         # Reduz saldo
ControleFiadoService.estabelecer_limite()  # Define limite
ControleFiadoService.bloquear_fiado()      # Bloqueia crédito
ControleFiadoService.desbloquear_fiado()   # Desbloqueia
```

## 🔐 Permissões

O app usa grupos de permissão:
- `admin/gestor` - Acesso completo
- `boletos/vendedor` - Acesso limitado (criar boletos, registrar pagamentos)

## 📱 URLs Disponíveis

```
/boletos/                          # Lista de boletos
/boletos/boleto/<id>/              # Detalhes do boleto
/boletos/boleto/novo/              # Criar novo boleto
/boletos/boleto/<id>/editar/        # Editar boleto
/boletos/boleto/<id>/pagamento/     # Registrar pagamento

/boletos/clientes/                 # Lista de clientes
/boletos/cliente/<id>/             # Detalhes do cliente
/boletos/cliente/novo/             # Novo cliente
/boletos/cliente/<id>/editar/       # Editar cliente

/boletos/lista-negra/              # Clientes bloqueados
/boletos/cliente/<id>/adicionar-lista-negra/
/boletos/cliente/<id>/remover-lista-negra/

/boletos/fiados/                   # Controle de fiados
/boletos/fiado/<id>/               # Detalhes do fiado
/boletos/fiado/<id>/editar/        # Editar fiado
```

## 🛡️ Validações

1. **Cliente em Lista Negra**: Impede criar novos boletos ou adicionar fiado
2. **Comprovante Obrigatório**: Boletos pagos requerem comprovante
3. **Saldo Insuficiente**: Valida fiado contra limite de crédito
4. **Vencimentos**: Atualiza status automaticamente
5. **Unicidade**: CPF/CNPJ e número de boleto são únicos

## 📈 Índices de Banco de Dados

Para performance otimizada:
- `idx_boleto_numero` - Busca rápida por número
- `idx_boleto_cliente_status` - Filtros comuns
- `idx_boleto_vencimento` - Alertas de vencimento
- `idx_cliente_nome_norm` - Busca por nome
- `idx_cliente_cpf_cnpj` - Busca por documento

## 🚀 Como Usar

### Criar um Boleto
```python
from boletos.services.boletos_service import BoletoService
from boletos.models import Cliente
from decimal import Decimal
from datetime import datetime, timedelta

cliente = Cliente.objects.get(pk=1)
boleto = BoletoService.criar_boleto(
    cliente=cliente,
    numero_boleto="001/2026",
    descricao="Serviço Profissional",
    valor=Decimal("1500.00"),
    data_vencimento=datetime.now().date() + timedelta(days=30),
    vendedor=request.user,
)
```

### Registrar Pagamento
```python
BoletoService.registrar_pagamento(
    boleto=boleto,
    data_pagamento=datetime.now().date(),
    comprovante=arquivo
)
```

### Adicionar à Lista Negra
```python
from boletos.services.boletos_service import ClienteService

ClienteService.adicionar_lista_negra(
    cliente=cliente,
    motivo="Histórico de débitos",
    responsavel=request.user
)
```

### Gerenciar Fiado
```python
from boletos.services.boletos_service import ControleFiadoService

ControleFiadoService.estabelecer_limite(cliente, Decimal("5000.00"))
ControleFiadoService.adicionar_fiado(cliente, Decimal("1200.00"))
ControleFiadoService.pagar_fiado(cliente, Decimal("600.00"))
```

## 📊 Estatísticas

Acesso rápido a métricas:
```python
stats = BoletoService.obter_estatisticas()
# {
#     'total_abertos': 15,
#     'total_pendentes': 3,
#     'total_pagos': 127,
#     'total_vencidos': 2,
#     'valor_total_aberto': Decimal('45320.50')
# }
```

## 🎨 Interface

- Dashboard com cards de estatísticas
- Tabelas responsivas com filtros
- Formulários com validação
- Paginação inteligente
- Badges de status coloridas
- Barras de progresso para fiado

## 🔒 Segurança

- ✅ CSRF Protection
- ✅ LoginRequiredMixin em todas as views
- ✅ GroupRequiredMixin para controle de acesso
- ✅ Validação de formulários
- ✅ Auditoria de ações

## 📝 Próximas Melhorias

- [ ] Geração de PDF de boletos
- [ ] Integração com sistemas de pagamento
- [ ] Relatórios avançados
- [ ] Notificações por email
- [ ] API REST para integração
- [ ] Dashboard com gráficos
- [ ] Backup automático

---

**Desenvolvido com ❤️ seguindo padrões Django profissionais e escaláveis**
