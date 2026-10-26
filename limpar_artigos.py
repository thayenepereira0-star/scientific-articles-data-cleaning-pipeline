import os
import re
import glob
import uuid
from difflib import SequenceMatcher

import pandas as pd
import rispy
import bibtexparser
import xml.etree.ElementTree as ET
from unidecode import unidecode

PASTA_ENTRADA = "entrada"
PASTA_SAIDA = "saida"
os.makedirs(PASTA_SAIDA, exist_ok=True)

COLUNAS_BASE = [
    "title", "authors", "year", "journal", "doi", "pmid",
    "abstract", "keywords", "source_file"
]
COLUNAS_EXPORTACAO = [
    "title", "authors", "year", "journal", "doi", "pmid",
    "abstract", "source_file"
]

# ==========================================
# 1. FUNÇÕES DE LIMPEZA E CRITÉRIOS
# ==========================================

def limpar_texto(txt):
    if txt is None or pd.isna(txt):
        return ""
    txt = str(txt).lower().strip()
    txt = unidecode(txt)
    txt = re.sub(r"[^\w\s]", " ", txt)
    txt = re.sub(r"\s+", " ", txt)
    return txt.strip()


def limpar_abstract(texto):
    if texto is None or pd.isna(texto):
        return ""
    texto = str(texto).replace("\n", " ").replace("\r", " ")
    texto = re.sub(r"\s+", " ", texto).strip()
    if texto.isdigit() or len(texto) < 20:
        return ""
    return texto


def extrair_ano(valor):
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return ""
    m = re.search(r"(19|20)\d{2}", str(valor))
    return m.group(0) if m else ""


def normalizar_doi(doi):
    if doi is None or pd.isna(doi):
        return ""
    doi = str(doi).strip().lower()
    doi = re.sub(r"^\s*(?:https?://(?:dx\.)?doi\.org/|doi\s*:\s*)", "", doi)
    doi = doi.strip().strip(" .;,()[]{}")
    return doi


def normalizar_pmid(pmid):
    if pmid is None or pd.isna(pmid):
        return ""
    m = re.search(r"\d+", str(pmid))
    return m.group(0) if m else ""


def garantir_colunas(df):
    """Garante um schema estável independentemente do formato de entrada."""
    df = df.copy()
    for col in COLUNAS_BASE:
        if col not in df.columns:
            df[col] = ""
    df[COLUNAS_BASE] = df[COLUNAS_BASE].fillna("")
    return df


def eh_tipo_ruim(row):
    campos = [
        str(row.get("title", "")), str(row.get("journal", "")),
        str(row.get("keywords", "")), str(row.get("abstract", ""))
    ]
    texto = unidecode(" ".join(campos).lower())
    termos_ruins = [
        "conference", "congress", "poster", "proceedings", "symposium",
        "meeting abstract", "conference abstract", "abstract book",
        "book of abstracts", "review", "systematic review",
        "literature review", "scoping review", "meta analysis",
        "meta-analysis", "narrative review", "publisher correction",
        "retraction", "corrigendum", "erratum"
    ]
    return any(t in texto for t in termos_ruins)


def score_completude(row):
    score = 0
    score += 100 if str(row.get("title", "")).strip() else 0
    score += 100 if str(row.get("authors", "")).strip() else 0
    score += 100 if str(row.get("doi", "")).strip() else 0
    score += 50 if str(row.get("pmid", "")).strip() else 0
    score += len(str(row.get("abstract", "")))
    if eh_tipo_ruim(row):
        score -= 5000
    return score


# ==========================================
# 2. PARSERS (RIS, BIB, NBIB, CIW, XML, CSV)
# ==========================================

def carregar_ris(caminho):
    with open(caminho, "r", encoding="utf-8", errors="ignore") as f:
        dados = rispy.load(f)
    return [{
        "title": str(r.get("title", "")),
        "authors": "; ".join(r.get("authors", [])) if isinstance(r.get("authors", []), list) else str(r.get("authors", "")),
        "year": extrair_ano(r.get("year", "") or r.get("date", "")),
        "journal": str(r.get("journal_name", "") or r.get("secondary_title", "")),
        "doi": normalizar_doi(r.get("doi", "")),
        "pmid": normalizar_pmid(r.get("pmid", "")),
        "abstract": str(r.get("abstract", "")),
        "keywords": "; ".join(r.get("keywords", [])) if isinstance(r.get("keywords", []), list) else str(r.get("keywords", "")),
        "source_file": os.path.basename(caminho)
    } for r in dados]


