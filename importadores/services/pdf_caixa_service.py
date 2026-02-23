from __future__ import annotations

import hashlib
import re
from datetime import datetime
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError

from estoque.models import UnidadeLoja


class PDFCaixaService:
    @staticmethod
    def build_hash(raw: bytes) -> str:
        return hashlib.sha256(raw).hexdigest()

    @classmethod
    def extract_text_from_pdf_bytes(cls, raw: bytes) -> str:
        try:
            from pypdf import PdfReader  # type: ignore
        except Exception as exc:
            raise ValidationError(
                "Biblioteca pypdf nao instalada. Instale com: pip install pypdf"
            ) from exc

        import io

        reader = PdfReader(io.BytesIO(raw))
        pages = [page.extract_text() or "" for page in reader.pages]
        text = "\n".join(pages)
        if not text.strip():
            raise ValidationError("Nao foi possivel extrair texto do PDF informado.")
        return text

    @classmethod
    def parse_caixa_text(
        cls,
        text: str,
        unidade_override: str = "",
        data_override=None,
        source_name: str = "",
    ) -> dict[str, Any]:
        data_ref = data_override or cls._extract_data(text) or cls._extract_data_from_filename(source_name)
        empresa = cls._extract_empresa(text)
        unidade = unidade_override or cls._infer_unidade(text, empresa)
        vendas_detalhadas = cls._extract_vendas_detalhadas(text)
        total_vendas = cls._extract_total_vendas(text) or vendas_detalhadas.get("TOTAL")
        total_trocas = vendas_detalhadas.get("TOTAL_TROCAS", Decimal("0.00"))
        itens = cls._extract_itens_vendidos(text)

        if not data_ref:
            raise ValidationError("Nao foi possivel identificar a data do relatorio no PDF.")
        if not unidade:
            raise ValidationError("Nao foi possivel identificar a unidade (LOJA_1/LOJA_2).")
        if total_vendas is None:
            raise ValidationError("Nao foi possivel identificar o TOTAL de vendas na secao 'Totalizacao do Caixa'.")

        return {
            "data_referencia": data_ref,
            "empresa_nome": empresa,
            "unidade": unidade,
            "total_vendas": total_vendas,
            "total_trocas": total_trocas,
            "vendas_detalhadas": vendas_detalhadas,
            "itens": itens,
        }

    @staticmethod
    def _extract_data(text: str):
        patterns = [
            r"\bData\s*[:\-]?\s*(\d{2}[\/\-.]\d{2}[\/\-.]\d{2,4})",
            r"\bRelatorio\s*[:\-]?\s*(\d{2}[\/\-.]\d{2}[\/\-.]\d{2,4})",
            r"\bPeriodo\s*[:\-]?\s*(\d{2}[\/\-.]\d{2}[\/\-.]\d{2,4})",
            r"\bEmiss[aã]o\s*[:\-]?\s*(\d{2}[\/\-.]\d{2}[\/\-.]\d{2,4})",
            r"\b(\d{2}[\/\-.]\d{2}[\/\-.]\d{4})\b",
        ]
        for pattern in patterns:
            m = re.search(pattern, text, flags=re.IGNORECASE)
            if m:
                parsed = PDFCaixaService._parse_flexible_date(m.group(1))
                if parsed:
                    return parsed
        return None

    @staticmethod
    def _extract_data_from_filename(source_name: str):
        if not source_name:
            return None
        base = source_name.rsplit(".", 1)[0]
        # ddmmyyyy
        m1 = re.search(r"(?<!\d)(\d{2})(\d{2})(\d{4})(?!\d)", base)
        if m1:
            parsed = PDFCaixaService._parse_flexible_date(f"{m1.group(1)}/{m1.group(2)}/{m1.group(3)}")
            if parsed:
                return parsed
        # yyyymmdd
        m2 = re.search(r"(?<!\d)(\d{4})(\d{2})(\d{2})(?!\d)", base)
        if m2:
            try:
                return datetime.strptime(f"{m2.group(1)}-{m2.group(2)}-{m2.group(3)}", "%Y-%m-%d").date()
            except ValueError:
                return None
        return None

    @staticmethod
    def _parse_flexible_date(raw: str):
        if not raw:
            return None
        normalized = raw.strip().replace(".", "/").replace("-", "/")
        for fmt in ("%d/%m/%Y", "%d/%m/%y"):
            try:
                dt = datetime.strptime(normalized, fmt).date()
                if dt.year < 2000:
                    dt = dt.replace(year=dt.year + 2000)
                return dt
            except ValueError:
                continue
        return None

    @staticmethod
    def _extract_empresa(text: str) -> str:
        patterns = [
            r"\bEmpresa\s*[:\-]\s*([A-Za-z0-9\s\/\-\._]+)",
            r"\bUnidade\s*[:\-]\s*([A-Za-z0-9\s\/\-\._]+)",
        ]
        for pattern in patterns:
            m = re.search(pattern, text, flags=re.IGNORECASE)
            if m:
                return m.group(1).strip()[:120]
        return ""

    @staticmethod
    def _infer_unidade(text: str, empresa_nome: str) -> str:
        src = f"{text}\n{empresa_nome}".upper()
        if "MATRIZ" in src or "LOJA 1" in src or "LOJA_1" in src:
            return UnidadeLoja.LOJA_1
        if "FILIAL" in src or "LOJA 2" in src or "LOJA_2" in src:
            return UnidadeLoja.LOJA_2
        return ""

    @staticmethod
    def _extract_total_vendas(text: str) -> Decimal | None:
        section_patterns = [
            r"Totaliza[cç][aã]o do Caixa(.{0,2000})",
            r"TOTALIZA[ÇC][AÃ]O DO CAIXA(.{0,2000})",
        ]
        for sp in section_patterns:
            m = re.search(sp, text, flags=re.IGNORECASE | re.DOTALL)
            if not m:
                continue
            section = m.group(1)
            mv = re.search(
                r"Vendas.{0,400}?TOTAL\s*[:\-]\s*([0-9\.\,]+)",
                section,
                flags=re.IGNORECASE | re.DOTALL,
            )
            if mv:
                return PDFCaixaService._to_decimal_br(mv.group(1))

        fallback = re.findall(r"\bTOTAL\s*[:\-]\s*([0-9\.\,]+)", text, flags=re.IGNORECASE)
        if fallback:
            return PDFCaixaService._to_decimal_br(fallback[-1])
        return None

    @staticmethod
    def _extract_vendas_detalhadas(text: str) -> dict[str, Decimal]:
        details: dict[str, Decimal] = {}
        section = PDFCaixaService._extract_totalizacao_section(text)
        if not section:
            return details

        aliases = {
            "ESPECIE": "ESPECIE",
            "DUPLICATA": "DUPLICATA",
            "BOLETO": "BOLETO",
            "CARTAO DE CREDITO": "CARTAO_CREDITO",
            "CARTAO DE DEBITO": "CARTAO_DEBITO",
            "PIX": "PIX",
            "PIX OFF": "PIX_OFF",
            "TOTAL": "TOTAL",
            "TOTAL TROCAS": "TOTAL_TROCAS",
        }

        line_pattern = re.compile(r"^\s*([^\n\r:]+?)\s*:\s*([0-9\.\,]+)\s*$", re.IGNORECASE | re.MULTILINE)
        for label_raw, value_raw in line_pattern.findall(section):
            label_norm = PDFCaixaService._normalize_label(label_raw)
            canonical = aliases.get(label_norm)
            if not canonical:
                continue
            details[canonical] = PDFCaixaService._to_decimal_br(value_raw)

        return details

    @staticmethod
    def _extract_totalizacao_section(text: str) -> str:
        patterns = [
            r"Totaliza[cç][aã]o do Caixa(.{0,4000})",
            r"TOTALIZA[ÇC][AÃ]O DO CAIXA(.{0,4000})",
        ]
        for pattern in patterns:
            m = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
            if m:
                return m.group(1)
        return text

    @staticmethod
    def _normalize_label(label: str) -> str:
        cleaned = (label or "").upper()
        replacements = {
            "É": "E",
            "Ê": "E",
            "Ã": "A",
            "Á": "A",
            "À": "A",
            "Ç": "C",
            "Í": "I",
            "Ó": "O",
            "Ô": "O",
            "Ú": "U",
        }
        for src, dst in replacements.items():
            cleaned = cleaned.replace(src, dst)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    @staticmethod
    def _extract_itens_vendidos(text: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []

        # Padrão comum: CODIGO DESCRICAO QTD
        line_pattern = re.compile(
            r"^\s*(?P<codigo>\d{3,})\s+(?P<descricao>.+?)\s+(?P<qtd>\d+[\,\.]?\d{0,3})\s*$",
            flags=re.MULTILINE,
        )
        for match in line_pattern.finditer(text):
            qtd = PDFCaixaService._to_decimal_br(match.group("qtd"))
            if qtd <= 0:
                continue
            items.append(
                {
                    "codigo_mercadoria": match.group("codigo").strip(),
                    "descricao": match.group("descricao").strip()[:255],
                    "quantidade": qtd,
                }
            )

        # Remove duplicidades triviais da extração textual
        dedup = {}
        for item in items:
            key = (item["codigo_mercadoria"], item["descricao"], str(item["quantidade"]))
            dedup[key] = item
        return list(dedup.values())

    @staticmethod
    def _to_decimal_br(value: str) -> Decimal:
        txt = (value or "").strip().replace(".", "").replace(",", ".")
        return Decimal(txt).quantize(Decimal("0.01"))
