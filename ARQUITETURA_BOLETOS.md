# 📐 Arquitetura do App Boletos

## 📊 Diagrama de Modelos

```
┌─────────────────────────────────────────────────────────────────┐
│                        APP BOLETOS                              │
└─────────────────────────────────────────────────────────────────┘

                           RamoAtuacao
                           ┌─────────┐
                           │  nome   │
                           │ descr   │
                           │ ativo   │
                           └────┬────┘
                                │
                                │ 1:M
                                │
                    ┌───────────┴──────────────┐
                    │                          │
                    │                          │
              ┌─────▼────────┐         ┌──────▼────────┐
              │   Cliente    │         │  Cliente      │
              │  ┌─────────┐ │         │  ListaNegra   │
              │  │ nome    │ │         │  ┌──────────┐ │
              │  │ cpf_cnpj│ │         │  │ motivo   │ │
              │  │ email   │ │         │  │ data_blq │ │
              │  │ telefone│ │         │  │ responsv │ │
              │  │ endereco│ │         │  │ ativo    │ │
              │  │ ramo_id │ │         │  └──────────┘ │
              │  │ ativo   │ │         │  (OneToOne)   │
              │  └─────────┘ │         └───────────────┘
              └────┬─────────┘
                   │
                   │ 1:M (Boleto.cliente)
                   │
              ┌────▼──────────┐
              │    Boleto     │
              │  ┌──────────┐ │
              │  │ numero   │ │
              │  │ valor    │ │
              │  │ vencim   │ │
              │  │ pagam    │ │
              │  │ status   │ │
              │  │ vendedor │ │  ◄─── User (FK)
              │  │ comprv   │ │
              │  │ obs      │ │
              │  └──────────┘ │
              └────┬──────────┘
                   │
                   │ 1:M (ParcelaBoleto.boleto)
                   │
              ┌────▼────────────┐
              │ ParcelaBoleto    │
              │  ┌────────────┐  │
              │  │ numero     │  │
              │  │ valor      │  │
              │  │ vencim     │  │
              │  │ pagam      │  │
              │  │ status     │  │
              │  └────────────┘  │
              └──────────────────┘

              ┌────────────────┐
              │ ControleFiado   │
              │  ┌──────────┐   │
              │  │ cliente  │   │ ◄─── OneToOne
              │  │ limite   │   │
              │  │ saldo    │   │
              │  │ status   │   │
              │  └──────────┘   │
              └──────────────────┘
```

---

## 🔄 Fluxo de Dados

### Criação de Boleto
```
User Input (Form)
    │
    ▼
BoletoForm (Validação de entrada)
    │
    ├─ Valida cliente não em lista negra
    ├─ Valida arquivo comprovante (se PAGO)
    └─ Salva no banco
    │
    ▼
BoletoCreateView
    │
    ├─ save() no formulário
    └─ Redirect para detalhes
    │
    ▼
BoletoDetailView (Exibe boleto criado)
```

### Registro de Pagamento
```
User Input (Foto/PDF comprovante)
    │
    ▼
BoletoComPagamentoForm
    │
    ├─ Valida comprovante obrigatório
    └─ Valida status PAGO
    │
    ▼
BoletoRegistrarPagamentoView
    │
    ├─ BoletoService.registrar_pagamento()
    │  └─ Atualiza status, data, comprovante
    │
    ▼
Redirect para BoletoDetailView
```

### Adicionar à Lista Negra
```
User (Clica "Adicionar à Lista Negra")
    │
    ▼
ClienteAdicionarListaNegraMixin
    │
    ├─ Recebe POST com motivo
    │
    ▼
ClienteService.adicionar_lista_negra()
    │
    ├─ Cria ClienteListaNegra
    ├─ Registra responsável (user)
    ├─ Registra data
    └─ Define ativo=True
    │
    ▼
Agora: Não pode mais receber boletos!
```

---

## 🏗️ Arquitetura em Camadas