def carregar_bib(caminho):
    with open(caminho, "r", encoding="utf-8", errors="ignore") as f:
        raw = f.read()
    # Evita colisões de chaves repetidas no mesmo arquivo BIB.
    raw = re.sub(
        r"(@[a-zA-Z]+\{)([^,]+)(,)",
        lambda m: f"{m.group(1)}{m.group(2)}_{uuid.uuid4().hex[:4]}{m.group(3)}",
        raw
    )
    db = bibtexparser.loads(raw)
    return [{
        "title": r.get("title", ""),
        "authors": r.get("author", "").replace(" and ", "; "),
        "year": extrair_ano(r.get("year", "")),
        "doi": normalizar_doi(r.get("doi", "")),
        "pmid": normalizar_pmid(r.get("pmid", "")),
        "journal": r.get("journal", ""),
        "abstract": r.get("abstract", ""),
        "keywords": r.get("keywords", r.get("keyword", "")),
        "source_file": os.path.basename(caminho)
    } for r in db.entries]


def carregar_formato_tag(caminho, regex_tag, map_tags, tag_inicio):
    saida, registro, tag_atual = [], {}, ""
    with open(caminho, "r", encoding="utf-8", errors="ignore") as f:
        for linha in f:
            linha = linha.rstrip()
            if re.match(tag_inicio, linha) and registro:
                saida.append(registro)
                registro = {}
            match = re.match(regex_tag, linha)
            if match:
                tag_atual = match.group(1).strip()
                registro.setdefault(tag_atual, []).append(match.group(2).strip())
            elif tag_atual and linha.startswith(" "):
                registro[tag_atual][-1] += " " + linha.strip()
    if registro:
        saida.append(registro)

    final = []
    for r in saida:
        item = {"source_file": os.path.basename(caminho)}
        for p, tags in map_tags.items():
            vals = [v for t in tags if t in r for v in r[t]]
            if p == "doi" and vals:
                m = re.search(r"(10\.\d{4,9}/[-._;()/:A-Z0-9]+)", " ".join(vals), re.I)
                item[p] = normalizar_doi(m.group(1)) if m else ""
            elif p == "pmid":
                item[p] = normalizar_pmid(" ".join(vals))
            elif p == "year":
                item[p] = extrair_ano(" ".join(vals))
            else:
                item[p] = "; ".join(vals)
        final.append(item)
    return final


def carregar_xml_pubmed(caminho):
    linhas = []
    root = ET.parse(caminho).getroot()
    for art in root.findall(".//PubmedArticle") + root.findall(".//PubmedBookArticle"):
        doi = ""
        for aid in art.findall(".//ArticleIdList/ArticleId"):
            if aid.get("IdType") == "doi":
                doi = aid.text or ""
        pmid = art.findtext(".//PMID") or ""
        abstract_parts = []
        for node in art.findall(".//AbstractText"):
            abstract_parts.append("".join(node.itertext()).strip())
        linhas.append({
            "title": "".join((art.find(".//ArticleTitle") or ET.Element("x")).itertext()).strip()
                     or art.findtext(".//BookTitle") or "",
            "doi": normalizar_doi(doi),
            "pmid": normalizar_pmid(pmid),
            "abstract": " ".join(p for p in abstract_parts if p),
            "journal": art.findtext(".//Journal/Title") or "",
            "year": extrair_ano(
                art.findtext(".//PubDate/Year")
                or art.findtext(".//PubDate/MedlineDate")
                or ""
            ),
            "source_file": os.path.basename(caminho)
        })
    return linhas


