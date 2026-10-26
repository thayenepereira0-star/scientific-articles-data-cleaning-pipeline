# Scientific Articles Data Cleaning Pipeline

Pipeline em Python para leitura, normalização, deduplicação, fusão de metadados e filtragem de registros bibliográficos provenientes de diferentes bases acadêmicas.

O projeto foi desenvolvido a partir de uma necessidade real de tratamento de dados em revisão sistemática, com foco em **qualidade dos dados, rastreabilidade e redução de trabalho manual antes da triagem**.

> **Importante:** bases bibliográficas reais utilizadas em pesquisa não são versionadas neste repositório. O diretório `entrada/` é ignorado pelo Git para evitar a publicação acidental de dados de pesquisa.

## Visão geral do pipeline

```text
Arquivos bibliográficos
(RIS / BIB / NBIB / CIW / ENW / TXT / XML / CSV)
        ↓
Leitura e padronização de schema
        ↓
Normalização de títulos, DOI, PMID, ano e abstracts
        ↓
Deduplicação por DOI
        ↓
Deduplicação por PMID
        ↓
Deduplicação por título normalizado
        ↓
Comparação conservadora de títulos semelhantes
        ↓
Fusão de metadados e seleção do registro mais completo
        ↓
Filtros de qualidade e tipologia
        ↓
Exportação em CSV e BibTeX
```

## Funcionalidades

- leitura de arquivos `RIS`, `BIB`, `NBIB`, `CIW`, `ENW`, `TXT`, `XML` e `CSV`;
- padronização de estruturas bibliográficas heterogêneas;
- normalização de DOI e PMID;
- limpeza de títulos e abstracts;
- deduplicação em múltiplas etapas;
- bloqueio de fusão quando existem identificadores conflitantes;
- seleção de registro principal por score de completude;
- preenchimento de lacunas com metadados presentes nas duplicatas;
- preservação da origem dos registros por `source_file`;
- separação de registros sem DOI, sem abstract ou fora do escopo;
- exportação dos resultados em `CSV` e `BibTeX`.

## Estratégia de deduplicação

A deduplicação segue uma abordagem conservadora para reduzir o risco de fundir artigos diferentes:

1. **DOI:** identifica registros com o mesmo identificador digital normalizado.
2. **PMID:** identifica registros equivalentes provenientes do PubMed/MEDLINE.
3. **Título normalizado:** compara títulos após remoção de acentos, pontuação e diferenças de capitalização.
4. **Similaridade textual:** avalia títulos muito semelhantes somente quando os critérios de segurança são satisfeitos.

Registros com DOI ou PMID distintos não são fundidos por similaridade de título.

## Fusão de metadados

Quando duplicatas são identificadas, o pipeline não apenas elimina uma das cópias. Ele:

- calcula um score de completude;
- escolhe o registro de maior qualidade como registro principal;
- preserva o abstract mais informativo;
- recupera metadados ausentes a partir das outras cópias;
- mantém a rastreabilidade dos arquivos de origem.

## Estrutura do projeto

```text
scientific-articles-data-cleaning-pipeline/
├── entrada/
│   └── .gitkeep
├── saida/
│   └── .gitkeep
├── limpar_artigos.py
├── requirements.txt
├── .gitignore
└── README.md
```

## Como executar

### 1. Clonar o repositório

```bash
git clone <URL_DO_REPOSITORIO>
cd scientific-articles-data-cleaning-pipeline
```

### 2. Criar um ambiente virtual

No PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Instalar as dependências

```powershell
pip install -r requirements.txt
```

### 4. Adicionar os arquivos de entrada

Coloque os arquivos bibliográficos exportados das bases acadêmicas dentro da pasta:

```text
entrada/
```

### 5. Executar o pipeline

```powershell
python limpar_artigos.py
```

Os resultados serão gerados automaticamente em:

```text
saida/
```

## Arquivos de saída

O pipeline pode gerar:

- `01_base_limpa_final.csv` e `.bib`: registros qualificados após limpeza e deduplicação;
- `02_artigos_sem_doi_descartados.csv` e `.bib`: registros sem DOI;
- `03_artigos_incompletos_descartados.csv` e `.bib`: registros sem abstract;
- `04_log_exclusao_por_termo.csv` e `.bib`: registros removidos por critérios de tipologia.

## Validação

A lógica central foi validada com amostras controladas cobrindo:

- normalização de DOI e PMID;
- leitura de CSV com colunas ausentes;
- leitura de NBIB e XML PubMed;
- deduplicação por identificadores;
- preservação do registro mais completo;
- recuperação de metadados presentes apenas em uma duplicata;
- prevenção de falso positivo quando identificadores são conflitantes;
- comparação de títulos semelhantes;
- exportação em CSV e BibTeX.

Em uma aplicação real que motivou o desenvolvimento do pipeline, uma carga bruta de **7.942 registros bibliográficos** foi reduzida a **5.151 registros únicos** após deduplicação, com diferença de 12 registros em relação à conferência realizada no Rayyan. Esses números representam aquela execução específica e não constituem benchmark universal do algoritmo.

## Limitações

- diferenças severas de grafia ou metadados podem impedir a identificação automática de algumas duplicatas;
- a etapa de similaridade textual foi deliberadamente configurada de forma conservadora para reduzir falsos positivos;
- registros sem DOI são separados do conjunto principal conforme a regra metodológica adotada no projeto original;
- critérios de exclusão por termos dependem do protocolo da revisão e devem ser adaptados antes de reutilizar o pipeline em outros estudos;
- a decisão científica final sobre inclusão ou exclusão de artigos continua sendo responsabilidade dos revisores.

## Tecnologias utilizadas

- Python
- pandas
- rispy
- bibtexparser
- Unidecode
- XML ElementTree

## Possíveis evoluções

- criar uma suíte automatizada de testes com `pytest`;
- adicionar arquivo de configuração para critérios de exclusão;
- registrar estatísticas detalhadas de cada fase da deduplicação;
- adicionar logging estruturado;
- transformar o pipeline em pacote ou ferramenta de linha de comando;
- comparar formalmente precisão e recall da deduplicação contra uma base validada manualmente.

## Uso responsável

Este projeto automatiza tratamento de dados bibliográficos, mas não substitui as decisões metodológicas de uma revisão sistemática. Regras de qualidade e exclusão devem ser definidas de acordo com o protocolo de cada pesquisa.