```
┌─────────────────────────────────────────┐
│           Presentation (Templates)      │
│  (HTML, Bootstrap, Forms, Validation)  │
└────────────────────┬────────────────────┘
                     │
┌────────────────────▼────────────────────┐
│         Views (Django CBVs)             │
│  (ListView, DetailView, CreateView)    │
│  (Paginação, Filtros, Contexto)       │
└────────────────────┬────────────────────┘
                     │
┌────────────────────▼────────────────────┐
│          Forms (Validação)              │
│  (Field validation, clean methods)     │
│  (Business rules enforcement)          │
└────────────────────┬────────────────────┘
                     │
┌────────────────────▼────────────────────┐
│        Services (Business Logic)        │
│  - BoletoService                       │
│  - ClienteService                      │
│  - ControleFiadoService                │
│  (Cálculos, validações, transações)   │
└────────────────────┬────────────────────┘
                     │
┌────────────────────▼────────────────────┐
│         Models (Django ORM)             │
│  - Cliente                             │
│  - Boleto                              │
│  - ParcelaBoleto                       │
│  - ClienteListaNegra                   │
│  - ControleFiado                       │
│  - RamoAtuacao                         │
│  (Índices, constraints, signals)      │
└────────────────────┬────────────────────┘
                     │
┌────────────────────▼────────────────────┐
│           Database (SQLite)             │
│  (Persistência de dados)               │
└─────────────────────────────────────────┘
```

---

## 🔐 Fluxo de Autorização

```
Request chega
    │
    ▼
URLRouter (/boletos/...)
    │
    ▼
View (ex: BoletoListView)
    │
    ├─ LoginRequiredMixin
    │  └─ User autenticado? NÃO → Redirect /login
    │  └─ User autenticado? SIM → Continua
    │
    ├─ GroupRequiredMixin (BoletoAccessMixin)
    │  └─ User em "admin/gestor" ou "boletos/vendedor"?
    │  └─ NÃO → 403 Forbidden
    │  └─ SIM → Continua
    │
    ▼
get_queryset() + context
    │
    ▼
Render template com dados
    │
    ▼
Response ao user
```

---

## 📊 Fluxo de Paginação

```
GET /boletos/?page=2
    │
    ▼
BoletoListView.get_paginate_by()
    │
    ├─ Lê settings
    ├─ Chama get_pagination_params(request)
    └─ Retorna page_size=20
    │
    ▼
Django Paginator
    │
    ├─ Total de 127 boletos
    ├─ 20 por página = 7 páginas
    ├─ Página 2 = itens 20-40
    │
    ▼
Context com page_obj
    │
    ├─ page_obj.number = 2
    ├─ page_obj.paginator.num_pages = 7
    ├─ page_obj.has_previous = True
    ├─ page_obj.has_next = True
    │
    ▼
Template renderiza
    │
    └─ Links: Primeira | Anterior | 2 de 7 | Próxima | Última
```

---

## 🔍 Fluxo de Filtros

```
User seleciona filtro
    │
    GET /boletos/?status=PAGO&cliente=1
    │
    ▼
BoletoListView.get_queryset()
    │
    ├─ Base: Boleto.objects.all()
    │
    ├─ if status:
    │  └─ qs = qs.filter(status=status)
    │
    ├─ if cliente_id:
    │  └─ qs = qs.filter(cliente_id=cliente_id)
    │
    ├─ if vendedor_id:
    │  └─ qs = qs.filter(vendedor_id=vendedor_id)
    │
    ▼
Retorna queryset filtrado
    │
    ▼
Template exibe resultados
```

---

## 💾 Fluxo de Salvamento no Banco

```
Form submetido via POST
    │
    ▼
BoletoForm.clean()
    │
    ├─ Validação de campo por campo
    ├─ Validações customizadas
    └─ Retorna cleaned_data ou erros
    │
    ▼
View.form_valid() ou form_invalid()
    │
    │ [SE VÁLIDO]
    ▼
form.save(commit=False)
    │
    ├─ Cria instância sem salvar
    ├─ Permite modificações (se necessário)
    │
    ▼
instance.save()
    │
    ├─ Triggers model.save()
    ├─ Executa validadores
    ├─ INSERT ou UPDATE no banco
    │
    ▼
messages.success() [feedback]
    │
    ▼
Redirect para detalhes
    │
    │ [SE INVÁLIDO]
    ▼
form_invalid()
    │
    ├─ Re-renderiza template com erros
    └─ User corrige e resubmete
```

---

## 📈 Fluxo de Estatísticas