def carregar_csv(caminho):
    df_c = pd.read_csv(caminho, dtype=str).fillna("")
    df_c.columns = [c.lower().strip() for c in df_c.columns]
    res = []
    chaves = {
        "title": ["title", "título", "titulo", "article title"],
        "doi": ["doi"],
        "pmid": ["pmid", "pubmed id"],
        "abstract": ["abstract", "resumo"],
        "authors": ["author", "authors", "autor", "autores"],
        "year": ["year", "ano", "publication year"],
        "journal": ["journal", "source title", "revista", "periódico", "periodico"],
        "keywords": ["keywords", "keyword", "palavras-chave", "palavras chave"]
    }
    for _, r in df_c.iterrows():
        item = {col: "" for col in COLUNAS_BASE}
        item["source_file"] = os.path.basename(caminho)
        for campo, possiveis in chaves.items():
            for p in possiveis:
                if p in df_c.columns:
                    item[campo] = r[p]
                    break
        item["doi"] = normalizar_doi(item["doi"])
        item["pmid"] = normalizar_pmid(item["pmid"])
        item["year"] = extrair_ano(item["year"])
        res.append(item)
    return res


# ==========================================
# 3. LÓGICA DE FUSÃO E DEDUPLICAÇÃO
# ==========================================

def pegar_mais_longo(valores):
    validos = [str(v).strip() for v in valores if pd.notna(v) and str(v).strip()]
    return max(validos, key=len) if validos else ""


def mesclar_grupo(grupo):
    """Escolhe o registro de maior score e usa as cópias para preencher/enriquecer campos."""
    grupo = grupo.sort_values("score", ascending=False)
    mestre = grupo.iloc[0].copy()

    # O abstract mais completo é sempre preservado.
    mestre["abstract"] = pegar_mais_longo(grupo["abstract"])

    # Lacunas do mestre são preenchidas a partir das demais cópias.
    for col in COLUNAS_BASE:
        if col in ("abstract", "source_file"):
            continue
        if not str(mestre.get(col, "")).strip():
            mestre[col] = pegar_mais_longo(grupo[col])

    # Mantém a rastreabilidade de todas as fontes que contribuíram para o mestre.
    fontes = []
    for valor in grupo["source_file"]:
        for fonte in str(valor).split("; "):
            fonte = fonte.strip()
            if fonte and fonte not in fontes:
                fontes.append(fonte)
    mestre["source_file"] = "; ".join(fontes)
    mestre["score"] = score_completude(mestre)
    return mestre


def deduplicar_por_campo(df, campo):
    if campo not in df.columns:
        return df, pd.DataFrame()

    df_com = df[df[campo].astype(str).str.strip() != ""].copy()
    df_sem = df[df[campo].astype(str).str.strip() == ""].copy()
    if df_com.empty:
        return df, pd.DataFrame()

    removidos = df_com[df_com.duplicated(subset=[campo], keep=False)].copy()
    mantidos = []
    for _, grupo in df_com.groupby(campo, sort=False):
        mantidos.append(mesclar_grupo(grupo) if len(grupo) > 1 else grupo.iloc[0])

    df_mantidos = pd.DataFrame(mantidos)
    return pd.concat([df_mantidos, df_sem], ignore_index=True), removidos


def titulos_sao_quase_iguais(a, b):
    """Comparação conservadora para pequenas variações reais de título."""
    a = str(a).strip()
    b = str(b).strip()
    if not a or not b or a == b:
        return False

    wa, wb = a.split(), b.split()
    if min(len(wa), len(wb)) < 4:
        return False

    # Caso típico: mesmo título com um pequeno subtítulo/qualificador adicional.
    menor, maior = (wa, wb) if len(wa) <= len(wb) else (wb, wa)
    if len(menor) >= 6 and len(maior) - len(menor) <= 4 and maior[:len(menor)] == menor:
        return True

    set_a, set_b = set(wa), set(wb)
    cobertura = len(set_a & set_b) / min(len(set_a), len(set_b))
    similaridade = SequenceMatcher(None, a, b).ratio()
    return cobertura >= 0.90 and similaridade >= 0.96


def pode_mesclar_fuzzy(row_a, row_b):
    # Se ambos possuem identificadores e eles discordam, não há fusão fuzzy.
    doi_a, doi_b = str(row_a.get("doi", "")).strip(), str(row_b.get("doi", "")).strip()
    if doi_a and doi_b and doi_a != doi_b:
        return False
    pmid_a, pmid_b = str(row_a.get("pmid", "")).strip(), str(row_b.get("pmid", "")).strip()
    if pmid_a and pmid_b and pmid_a != pmid_b:
        return False

    ano_a, ano_b = str(row_a.get("year", "")).strip(), str(row_b.get("year", "")).strip()
    if not ano_a or not ano_b or ano_a != ano_b:
        return False

    return titulos_sao_quase_iguais(row_a.get("title_norm", ""), row_b.get("title_norm", ""))


