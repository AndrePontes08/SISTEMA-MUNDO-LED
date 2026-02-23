from __future__ import annotations

import csv
import re
from decimal import Decimal, InvalidOperation
from typing import IO, Optional, List

from django.db import transaction
from django.utils.dateparse import parse_date

from contas.models import ContaAPagar, Categoria, CentroCustoChoices, StatusContaChoices


_RE_R = re.compile(r"R\$\s*", re.IGNORECASE)
_RE_KEEP_NUM = re.compile(r"[^0-9,.\-]")


def parse_decimal_brl_any(text: str) -> Optional[Decimal]:
    if text is None:
        return None
    s = str(text).strip()
    if not s:
        return None

    s = _RE_R.sub("", s)
    s = _RE_KEEP_NUM.sub("", s).strip()
    if not s or s in {"-", ",", "."}:
        return None

    # Ambos separadores: o último costuma ser decimal
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            num = s.replace(".", "").replace(",", ".")
        else:
            num = s.replace(",", "")
    elif "," in s:
        parts = s.split(",")
        if len(parts[-1]) == 2:
            num = s.replace(".", "").replace(",", ".")
        else:
            num = s.replace(",", "")
    elif "." in s:
        parts = s.split(".")
        if len(parts[-1]) == 2:
            num = s.replace(",", "")
        else:
            num = s.replace(".", "")
    else:
        num = s

    try:
        return Decimal(num).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def parse_date_any(text: str):
    """
    aceita:
    - yyyy-mm-dd
    - dd/mm/yyyy
    """
    if text is None:
        return None
    t = str(text).strip()
    if not t:
        return None

    # yyyy-mm-dd
    if re.match(r"^\d{4}-\d{2}-\d{2}$", t):
        return parse_date(t)

    # dd/mm/yyyy
    if re.match(r"^\d{2}/\d{2}/\d{4}$", t):
        dd, mm, yyyy = t.split("/")
        return parse_date(f"{yyyy}-{mm}-{dd}")

    return None


def get_or_create_categoria_default() -> Categoria:
    obj, _ = Categoria.objects.get_or_create(nome="GERAL")
    return obj


def normalize_centro(value: str) -> str:
    v = (value or "").strip().upper()
    v = v.replace(" ", "")
    if v in ("FM", "ML", "PESSOAL"):
        return v
    if v in ("FM/ML", "FMML"):
        return CentroCustoChoices.FM_ML
    return CentroCustoChoices.OUTROS


@transaction.atomic
def import_contas_csv(
    file: IO[str],
    *,
    fonte: str = "CSV",
    exige_comprovante_padrao: bool = False,
    exige_boleto_padrao: bool = False,
    exige_nota_fiscal_padrao: bool = False,
) -> dict:
    """
    CSV esperado (com ;):
      vencimento;descricao;Centro_Custo;valor;Observacao

    - usa SEMPRE a coluna "valor" (não pega NF da descrição)
    - se não existir header, tenta posição fixa (0..4)
    """
    categoria_default = get_or_create_categoria_default()

    raw = file.read()
    # volta cursor
    try:
        file.seek(0)
    except Exception:
        pass

    # detecta delimitador (prioriza ;)
    delimiter = ";" if raw.count(";") >= raw.count(",") else ","
    try:
        file.seek(0)
    except Exception:
        pass

    # tenta DictReader
    reader = csv.reader(file, delimiter=delimiter)
    rows = list(reader)
    if not rows:
        return {"criados": 0, "erros": ["Arquivo vazio."]}

    # detecta header
    header = [h.strip().lstrip("\ufeff") for h in rows[0]]
    has_header = any(h.lower() in ("vencimento", "descricao", "centro_custo", "centro", "valor", "observacao") for h in header)

    criados = 0
    erros: List[str] = []

    hmap = {header[i].strip().lower(): i for i in range(len(header))} if has_header else {}
    aliases = {
        "vencimento": ["vencimento", "data", "data_vencimento"],
        "descricao": ["descricao", "descrição", "historico", "histórico"],
        "centro_custo": ["centro_custo", "centro", "centrodecusto", "cc"],
        "valor": ["valor", "vlr", "valor_r$", "valor_rs"],
        "observacao": ["observacao", "observação", "obs", "observacoes", "observações"],
    }

    # função para pegar colunas por header OU por posição
    def get_col(row, name, idx_default):
        if has_header:
            for key in aliases.get(name, [name]):
                if key in hmap and hmap[key] < len(row):
                    return row[hmap[key]]
            return ""
        else:
            return row[idx_default] if idx_default < len(row) else ""

    start = 1 if has_header else 0
    for idx in range(start, len(rows)):
        row = rows[idx]
        try:
            if not row or all(str(c).strip() == "" for c in row):
                continue

            venc_raw = get_col(row, "vencimento", 0)
            data = parse_date_any(venc_raw)
            if not data:
                # ignora lixo/cabeçalho repetido
                continue

            desc = str(get_col(row, "descricao", 1)).strip()
            centro = normalize_centro(str(get_col(row, "centro_custo", 2)))

            valor_raw = get_col(row, "valor", 3)
            valor = parse_decimal_brl_any(valor_raw)

            # se ainda não achou, tenta procurar em colunas 3..N mas ignora valores sem centavos (evita NF)
            if valor is None:
                for c in row[3:]:
                    v = parse_decimal_brl_any(c)
                    if v is None:
                        continue
                    # regra anti-NF: se for um número gigante e veio de texto solto, provavelmente NF
                    if abs(v) > Decimal("10000000.00"):
                        continue
                    valor = v
                    break

            if valor is None:
                raise ValueError(f"Valor inválido: {valor_raw!r}")

            obs = str(get_col(row, "observacao", 4)).strip()
            if len(obs) > 5000:
                obs = obs[:5000]

            ContaAPagar.objects.create(
                vencimento=data,
                descricao=desc[:255] if desc else "SEM DESCRICAO",
                centro_custo=centro,
                valor=valor,
                status=StatusContaChoices.ABERTA,
                categoria=categoria_default,  # pode trocar depois; mas não é obrigatório no model
                observacoes=obs,
                exige_comprovante=exige_comprovante_padrao,
                exige_boleto=exige_boleto_padrao,
                exige_nota_fiscal=exige_nota_fiscal_padrao,
                importado=True,
                fonte_importacao=fonte,
                linha_importacao=idx + 1,
            )
            criados += 1

        except Exception as e:
            erros.append(f"Linha {idx+1}: {e}")

    return {"criados": criados, "erros": erros}
