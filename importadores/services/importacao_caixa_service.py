from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from importadores.models import (
    CaixaRelatorioImportacao,
    CaixaRelatorioItem,
    StatusImportacaoPDFChoices,
)
from importadores.services.estoque_baixa_service import EstoqueBaixaService
from importadores.services.pdf_caixa_service import PDFCaixaService


class ImportacaoCaixaService:
    @classmethod
    def importar_pdf(cls, *, uploaded_file, usuario, unidade_override: str = "", data_referencia_override=None):
        raw = uploaded_file.read()
        if not raw:
            raise ValidationError("Arquivo PDF vazio.")

        arquivo_hash = PDFCaixaService.build_hash(raw)
        text = PDFCaixaService.extract_text_from_pdf_bytes(raw)
        parsed = PDFCaixaService.parse_caixa_text(
            text,
            unidade_override=unidade_override,
            data_override=data_referencia_override,
            source_name=getattr(uploaded_file, "name", "") or "",
        )

        uploaded_file.seek(0)
        try:
            with transaction.atomic():
                importacao = CaixaRelatorioImportacao.objects.create(
                    data_referencia=parsed["data_referencia"],
                    unidade=parsed["unidade"],
                    empresa_nome=parsed["empresa_nome"],
                    arquivo_pdf=uploaded_file,
                    arquivo_nome=getattr(uploaded_file, "name", "") or "",
                    arquivo_hash=arquivo_hash,
                    total_vendas=parsed["total_vendas"],
                    total_trocas=parsed.get("total_trocas") or 0,
                    vendas_detalhadas={k: str(v) for k, v in (parsed.get("vendas_detalhadas") or {}).items()},
                    status=StatusImportacaoPDFChoices.SUCESSO,
                    criado_por=usuario if getattr(usuario, "is_authenticated", False) else None,
                )

                for item in parsed["itens"]:
                    CaixaRelatorioItem.objects.create(
                        importacao=importacao,
                        codigo_mercadoria=item["codigo_mercadoria"],
                        descricao=item.get("descricao", ""),
                        quantidade=item["quantidade"],
                    )
        except IntegrityError as exc:
            raise ValidationError(
                "Este PDF ja foi importado para a mesma data e unidade (idempotencia ativa)."
            ) from exc

        resumo_baixa = EstoqueBaixaService.baixar_itens_por_importacao(importacao)
        if resumo_baixa["inconsistentes"] > 0:
            importacao.status = StatusImportacaoPDFChoices.PARCIAL
            importacao.save(update_fields=["status", "atualizado_em"])
        return importacao