def deduplicar_fuzzy_conservador(df):
    """Funde apenas títulos altamente semelhantes, no mesmo ano e sem IDs conflitantes."""
    if df.empty:
        return df, pd.DataFrame()

    df = df.reset_index(drop=True).copy()
    parent = list(range(len(df)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    # Blocking simples para evitar comparar toda a base com toda a base.
    blocos = {}
    for i, row in df.iterrows():
        titulo = str(row.get("title_norm", "")).strip()
        ano = str(row.get("year", "")).strip()
        palavras = titulo.split()
        if len(palavras) < 4 or not ano:
            continue
        chave = (ano, palavras[0])
        blocos.setdefault(chave, []).append(i)

    for indices in blocos.values():
        for pos, i in enumerate(indices):
            for j in indices[pos + 1:]:
                if pode_mesclar_fuzzy(df.iloc[i], df.iloc[j]):
                    union(i, j)

    grupos = {}
    for i in range(len(df)):
        grupos.setdefault(find(i), []).append(i)

    mantidos, removidos = [], []
    for indices in grupos.values():
        grupo = df.iloc[indices]
        if len(indices) > 1:
            mantidos.append(mesclar_grupo(grupo))
            removidos.extend(indices)
        else:
            mantidos.append(grupo.iloc[0])

    removidos_df = df.iloc[removidos].copy() if removidos else pd.DataFrame()
    return pd.DataFrame(mantidos).reset_index(drop=True), removidos_df


# ==========================================
# 4. EXPORTAÇÃO
# ==========================================

def salvar_para_bibtex(df, caminho_saida):
    """Gera um arquivo .bib compatível com Rayyan."""
    with open(caminho_saida, "w", encoding="utf-8") as f:
        for _, row in df.iterrows():
            autor_raw = str(row.get("authors", "Anonimo")).split(";")[0].split(",")[0].strip() or "Anonimo"
            chave_limpa = re.sub(r"\W+", "", unidecode(autor_raw)) or "Anonimo"
            chave = f"{chave_limpa}{row.get('year', '0000')}_{uuid.uuid4().hex[:4]}"
            f.write(f"@article{{{chave},\n")

            for col in COLUNAS_EXPORTACAO:
                valor = str(row.get(col, "")).replace("{", "[").replace("}", "]")
                valor = valor.replace("\n", " ").replace("\r", " ")
                nome_campo = "author" if col == "authors" else col
                if col == "authors":
                    valor = valor.replace(";", " and ")
                f.write(f"  {nome_campo} = {{{valor}}},\n")
            f.write("}\n\n")


def exportar_csv_e_bib(df, nome_base):
    df = garantir_colunas(df)
    df.reindex(columns=COLUNAS_EXPORTACAO).to_csv(
        os.path.join(PASTA_SAIDA, f"{nome_base}.csv"),
        index=False,
        encoding="utf-8-sig"
    )
    salvar_para_bibtex(df, os.path.join(PASTA_SAIDA, f"{nome_base}.bib"))


# ==========================================
# 5. EXECUÇÃO PRINCIPAL
# ==========================================

def main():
    print("\n=== INICIANDO VARREDURA E LIMPEZA ===")
    extensoes = ["*.ris", "*.bib", "*.nbib", "*.ciw", "*.enw", "*.txt", "*.xml", "*.csv"]
    arquivos = []
    for ext in extensoes:
        arquivos.extend(glob.glob(os.path.join(PASTA_ENTRADA, ext)))

    if not arquivos:
        raise SystemExit("Nenhum arquivo encontrado na pasta 'entrada'.")

    registros = []
    for arq in arquivos:
        ext = arq.lower().rsplit(".", 1)[-1]
        regs = []
        try:
            if ext == "ris":
                regs = carregar_ris(arq)
            elif ext == "bib":
                regs = carregar_bib(arq)
            elif ext == "nbib":
                regs = carregar_formato_tag(
                    arq,
                    r"^([A-Z0-9]{2,4})\s*-\s*(.*)",
                    {"title": ["TI"], "authors": ["FAU", "AU"], "year": ["DP"],
                     "doi": ["LID", "AID"], "abstract": ["AB"], "pmid": ["PMID"],
                     "journal": ["JT"], "keywords": ["OT", "MH"]},
                    r"^PMID\s*-"
                )
            elif ext == "ciw":
                regs = carregar_formato_tag(
                    arq,
                    r"^([A-Z0-9]{2})\s+(.*)",
                    {"title": ["TI"], "authors": ["AU", "AF"], "year": ["PY"],
                     "doi": ["DI"], "abstract": ["AB"], "journal": ["SO"],
                     "keywords": ["DE", "ID"]},
                    r"^PT\s"
                )
            elif ext in ["enw", "txt"]:
                regs = carregar_formato_tag(
                    arq,
                    r"^%([A-Z0-9])\s+(.*)",
                    {"title": ["T"], "authors": ["A"], "year": ["D"],
                     "doi": ["R"], "abstract": ["X"], "journal": ["J"],
                     "keywords": ["K"]},
                    r"^%0\s"
                )
            elif ext == "xml":
                regs = carregar_xml_pubmed(arq)
            elif ext == "csv":
                regs = carregar_csv(arq)

            registros.extend(regs)
            print(f"[{ext.upper():>4}] {os.path.basename(arq):<30} -> Leu {len(regs)} artigos.")
        except Exception as e:
            print(f"[ERRO] {os.path.basename(arq)}: {e}")

    if not registros:
        raise SystemExit("Arquivos encontrados, mas nenhum registro pôde ser carregado.")

    df = garantir_colunas(pd.DataFrame(registros))
    total_lido = len(df)

    df["abstract"] = df["abstract"].apply(limpar_abstract)
    df["doi"] = df["doi"].apply(normalizar_doi)
    df["pmid"] = df["pmid"].apply(normalizar_pmid)
    df["year"] = df["year"].apply(extrair_ano)
    df["title_norm"] = df["title"].apply(limpar_texto)
    df["score"] = df.apply(score_completude, axis=1)

    print("\nDeduplicando em 4 fases (DOI, PMID, Título exato e similaridade conservadora)...")
    df, _ = deduplicar_por_campo(df, "doi")
    df, _ = deduplicar_por_campo(df, "pmid")
    df, _ = deduplicar_por_campo(df, "title_norm")
    df, _ = deduplicar_fuzzy_conservador(df)

    total_apos_fusao = len(df)

    print("Auditando termos proibidos e separando descartados...")
    mask_termos = df.apply(eh_tipo_ruim, axis=1)
    df_excluidos_termos = df[mask_termos].copy()
    df = df[~mask_termos].copy()

    mask_sem_doi = df["doi"].astype(str).str.strip() == ""
    df_excluidos_doi = df[mask_sem_doi].copy()
    df = df[~mask_sem_doi].copy()

    mask_sem_abs = df["abstract"].astype(str).str.strip() == ""
    df_excluidos_abs = df[mask_sem_abs].copy()
    df = df[~mask_sem_abs].copy()

    exportar_csv_e_bib(df, "01_base_limpa_final")
    if not df_excluidos_doi.empty:
        exportar_csv_e_bib(df_excluidos_doi, "02_artigos_sem_doi_descartados")
    if not df_excluidos_abs.empty:
        exportar_csv_e_bib(df_excluidos_abs, "03_artigos_incompletos_descartados")
    if not df_excluidos_termos.empty:
        exportar_csv_e_bib(df_excluidos_termos, "04_log_exclusao_por_termo")

    print("\n=== RELATÓRIO FINAL DA LIMPEZA ===")
    print(f"1. Total Lido (Bruto):               {total_lido}")
    print(f"2. Duplicatas Mescladas:             {total_lido - total_apos_fusao}")
    print(f"3. Descartados (Termos Proibidos):   {len(df_excluidos_termos)}")
    print(f"4. Descartados (Sem DOI):            {len(df_excluidos_doi)}")
    print(f"5. Descartados (Sem Abstract):       {len(df_excluidos_abs)}")
    print(f"6. SOBREVIVENTES FINAIS:             {len(df)}")
    print("Todos os arquivos (CSV e BIB) foram gerados na pasta /saida.")
    print("=====================================")


if __name__ == "__main__":
    main()