```
BoletoListView.get_context_data()
    │
    ├─ context['stats'] = BoletoService.obter_estatisticas()
    │
    ▼
BoletoService.obter_estatisticas()
    │
    ├─ Boleto.objects.filter(status=ABERTO).count()
    ├─ Boleto.objects.filter(status=PENDENTE).count()
    ├─ Boleto.objects.filter(status=PAGO).count()
    ├─ Boleto.objects.filter(status=VENCIDO).count()
    ├─ Boleto.objects.filter(status__in=[ABERTO, PENDENTE]).aggregate(Sum('valor'))
    │
    ▼
Retorna dict {total_abertos, total_pagos, ...}
    │
    ▼
Template renderiza cards
    │
    └─ Card Abertos: 15
    └─ Card Pagos: 127
    └─ Card Vencidos: 2
    └─ Card Valor Total: R$ 45.320,50
```

---

## 🎯 Decisão: Adicionar à Lista Negra

```
User clica "Adicionar à Lista Negra"
    │
    ▼
POST /boletos/cliente/1/adicionar-lista-negra/
    │
    ▼
ClienteAdicionarListaNegraMixin.post()
    │
    ├─ cliente = get_object_or_404(Cliente, pk=pk)
    │
    ├─ ClienteService.adicionar_lista_negra(
    │    cliente=cliente,
    │    motivo=request.POST['motivo'],
    │    responsavel=request.user
    │  )
    │
    ▼
ClienteListaNegra.objects.get_or_create()
    │
    ├─ Cria novo registro se não existe
    ├─ Registra data_bloqueio (today)
    ├─ Registra responsavel (user)
    ├─ Define ativo=True
    │
    ▼
messages.success()
    │
    └─ "Cliente XYZ adicionado à lista negra"
    │
    ▼
Redirect para cliente_detail
    │
    ▼
Template exibe badge vermelho "🚫 CLIENTE EM LISTA NEGRA"
```

---

## 🔄 Fluxo Completo: Novo Boleto até Pagamento

```
1. User vai para /boletos/boleto/novo/
   └─ BoletoCreateView carrega template

2. User preenche formulário
   ├─ Cliente: Empresa XYZ
   ├─ Número: 001/2026
   ├─ Valor: 1500.00
   └─ Vencimento: 15/03/2026

3. User submete POST
   └─ BoletoForm valida

4. Se inválido: Re-renderiza com erros
   Se válido: Continua...

5. Cria Boleto no banco
   ├─ status = ABERTO
   ├─ data_emissao = today
   └─ vendedor = request.user

6. Redirect para BoletoDetailView
   ├─ Exibe resumo
   └─ Botão "Registrar Pagamento"

7. (Mais tarde) User clica "Registrar Pagamento"
   └─ Vai para BoletoRegistrarPagamentoView

8. User anexa comprovante
   ├─ Seleciona status PAGO
   └─ Submete

9. BoletoComPagamentoForm valida
   ├─ Comprovante obrigatório? ✓
   └─ Status PAGO? ✓

10. BoletoService.registrar_pagamento()
    ├─ status = PAGO
    ├─ data_pagamento = today
    ├─ comprovante_pagamento = arquivo
    └─ save()

11. Redirect para detalhes
    └─ Exibe com badge verde "PAGO"

12. Done! ✅
```

---

## 🎨 Estrutura de URLs

```
/boletos/                              (BoletoListView)
│
├─ boleto/
│  ├─ <id>/                           (BoletoDetailView)
│  ├─ <id>/editar/                    (BoletoUpdateView)
│  ├─ <id>/pagamento/                 (BoletoRegistrarPagamentoView)
│  └─ novo/                           (BoletoCreateView)
│
├─ clientes/                          (ClienteListView)
│  ├─ <id>/                           (ClienteDetailView)
│  ├─ <id>/editar/                    (ClienteUpdateView)
│  ├─ <id>/adicionar-lista-negra/     (ClienteAdicionarListaNegraMixin)
│  ├─ <id>/remover-lista-negra/       (ClienteRemoverListaNegraView)
│  └─ novo/                           (ClienteCreateView)
│
├─ lista-negra/                       (ListaNegraBoletoListView)
│
└─ fiados/                            (ControleFiadoListView)
   ├─ <id>/                           (ControleFiadoDetailView)
   └─ <id>/editar/                    (ControleFiadoUpdateView)
```

---

Este é um app profissional, bem estruturado e escalável! 🚀
