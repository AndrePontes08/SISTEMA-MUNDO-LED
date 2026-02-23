from __future__ import annotations

import hashlib
import logging
from datetime import date
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction

from financeiro.models import (
    ContaBancaria,
    ExtratoImportacao,
    StatusConciliacaoChoices,
    StatusImportacaoChoices,
    TipoMovimentoChoices,
    TransacaoBancaria,
)
from financeiro.services.normalizacao_service import NormalizacaoService
from financeiro.services.ofx_parser_service import OFXParserService

logger = logging.getLogger(__name__)


class ImportacaoOFXService:
    MAX_FILE_SIZE = 8 * 1024 * 1024

    @classmethod
    def criar_preview(
        cls,
        uploaded_file: Any,
        usuario: Any,
        conta_forcada: ContaBancaria | None = None,
    ) -> tuple[ExtratoImportacao, dict[str, Any]]:
        raw = uploaded_file.read()
        if not raw:
            raise ValidationError("Arquivo OFX vazio.")
        if len(raw) > cls.MAX_FILE_SIZE:
            raise ValidationError("Arquivo OFX excede o limite de tamanho (8 MB).")

        parsed = OFXParserService.parse_bytes(raw)
        banco_info = cls._extract_bank_info(parsed)
        conta_detectada = conta_forcada or cls._detectar_conta(parsed)
        sha256 = hashlib.sha256(raw).hexdigest()
        uploaded_file.seek(0)

        importacao = ExtratoImportacao.objects.create(
            conta=conta_detectada,
            banco_codigo=banco_info["banco_codigo"],
            banco_nome=banco_info["banco_nome"],
            arquivo=uploaded_file,
            arquivo_nome=getattr(uploaded_file, "name", "") or "",
            arquivo_sha256=sha256,
            periodo_inicio=parsed["detected_period_start"],
            periodo_fim=parsed["detected_period_end"],
            status=StatusImportacaoChoices.PREVIEW,
            transacoes_detectadas=len(parsed["transactions"]),
            alertas=cls._gerar_alertas_preview(parsed),
            resumo={
                "conta_detectada_id": conta_detectada.id if conta_detectada else None,
                "preview_transacoes": cls._preview_rows(parsed["transactions"]),
            },
            criado_por=usuario if getattr(usuario, "is_authenticated", False) else None,
        )

        logger.info(
            "Preview OFX criado importacao_id=%s conta_id=%s qtd=%s",
            importacao.id,
            importacao.conta_id,
            importacao.transacoes_detectadas,
        )
        return importacao, parsed

    @classmethod
    def confirmar_importacao(
        cls,
        importacao: ExtratoImportacao,
        conta: ContaBancaria | None,
        usuario: Any,
    ) -> dict[str, Any]:
        if importacao.status not in (StatusImportacaoChoices.PREVIEW, StatusImportacaoChoices.ERRO):
            raise ValidationError("Importacao ja processada.")
        if conta is None:
            raise ValidationError("Selecione uma conta bancaria antes de confirmar.")

        importacao.arquivo.open("rb")
        raw = importacao.arquivo.read()
        importacao.arquivo.close()
        parsed = OFXParserService.parse_bytes(raw)

        novas = 0
        duplicadas = 0
        periodo_inicio: date | None = parsed["detected_period_start"]
        periodo_fim: date | None = parsed["detected_period_end"]
        erros_linha: list[str] = []
        created_ids: list[int] = []

        with transaction.atomic():
            for idx, tx in enumerate(parsed["transactions"], start=1):
                data_lanc = tx["posted_at"]
                if not data_lanc:
                    erros_linha.append(f"Linha {idx}: data invalida.")
                    continue

                valor = Decimal(tx["amount"])
                tipo = cls._classificar_tipo(tx["trn_type"], valor)
                valor_abs = abs(valor)
                external_id = tx["fitid"] or None
                idempotency_key = cls._build_idempotency_key(
                    conta=conta,
                    data_lancamento=data_lanc,
                    valor=valor_abs,
                    descricao=tx["description"],
                    external_id=external_id,
                    account_id=tx.get("account_id", ""),
                )

                transacao, created = TransacaoBancaria.objects.get_or_create(
                    idempotency_key=idempotency_key,
                    defaults={
                        "conta": conta,
                        "importacao": importacao,
                        "data_lancamento": data_lanc,
                        "valor": valor_abs,
                        "tipo_movimento": tipo,
                        "descricao": tx["description"][:255],
                        "external_id": external_id,
                        "status_conciliacao": StatusConciliacaoChoices.PENDENTE,
                        "metadados": {
                            "trn_type": tx["trn_type"],
                            "memo": tx.get("memo", ""),
                            "name": tx.get("name", ""),
                            "checknum": tx.get("checknum", ""),
                            "bank_id": tx.get("bank_id", ""),
                            "branch_id": tx.get("branch_id", ""),
                            "account_id": tx.get("account_id", ""),
                        },
                    },
                )

                if created:
                    novas += 1
                    created_ids.append(transacao.id)
                else:
                    duplicadas += 1

            status = StatusImportacaoChoices.SUCESSO
            if erros_linha:
                status = StatusImportacaoChoices.PARCIAL if novas > 0 else StatusImportacaoChoices.ERRO
            elif duplicadas > 0 and novas == 0:
                status = StatusImportacaoChoices.PARCIAL

            importacao.conta = conta
            importacao.periodo_inicio = periodo_inicio
            importacao.periodo_fim = periodo_fim
            importacao.status = status
            importacao.transacoes_detectadas = len(parsed["transactions"])
            importacao.transacoes_importadas = novas
            importacao.transacoes_duplicadas = duplicadas
            importacao.alertas = cls._gerar_alertas_preview(parsed)
            importacao.resumo = {
                "conta_detectada_id": conta.id,
                "preview_transacoes": cls._preview_rows(parsed["transactions"]),
            }
            importacao.log_erro = "\n".join(erros_linha[:200])
            importacao.save()

        if created_ids:
            from financeiro.services.conciliacao_service import ConciliacaoService

            ConciliacaoService.marcar_sugestoes_para_transacoes(created_ids)

        logger.info(
            "Importacao OFX concluida importacao_id=%s status=%s novas=%s duplicadas=%s",
            importacao.id,
            importacao.status,
            novas,
            duplicadas,
        )

        return {
            "novas": novas,
            "duplicadas": duplicadas,
            "periodo_inicio": periodo_inicio,
            "periodo_fim": periodo_fim,
            "status": importacao.status,
            "erros": erros_linha,
        }

    @staticmethod
    def _classificar_tipo(trn_type: str, valor: Decimal) -> str:
        normalized = (trn_type or "").upper()
        if normalized in {"DEBIT", "PAYMENT", "FEE"}:
            return TipoMovimentoChoices.SAIDA
        if normalized in {"CREDIT", "DEP", "INT", "DIRECTDEP"}:
            return TipoMovimentoChoices.ENTRADA
        return TipoMovimentoChoices.ENTRADA if valor >= 0 else TipoMovimentoChoices.SAIDA

    @staticmethod
    def _build_idempotency_key(
        conta: ContaBancaria,
        data_lancamento: date,
        valor: Decimal,
        descricao: str,
        external_id: str | None,
        account_id: str,
    ) -> str:
        if external_id:
            return NormalizacaoService.gerar_hash_idempotencia(
                [str(conta.id), external_id, account_id]
            )
        return NormalizacaoService.gerar_hash_idempotencia(
            [str(conta.id), str(data_lancamento), str(valor), descricao, account_id]
        )

    @staticmethod
    def _preview_rows(transactions: list[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
        preview = []
        for tx in transactions[:limit]:
            preview.append(
                {
                    "posted_at": tx["posted_at"].isoformat() if tx["posted_at"] else "",
                    "amount": str(tx["amount"]),
                    "description": tx["description"],
                    "fitid": tx["fitid"],
                }
            )
        return preview

    @staticmethod
    def _extract_bank_info(parsed: dict[str, Any]) -> dict[str, str]:
        statements = parsed.get("statements") or []
        if not statements:
            return {"banco_codigo": "", "banco_nome": ""}
        first = statements[0]
        code = first.get("bank_id", "") or ""
        return {"banco_codigo": code, "banco_nome": code}

    @staticmethod
    def _detectar_conta(parsed: dict[str, Any]) -> ContaBancaria | None:
        statements = parsed.get("statements") or []
        if not statements:
            return None
        first = statements[0]
        bank_id = "".join(ch for ch in (first.get("bank_id", "") or "") if ch.isdigit())
        branch = "".join(ch for ch in (first.get("branch_id", "") or "") if ch.isdigit())
        account = "".join(ch for ch in (first.get("account_id", "") or "") if ch.isdigit())
        qs = ContaBancaria.objects.filter(ativa=True)
        if bank_id:
            qs = qs.filter(banco_codigo__icontains=bank_id)
        if branch:
            qs = qs.filter(agencia__icontains=branch)
        if account:
            qs = qs.filter(conta_numero__icontains=account)
        return qs.first()

    @staticmethod
    def _gerar_alertas_preview(parsed: dict[str, Any]) -> list[str]:
        alerts = list(parsed.get("alerts", []))
        start = parsed.get("detected_period_start")
        end = parsed.get("detected_period_end")
        if start and end:
            delta = (end - start).days
            if delta <= 1:
                alerts.append("Periodo detectado curto (ate 1 dia).")
        return alerts
