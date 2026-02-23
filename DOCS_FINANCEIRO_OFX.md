# Modulo Financeiro - Importacao OFX (BB e Sicredi)

## Perfis com acesso
- `admin/gestor`
- `financeiro`

## Fluxo de uso
1. Acesse `Financeiro > Importar OFX`.
2. Arraste o arquivo `.ofx` ou selecione manualmente.
3. Revise a previa (primeiras transacoes, periodo e alertas).
4. Confirme a conta bancaria detectada (ou selecione no dropdown).
5. Clique em `Confirmar Importacao`.
6. Consulte o resultado em `Historico de Importacoes`.

## Como baixar OFX no Banco do Brasil (resumo)
1. Entre no internet banking BB.
2. Abra a opcao de `Extratos` da conta.
3. Selecione periodo desejado.
4. Escolha formato `OFX` para download.
5. Salve o arquivo e importe no ERP.

## Como baixar OFX no Sicredi (resumo)
1. Entre no internet banking Sicredi.
2. Acesse `Conta Corrente` ou `Extrato`.
3. Selecione o periodo.
4. Baixe em formato `OFX`.
5. Importe no ERP pela tela de OFX.

## Regras de seguranca e validacao
- Apenas extensao `.ofx` e ate `8 MB`.
- Arquivo armazenado em `media/financeiro/ofx`.
- Em producao, mantenha `MEDIA_ROOT` fora de acesso publico direto.
- Logs nao gravam dados sensiveis de autenticacao bancaria.

## Idempotencia e duplicidade zero
- Se `FITID` existir, chave idempotente usa `conta + FITID + account_id`.
- Se `FITID` nao existir, chave usa `conta + data + valor + descricao + account_id`.
- `TransacaoBancaria.idempotency_key` possui `UNIQUE` no banco.

## Conciliacao automatica (sugestoes)
- Compara entradas bancarias com recebiveis abertos.
- Regra padrao:
  - tolerancia de valor: `0.05`
  - janela de datas: `7 dias`
- Acoes manuais:
  - `Conciliar`
  - `Marcar divergente`
  - `Ignorar`

## Operacao e suporte
- Rode periodicamente o comando de grupos apos migracoes:
  - `python manage.py seed_groups`
- Para troubleshooting, use detalhes da importacao no historico (status, alertas e log).

