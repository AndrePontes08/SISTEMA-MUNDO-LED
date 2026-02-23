from __future__ import annotations

import re
from typing import Any

from financeiro.services.normalizacao_service import NormalizacaoService


class OFXParserService:
    """
    Parser OFX tolerante a SGML sem fechamento de tags.
    Retorna estrutura padrao para importacao.
    """

    _TAG_VALUE = re.compile(r"<(?P<tag>[A-Z0-9_]+)>(?P<value>[^\r\n<]*)", re.IGNORECASE)

    @classmethod
    def parse_bytes(cls, raw: bytes) -> dict[str, Any]:
        text = NormalizacaoService.decode_bytes(raw)
        return cls.parse_text(text)

    @classmethod
    def parse_text(cls, text: str) -> dict[str, Any]:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        blocks = cls._split_blocks(normalized, "STMTRS")
        if not blocks:
            blocks = cls._split_blocks(normalized, "CCSTMTRS")

        statements: list[dict[str, Any]] = []
        alerts: list[str] = []

        for block in blocks:
            statement = cls._parse_statement_block(block)
            if statement["transactions"]:
                statements.append(statement)

        if not statements:
            alerts.append("Nenhuma transacao encontrada no OFX.")

        detected_start = min(
            (s["period_start"] for s in statements if s["period_start"] is not None),
            default=None,
        )
        detected_end = max(
            (s["period_end"] for s in statements if s["period_end"] is not None),
            default=None,
        )

        flattened_transactions: list[dict[str, Any]] = []
        for statement in statements:
            flattened_transactions.extend(statement["transactions"])

        if len(flattened_transactions) == 0:
            alerts.append("Arquivo OFX vazio ou sem movimentos no periodo.")

        return {
            "statements": statements,
            "transactions": flattened_transactions,
            "detected_period_start": detected_start,
            "detected_period_end": detected_end,
            "alerts": alerts,
        }

    @classmethod
    def _parse_statement_block(cls, block: str) -> dict[str, Any]:
        bank_id = cls._extract_tag(block, "BANKID")
        branch_id = cls._extract_tag(block, "BRANCHID")
        account_id = cls._extract_tag(block, "ACCTID")
        account_type = cls._extract_tag(block, "ACCTTYPE")
        period_start = NormalizacaoService.normalizar_data_ofx(cls._extract_tag(block, "DTSTART"))
        period_end = NormalizacaoService.normalizar_data_ofx(cls._extract_tag(block, "DTEND"))

        bank_trn_blocks = cls._split_blocks(block, "STMTTRN")
        transactions: list[dict[str, Any]] = []
        for trn_block in bank_trn_blocks:
            trn_type = NormalizacaoService.normalizar_texto(cls._extract_tag(trn_block, "TRNTYPE")).upper()
            posted_at = NormalizacaoService.normalizar_data_ofx(cls._extract_tag(trn_block, "DTPOSTED"))
            amount = NormalizacaoService.normalizar_decimal(cls._extract_tag(trn_block, "TRNAMT"))
            fitid = NormalizacaoService.normalizar_texto(cls._extract_tag(trn_block, "FITID"))
            memo = NormalizacaoService.normalizar_texto(cls._extract_tag(trn_block, "MEMO"))
            name = NormalizacaoService.normalizar_texto(cls._extract_tag(trn_block, "NAME"))
            checknum = NormalizacaoService.normalizar_texto(cls._extract_tag(trn_block, "CHECKNUM"))
            description = memo or name or "Sem descricao"
            transactions.append(
                {
                    "trn_type": trn_type,
                    "posted_at": posted_at,
                    "amount": amount,
                    "fitid": fitid,
                    "memo": memo,
                    "name": name,
                    "checknum": checknum,
                    "description": description,
                    "account_id": account_id,
                    "bank_id": bank_id,
                    "branch_id": branch_id,
                    "account_type": account_type,
                }
            )

        return {
            "bank_id": bank_id,
            "branch_id": branch_id,
            "account_id": account_id,
            "account_type": account_type,
            "period_start": period_start,
            "period_end": period_end,
            "transactions": transactions,
        }

    @classmethod
    def _split_blocks(cls, text: str, tag: str) -> list[str]:
        tag_upper = tag.upper()
        open_token = f"<{tag_upper}>"
        close_token = f"</{tag_upper}>"
        chunks: list[str] = []

        start = 0
        while True:
            i = text.upper().find(open_token, start)
            if i < 0:
                break
            j = text.upper().find(close_token, i + len(open_token))
            if j >= 0:
                chunks.append(text[i + len(open_token) : j])
                start = j + len(close_token)
            else:
                # Sem fechamento: usa ate abertura do mesmo tag seguinte
                k = text.upper().find(open_token, i + len(open_token))
                if k < 0:
                    chunks.append(text[i + len(open_token) :])
                    break
                chunks.append(text[i + len(open_token) : k])
                start = k
        return chunks

    @classmethod
    def _extract_tag(cls, text: str, tag: str) -> str:
        search = re.search(rf"<{re.escape(tag)}>([^\r\n<]*)", text, re.IGNORECASE)
        return search.group(1).strip() if search else ""

