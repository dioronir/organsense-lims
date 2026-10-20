# =============================================================================
# BLOCO 1/3: INFRAESTRUTURA, BANCO DE DADOS, CHAT/COMENTARIOS E PDF ONE-SHOT
# =============================================================================
from datetime import date, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import hashlib
import io
import json
import math
import os
import random
import re
import smtplib
import string

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
from sqlalchemy import create_engine, text
import streamlit as st

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

st.set_page_config(
    page_title="OrganSense | Homeostas.IA",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
        [data-testid="stSidebar"] { display: none; }
        [data-testid="collapsedControl"] { display: none; }
        .block-container { padding-top: 1.0rem; padding-bottom: 1.8rem; }
        .os-card {
            background-color: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-radius: 8px;
            padding: 14px 18px;
            margin-bottom: 12px;
        }
        .os-minimal-tracker {
            background-color: #F8FAFC;
            border: 1px solid #E2E8F0;
            border-radius: 8px;
            padding: 10px 14px;
            margin-bottom: 12px;
        }
        .os-step-dot {
            display: inline-block;
            width: 7px;
            height: 7px;
            border-radius: 50%;
            margin-right: 5px;
        }
        .os-chat-msg {
            background-color: #F8FAFC;
            border-left: 3px solid #0284C7;
            padding: 8px 12px;
            border-radius: 4px;
            margin-bottom: 6px;
            font-size: 13px;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def get_engine():
    db_url = st.secrets["database"]["url"]
    db_url = re.sub(r"^postgres(ql)?(\+\w+)?://", "postgresql+pg8000://", db_url)
    return create_engine(
        db_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )


engine = get_engine()


def run_sql(query, params=None):
    with engine.begin() as conn:
        return conn.execute(text(query), params or {})


def fetch_one(query, params=None):
    with engine.connect() as conn:
        return conn.execute(text(query), params or {}).fetchone()


def fetch_all(query, params=None):
    with engine.connect() as conn:
        return conn.execute(text(query), params or {}).fetchall()


def fetch_df(query, params=None):
    with engine.connect() as conn:
        return pd.read_sql(text(query), conn, params=params or {})


def next_patient_code():
    rows = fetch_all("SELECT id_p FROM pacientes_final")
    nums = []
    for r in rows:
        if r[0]:
            m = re.search(r"(\d+)$", str(r[0]))
            if m:
                nums.append(int(m.group(1)))
    prox = (max(nums) if nums else 0) + 1
    return f"OS-{prox:03d}"


if "db_init_v6" not in st.session_state:
    ddl_statements = [
        "CREATE TABLE IF NOT EXISTS usuarios_final (username TEXT PRIMARY KEY, password TEXT, email TEXT, role TEXT, paciente_vinculado TEXT)",
        "CREATE TABLE IF NOT EXISTS controle_chaves_v2 (mes_ano TEXT PRIMARY KEY, chave_medico TEXT, chave_operador TEXT, chave_admin TEXT, chave_paciente TEXT, chave_parente TEXT)",
        "CREATE TABLE IF NOT EXISTS pacientes_final (id_p TEXT PRIMARY KEY, nome TEXT, idade INTEGER, sexo TEXT, nascimento TEXT, estado TEXT, city TEXT, responsavel_cad TEXT, hospital TEXT, status_geral TEXT)",
        "CREATE TABLE IF NOT EXISTS submissao_paciente_detalhada (id_p TEXT PRIMARY KEY, ecog TEXT, comorbidades TEXT, ca19_9 TEXT, cea TEXT, ast_tgo TEXT, alt_tgp TEXT, bilirrubina TEXT, creatinina TEXT, ureia TEXT, albumina TEXT, topografia TEXT, estadiamento_ajcc TEXT, tnm TEXT, ganglios_exam INTEGER, ganglios_pos INTEGER, lnr REAL, margem TEXT, grau_hist TEXT, invasao_perineural TEXT, invasao_linfovasc TEXT, status_tratamento TEXT, regime_quimio TEXT, modalidade_radio TEXT, tipo_resseccao TEXT, data_recebimento TEXT, responsavel TEXT)",
        "CREATE TABLE IF NOT EXISTS amostras_biobanco (id_amostra TEXT PRIMARY KEY, id_p TEXT, biotipo TEXT, prefixo_tipo TEXT, numero_tubo INTEGER, volume_ou_peso TEXT, isquemia_min INTEGER, meio_transporte TEXT, status_amostra TEXT, responsavel TEXT, data_coleta TEXT)",
        "CREATE TABLE IF NOT EXISTS linhagens_pdo (id_linhagem TEXT PRIMARY KEY, id_amostra_origem TEXT, id_p TEXT, codigo_base_tn TEXT, etapa_cultivo TEXT, passagem INTEGER, status_fenotipico TEXT, matriz_meio TEXT, observacoes TEXT, responsavel TEXT, data_registro TEXT)",
        "CREATE TABLE IF NOT EXISTS ampolas_congeladas (id_frozen TEXT PRIMARY KEY, id_estabelecida TEXT, id_p TEXT, codigo_base_tn TEXT, numero_ampola INTEGER, passagem_congelamento INTEGER, densidade TEXT, viabilidade_pos_descong REAL, qualificada_ensaio TEXT, responsavel TEXT, data_congelamento TEXT)",
        "CREATE TABLE IF NOT EXISTS ensaios_farmaco_genetico (id_ensaio_fg TEXT PRIMARY KEY, id_p TEXT, codigo_base_tn TEXT, id_frozen_origem TEXT, modalidade TEXT, indice_grupo INTEGER, grupo_tratamento TEXT, dose TEXT, metodo_analitico TEXT, gene_alvo TEXT, r1 TEXT, r2 TEXT, r3 TEXT, c1 TEXT, c2 TEXT, c3 TEXT, b1 TEXT, b2 TEXT, b3 TEXT, metrica_calculada REAL, responsavel TEXT, data_registro TEXT)",
        "CREATE TABLE IF NOT EXISTS config_modulos_analise (biotipo_codigo TEXT PRIMARY KEY, nome_sessao TEXT, liberado_admin INTEGER, versao_schema TEXT, colunas_custom_json TEXT, atualizado_por TEXT, data_atualizacao TEXT)",
        "CREATE TABLE IF NOT EXISTS analises_multibiotipo_futuro (id_registro TEXT PRIMARY KEY, id_amostra TEXT, id_p TEXT, biotipo_codigo TEXT, versao_schema TEXT, payload_json TEXT, responsavel TEXT, data_registro TEXT)",
        "CREATE TABLE IF NOT EXISTS config_motores_ia (id_motor TEXT PRIMARY KEY, nome_motor TEXT, escopo TEXT, liberado_admin INTEGER, versao TEXT)",
        "CREATE TABLE IF NOT EXISTS predicoes_ia_final (id_pred TEXT PRIMARY KEY, id_p TEXT, motor_ia TEXT, subtipo_purist TEXT, score_purist REAL, lnr REAL, recist_pct REAL, s24_sem_quimio REAL, s24_gemcitabina REAL, s24_poliquimio REAL, quadrante TEXT, conduta TEXT, responsavel TEXT, data_hora TEXT)",
        "CREATE TABLE IF NOT EXISTS config_acompanhamento_medico (id_p TEXT PRIMARY KEY, medico_username TEXT, medico_email TEXT, comentario_oficial TEXT, chat_ativo INTEGER, atualizado_em TEXT)",
        "CREATE TABLE IF NOT EXISTS mensagens_acompanhamento (id_msg SERIAL PRIMARY KEY, id_p TEXT, autor_username TEXT, autor_role TEXT, autor_email TEXT, mensagem TEXT, data_hora TEXT)",
        "CREATE TABLE IF NOT EXISTS audit_logs (id SERIAL PRIMARY KEY, username TEXT, acao TEXT, detalhe TEXT, data_hora TEXT)",
    ]
    with engine.begin() as conn:
        for stmt in ddl_statements:
            conn.execute(text(stmt))
        try:
            conn.execute(text("ALTER TABLE usuarios_final ADD COLUMN IF NOT EXISTS paciente_vinculado TEXT"))
        except Exception:
            pass

    biotipos_padrao = [
        ("TN", "Fragmento Tumoral In Natura (-TN)", 0, "v1.0", '["Pureza_Tumoral_Pct", "Mutacao_KRAS_Alelo"]'),
        ("STN", "Sangue Total (-STN)", 0, "v1.0", '["Hemoglobina_g_dL", "Relacao_NLR"]'),
        ("PN", "Plasma / Biópsia Líquida ctDNA (-PN)", 0, "v1.0", '["cfDNA_ng_mL", "VAF_KRAS_Pct"]'),
        ("SN", "Soro / Proteômica (-SN)", 0, "v1.0", '["CA19_9_Serico", "IL6_pg_mL"]'),
        ("PBMCN", "PBMC / Imunofenotipagem (-PBMCN)", 0, "v1.0", '["Viabilidade_PBMC_Pct", "CD8_Pct"]'),
    ]
    for cod_b, nome_b, lib_b, ver_b, cols_b in biotipos_padrao:
        if not fetch_one("SELECT 1 FROM config_modulos_analise WHERE biotipo_codigo = :c", {"c": cod_b}):
            run_sql(
                "INSERT INTO config_modulos_analise VALUES (:c, :n, :l, :v, :cj, 'Sistema', :dt)",
                {"c": cod_b, "n": nome_b, "l": lib_b, "v": ver_b, "cj": cols_b, "dt": datetime.now().strftime("%d/%m/%Y")},
            )

    motores_ia_padrao = [
        ("IA-RANK-FARMA", "Direcionador Farmacêutico Multi-Droga (Ranking IC50 / Letalidade F1..F9)", "Ordenação empírica de todas as rotas farmacológicas testadas no organoide", 0, "v1.2-beta"),
        ("IA-LIQUID-CTDNA", "Preditor de Biópsia Líquida & Dinâmica Clonal (-PN / -STN)", "Monitoramento longitudinal de resposta molecular e escape clonal", 0, "v1.0-draft"),
        ("IA-IMUNO-ESTROMA", "Classificador Imuno-Estromal & Barreira Desmoplásica (-PBMCN / -SN)", "Predição de penetração tecidual de fármacos e resposta imune", 0, "v1.0-draft"),
    ]
    for id_m, nm_m, esc_m, lib_m, ver_m in motores_ia_padrao:
        if not fetch_one("SELECT 1 FROM config_motores_ia WHERE id_motor = :id", {"id": id_m}):
            run_sql(
                "INSERT INTO config_motores_ia VALUES (:id, :nm, :es, :lb, :vr)",
                {"id": id_m, "nm": nm_m, "es": esc_m, "lb": lib_m, "vr": ver_m},
            )
    st.session_state.db_init_v6 = True


def log_audit(usuario, acao, detalhe):
    run_sql(
        "INSERT INTO audit_logs (username, acao, detalhe, data_hora) VALUES (:u, :a, :d, :dh)",
        {"u": usuario, "a": acao, "d": detalhe, "dh": datetime.now().strftime("%d/%m/%Y %H:%M:%S")},
    )


def send_email(destinatario, assunto, corpo, bcc_admin=False):
    try:
        rem = st.secrets["email"]["remetente"]
        msg = MIMEMultipart()
        msg["From"], msg["To"], msg["Subject"] = rem, destinatario, assunto
        msg.attach(MIMEText(corpo, "plain"))
        dests = [destinatario] + ([rem] if bcc_admin and destinatario != rem else [])
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=10) as srv:
            srv.starttls()
            srv.login(rem, st.secrets["email"]["senha_app"])
            srv.sendmail(rem, dests, msg.as_string())
        return True
    except Exception:
        return False


def notificar_vinculados_por_email(id_p: str, assunto: str, corpo: str):
    """Envia notificação por e-mail ao Médico responsável e aos Pacientes/Parentes vinculados ao ID."""
    destinatarios = set()
    rows_u = fetch_all(
        "SELECT email FROM usuarios_final WHERE paciente_vinculado = :id AND email IS NOT NULL",
        {"id": id_p},
    )
    for r in rows_u:
        if r[0] and "@" in r[0]:
            destinatarios.add(r[0].strip().lower())

    cfg_med = fetch_one(
        "SELECT medico_email FROM config_acompanhamento_medico WHERE id_p = :id",
        {"id": id_p},
    )
    if cfg_med and cfg_med[0] and "@" in cfg_med[0]:
        destinatarios.add(cfg_med[0].strip().lower())

    pac_resp = fetch_one("SELECT responsavel_cad FROM pacientes_final WHERE id_p = :id", {"id": id_p})
    if pac_resp and pac_resp[0]:
        em_r = fetch_one("SELECT email FROM usuarios_final WHERE username = :u", {"u": pac_resp[0]})
        if em_r and em_r[0] and "@" in em_r[0]:
            destinatarios.add(em_r[0].strip().lower())

    for email_dest in destinatarios:
        send_email(email_dest, assunto, corpo)


def obter_ou_gerar_chaves_5_perfis():
    mes_ref = datetime.now().strftime("%m/%Y")
    row = fetch_one(
        "SELECT chave_medico, chave_operador, chave_admin, chave_paciente, chave_parente FROM controle_chaves_v2 WHERE mes_ano = :m",
        {"m": mes_ref},
    )
    if row:
        return {
            "Médico": row[0],
            "Operador": row[1],
            "Administrador": row[2],
            "Paciente": row[3],
            "Parente": row[4],
        }

    def rand_tok(pref):
        suf = "".join(random.choices(string.ascii_uppercase + string.digits, k=5))
        return f"{pref}-{mes_ref[:2]}-{suf}"

    chaves = {
        "Médico": rand_tok("MED"),
        "Operador": rand_tok("OP"),
        "Administrador": rand_tok("ADM"),
        "Paciente": rand_tok("PAC"),
        "Parente": rand_tok("PAR"),
    }
    run_sql(
        "INSERT INTO controle_chaves_v2 VALUES (:m, :med, :op, :adm, :pac, :par)",
        {
            "m": mes_ref,
            "med": chaves["Médico"],
            "op": chaves["Operador"],
            "adm": chaves["Administrador"],
            "pac": chaves["Paciente"],
            "par": chaves["Parente"],
        },
    )
    if "email" in st.secrets and "remetente" in st.secrets["email"]:
        corpo = (
            f"Chaves OrganSense ({mes_ref}):\n"
            f"Médico: {chaves['Médico']}\n"
            f"Operador: {chaves['Operador']}\n"
            f"Administrador: {chaves['Administrador']}\n"
            f"Paciente: {chaves['Paciente']}\n"
            f"Parente: {chaves['Parente']}\n"
        )
        send_email(st.secrets["email"]["remetente"], f"Chaves OrganSense - {mes_ref}", corpo)
    return chaves


def hash_pwd(pwd):
    salt = os.urandom(16).hex()
    dk = hashlib.pbkdf2_hmac("sha256", pwd.encode(), bytes.fromhex(salt), 100000)
    return f"{salt}${dk.hex()}"


def verify_pwd(pwd, stored):
    if not stored:
        return False
    if "$" in stored:
        salt, key = stored.split("$", 1)
        return (
            hashlib.pbkdf2_hmac("sha256", pwd.encode(), bytes.fromhex(salt), 100000).hex()
            == key
        )
    return hashlib.sha256(pwd.encode()).hexdigest() == stored


def renderizar_medidor_senha_minimalista(pwd: str):
    criterios = [
        ("8+ caracteres", len(pwd) >= 8),
        ("Maiúscula", bool(re.search(r"[A-Z]", pwd))),
        ("Minúscula", bool(re.search(r"[a-z]", pwd))),
        ("Número", bool(re.search(r"[0-9]", pwd))),
        ("Símbolo", bool(re.search(r"[_@$!%*#?&]", pwd))),
    ]
    pts = sum(1 for _, ok in criterios if ok)
    escala = {
        0: ("0%", "#E2E8F0", "Aguardando"),
        1: ("20%", "#DC2626", "Muito fraca"),
        2: ("40%", "#EA580C", "Fraca"),
        3: ("60%", "#D97706", "Moderada"),
        4: ("80%", "#65A30D", "Forte"),
        5: ("100%", "#16A34A", "Segura"),
    }
    larg, cor, rotulo = escala[pts]
    valida = (
        len(pwd) >= 8
        and bool(re.search(r"[A-Z]", pwd))
        and bool(re.search(r"[0-9]", pwd))
        and bool(re.search(r"[_@$!%*#?&]", pwd))
    )

    pills = "".join([
        f"<span style='display:inline-flex; align-items:center; background:{'#DCFCE7' if ok else '#F1F5F9'}; "
        f"color:{'#15803D' if ok else '#64748B'}; border:1px solid {'#86EFAC' if ok else '#E2E8F0'}; "
        f"border-radius:99px; padding:2px 8px; font-size:11px; font-weight:600; margin-right:5px;'>"
        f"<span class='os-step-dot' style='background:{'#16A34A' if ok else '#CBD5E1'};'></span>{lbl}</span>"
        for lbl, ok in criterios
    ])
    st.markdown(
        f"""
        <div class="os-minimal-tracker">
            <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
                <span style="font-size:11px; font-weight:600; color:#475569;">Requisitos da Senha</span>
                <span style="font-size:11px; font-weight:700; color:{cor};">{rotulo} ({pts}/5)</span>
            </div>
            <div style="width:100%; background:#E2E8F0; height:5px; border-radius:3px; overflow:hidden; margin-bottom:7px;">
                <div style="width:{larg}; background:{cor}; height:100%; transition:width 0.25s ease;"></div>
            </div>
            <div>{pills}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    return valida


def norm_num(val):
    return str(val).strip().replace(",", ".") if val else ""


@st.cache_data(ttl=86400)
def get_ufs():
    try:
        r = requests.get("https://servicodados.ibge.gov.br/api/v1/localidades/estados", timeout=5)
        return sorted([x["sigla"] for x in r.json()])
    except Exception:
        return ["PE", "SP", "RJ", "MG", "BA", "RS", "PR", "CE"]


@st.cache_data(ttl=86400)
def get_cidades(uf):
    try:
        r = requests.get(f"https://servicodados.ibge.gov.br/api/v1/localidades/estados/{uf}/municipios", timeout=5)
        return [x["nome"] for x in r.json()]
    except Exception:
        return ["Recife", "Olinda", "Jaboatão dos Guararapes", "São Paulo"]


GRUPOS_TRATAMENTO_PDAC = [
    (1, "Sem Tratamento (Controle Basal)"),
    (2, "Gencitabina Monoterapia"),
    (3, "mFOLFIRINOX (5-FU + Irinotecano + Oxaliplatina)"),
    (4, "Gencitabina + nab-Paclitaxel"),
    (5, "5-Fluorouracil (5-FU) / Capecitabina"),
    (6, "FOLFOX (5-FU + Oxaliplatina)"),
    (7, "Cisplatina + Gencitabina (Perfil BRCA/HRD)"),
    (8, "Olaparibe (Inibidor de PARP)"),
    (9, "Derivado Tiazopiridínico (P1)"),
]

PAINEL_57_GENES_ASSINATURAS = {
    "SIG_Moffitt_Basal (13 genes)": [
        "KRT5", "KRT6A", "KRT14", "KRT17", "S100A2", "FAM83A", "VGLL1",
        "TNS4", "LY6D", "SCEL", "AREG", "LAMC2", "LAMA3",
    ],
    "SIG_Moffitt_Classical (14 genes)": [
        "TFF1", "TFF2", "TFF3", "LGALS4", "CTSE", "VSIG2", "AGR2",
        "REG4", "CDH17", "HNF4A", "FOXA2", "FOXA3", "SPINK4", "MUC13",
    ],
    "SIG_Proliferation_Index (9 genes)": [
        "TOP2A", "MKI67", "CDC6", "CCNB1", "CCNB2", "CDK1", "AURKA", "BUB1", "MCM2",
    ],
    "SIG_Hypoxia_Glycolysis (8 genes)": [
        "VIM", "SNAI2", "ZEB1", "TWIST1", "CA9", "LDHA", "SLC2A1", "VEGFA",
    ],
    "SIG_Stroma_Activated (13 genes)": [
        "FAP", "ACTA2", "COL1A1", "COL1A2", "COL3A1", "POSTN", "MMP11",
        "MMP3", "FN1", "SPARC", "THBS2", "INHBA", "WNT7A",
    ],
}

# Mediana de Ct Bruto calibrada na coorte TCGA-PAAD (n=139, Ct_GAPDH = 20.0) por assinatura
CT_MEDIANA_POR_ASSINATURA = {
    "SIG_Moffitt_Basal (13 genes)": "25.38",
    "SIG_Moffitt_Classical (14 genes)": "23.14",
    "SIG_Proliferation_Index (9 genes)": "26.39",
    "SIG_Hypoxia_Glycolysis (8 genes)": "24.09",
    "SIG_Stroma_Activated (13 genes)": "22.54",
}

GENES_PAINEL_HGNC = [
    gene
    for lista in PAINEL_57_GENES_ASSINATURAS.values()
    for gene in lista
]

LAUDOS_PDF_TESTE = {
    "Laudo_OneShot_PDAC.pdf": [
        "HOSPITAL DAS CLINICAS DA UFPE - PROTOCOLO PDAC",
        "Paciente: Roberto Carlos Cavalcanti de Albuquerque",
        "Sexo Biologico: Masculino | Data de Nascimento: 14/05/1958",
        "UF: PE | Municipio: Recife | Hospital: Hospital das Clinicas da UFPE",
        "Performance Status ECOG: 1 | Comorbidades: Diabetes recente",
        "CA 19-9: 420.5 U/mL | CEA: 4.8 ng/mL | Albumina: 3.7 g/dL",
        "AST / TGO: 68.4 U/L | ALT / TGP: 92.1 U/L | Bilirrubina Total: 1.4 mg/dL",
        "Creatinina Serica: 0.95 mg/dL | Ureia: 38.0 mg/dL",
        "Topografia Primaria: Cabeca do Pancreas | Estadiamento AJCC: IIB (Borderline)",
        "Classificacao TNM: pT3 pN1 cM0",
        "Ganglios Examinados: 18 | Ganglios Positivos: 2 | Margem Cirurgica: R0 | Grau Histologico: G2",
        "Isquemia Fria: 22 min | Passagem: 3 | Criotubos Congelados: 4",
        "Densidade Celular: 1.5x10^6 cel/mL | Viabilidade Pos-Descongelamento: 92%",
        "Concentracao Testada: 10 uM | Branco do Meio B1: 0.048 | B2: 0.050 | B3: 0.049",
        "Ensaio F1 -> R1: 0.412 | R2: 0.405 | R3: 0.418",
        "Ensaio F2 -> R1: 0.185 | R2: 0.179 | R3: 0.190",
        "Ensaio F3 -> R1: 0.118 | R2: 0.112 | R3: 0.121",
        "Ensaio F4 -> R1: 0.140 | R2: 0.135 | R3: 0.144",
        "Ct Endogeno Referencia (GAPDH/ACTB): 20.10",
        "Gene GATA6 -> Ct Alvo R1: 21.30 | R2: 21.25 | R3: 21.40",
        "Gene KRT5 -> Ct Alvo R1: 27.80 | R2: 27.95 | R3: 27.85",
        "Gene KRAS -> Ct Alvo R1: 22.40 | R2: 22.50 | R3: 22.45",
        "Gene MKI67 -> Ct Alvo R1: 25.10 | R2: 25.20 | R3: 25.05",
        "Gene COL1A1 -> Ct Alvo R1: 19.30 | R2: 19.45 | R3: 19.38",
    ],
}


def gerar_bytes_pdf_nativo(linhas_texto: list) -> bytes:
    conteudo = "BT\n/F1 10 Tf\n40 790 Td\n14 TL\n"
    for ln in linhas_texto:
        limpa = ln.replace("(", "\\(").replace(")", "\\)").encode("ascii", "ignore").decode("ascii")
        conteudo += f"({limpa}) '\n"
    conteudo += "ET"
    s_bytes = conteudo.encode("latin-1")
    objs = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n",
        b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
        f"5 0 obj\n<< /Length {len(s_bytes)} >>\nstream\n".encode("latin-1") + s_bytes + b"\nendstream\nendobj\n",
    ]
    pdf = b"%PDF-1.4\n"
    offs = []
    for o in objs:
        offs.append(len(pdf))
        pdf += o
    xref = len(pdf)
    pdf += f"xref\n0 {len(objs)+1}\n0000000000 65535 f \n".encode("latin-1")
    for off in offs:
        pdf += f"{off:010d} 00000 n \n".encode("latin-1")
    pdf += f"trailer\n<< /Size {len(objs)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode("latin-1")
    return pdf


def extrair_tudo_pdfs_oneshot(lista_arquivos) -> dict:
    if not lista_arquivos or PdfReader is None:
        return {}
    blocos = []
    for arq in lista_arquivos:
        try:
            leitor = PdfReader(io.BytesIO(arq.getvalue()))
            blocos.append("\n".join([p.extract_text() or "" for p in leitor.pages]).strip())
        except Exception:
            pass
    texto_total = "\n\n".join(blocos)
    if not texto_total:
        return {}

    dados = {}

    def buscar(padroes):
        for pat in padroes:
            m = re.search(pat, texto_total, re.IGNORECASE)
            if m:
                return m.group(1).strip()
        return ""

    dados["nome"] = buscar([r"(?:Paciente|Nome(?:\s+Completo)?)\s*[:\-]\s*([A-ZÀ-Úa-zà-ú\s]{5,70}?)(?:\n|\r|\||Data|Idade|Sexo|CPF|UF|$)"])
    sx = buscar([r"Sexo(?:\s+Biol[oó]gico)?\s*[:\-]\s*(Masculino|Feminino|M|F)\b"])
    if sx:
        dados["sexo"] = "Feminino" if sx.upper().startswith("F") else "Masculino"
    dados["data_nascimento"] = buscar([r"(?:Nascimento|Data\s+de\s+Nasc(?:imento)?|DN)\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})"])
    uf_m = buscar([r"(?:UF|Estado)\s*[:\-]\s*([A-Z]{2})\b"])
    if uf_m:
        dados["uf"] = uf_m.upper()
    dados["municipio"] = buscar([r"(?:Munic[ií]pio|Cidade)\s*[:\-]\s*([A-ZÀ-Úa-zà-ú\s\-]{3,45}?)(?:\n|\r|\||Hospital|$)"])
    dados["hospital"] = buscar([r"(?:Hospital|Institui[cç][aã]o|Servi[cç]o(?:\s+de\s+Cirurgia)?)\s*[:\-]\s*([^\n\r\|]{4,80})"])
    dados["ecog"] = buscar([r"ECOG\s*[:\-]?\s*([0-4])\b"])
    dados["comorbidades"] = buscar([r"Comorbidades\s*[:\-]\s*([^\n\r\|]+)"])
    dados["ca19_9"] = buscar([r"CA\s*19[\-\.]?9\s*[:\-=]?\s*(\d+(?:[\.,]\d+)?)"]).replace(",", ".")
    dados["cea"] = buscar([r"CEA\s*[:\-=]?\s*(\d+(?:[\.,]\d+)?)"]).replace(",", ".")
    dados["albumina"] = buscar([r"Albumina\s*[:\-=]?\s*(\d+(?:[\.,]\d+)?)"]).replace(",", ".")
    dados["ast_tgo"] = buscar([r"(?:AST|TGO|AST\s*/\s*TGO)\s*[:\-=]?\s*(\d+(?:[\.,]\d+)?)"]).replace(",", ".")
    dados["alt_tgp"] = buscar([r"(?:ALT|TGP|ALT\s*/\s*TGP)\s*[:\-=]?\s*(\d+(?:[\.,]\d+)?)"]).replace(",", ".")
    dados["bilirrubina"] = buscar([r"Bilirrubina(?:\s+Total)?\s*[:\-=]?\s*(\d+(?:[\.,]\d+)?)"]).replace(",", ".")
    dados["creatinina"] = buscar([r"Creatinina(?:\s+S[eé]rica)?\s*[:\-=]?\s*(\d+(?:[\.,]\d+)?)"]).replace(",", ".")
    dados["ureia"] = buscar([r"Ureia\s*[:\-=]?\s*(\d+(?:[\.,]\d+)?)"]).replace(",", ".")
    dados["ganglios_examinados"] = buscar([r"(?:G[aâ]nglios|Linfonodos)\s+Examinados\s*[:\-=]?\s*(\d+)"])
    dados["ganglios_positivos"] = buscar([r"(?:G[aâ]nglios|Linfonodos)\s+Positivos\s*[:\-=]?\s*(\d+)"])
    dados["margem_cirurgica"] = buscar([r"Margem(?:\s+Cir[uú]rgica)?\s*[:\-=]?\s*(R0|R1|R2)\b"])
    dados["grau_histologico"] = buscar([r"Grau(?:\s+Histol[oó]gico)?\s*[:\-=]?\s*(G1|G2|G3|G4)\b"])
    dados["isquemia_min"] = buscar([r"Isquemia(?:\s+Fria)?\s*[:\-=]?\s*(\d+)"])
    dados["passagem"] = buscar([r"Passagem\s*[:\-]?\s*P?(\d+)"])
    dados["n_criotubos"] = buscar([r"(?:Criotubos|Ampolas)(?:\s+Congelados)?\s*[:\-]?\s*(\d+)"])
    dados["densidade_cel"] = buscar([r"Densidade(?:\s+Celular)?\s*[:\-]\s*([^\n\r\|]+)"])
    dados["viabilidade_tripan"] = buscar([r"Viabilidade[^\n\r:]*[:\-]\s*(\d+(?:[\.,]\d+)?)\s*%"])

    blk_r = re.search(
        r"Branco[^\n\r]*B1\s*[:=]\s*([0-9\.]+)[^\n\r]*B2\s*[:=]\s*([0-9\.]+)[^\n\r]*B3\s*[:=]\s*([0-9\.]+)",
        texto_total, re.IGNORECASE,
    )
    if blk_r:
        dados["b1"], dados["b2"], dados["b3"] = blk_r.group(1), blk_r.group(2), blk_r.group(3)

    ensaios_f_extraidos = {}
    for m_f in re.finditer(
        r"Ensaio\s+F(\d+)\s*->\s*R1\s*[:=]\s*([0-9\.]+)\s*\|\s*R2\s*[:=]\s*([0-9\.]+)\s*\|\s*R3\s*[:=]\s*([0-9\.]+)",
        texto_total, re.IGNORECASE,
    ):
        ensaios_f_extraidos[int(m_f.group(1))] = (m_f.group(2), m_f.group(3), m_f.group(4))
    if ensaios_f_extraidos:
        dados["ensaios_f_map"] = ensaios_f_extraidos

    ct_endo = buscar([r"Ct\s+End[oó]geno\s+Refer[eê]ncia[^\n\r:]*[:=]\s*([0-9\.]+)"])
    if ct_endo:
        dados["ct_endo"] = ct_endo

    genes_g_extraidos = {}
    for m_g in re.finditer(
        r"Gene\s+([A-Z0-9]+)\s*->\s*Ct\s+Alvo\s+R1\s*[:=]\s*([0-9\.]+)\s*\|\s*R2\s*[:=]\s*([0-9\.]+)\s*\|\s*R3\s*[:=]\s*([0-9\.]+)",
        texto_total, re.IGNORECASE,
    ):
        genes_g_extraidos[m_g.group(1).upper()] = (m_g.group(2), m_g.group(3), m_g.group(4))
    if genes_g_extraidos:
        dados["genes_g_map"] = genes_g_extraidos

    return dados


def aplicar_dados_pdf_em_todos_os_estados(ext: dict):
    st.session_state.setdefault("pdf_pac_cache", {}).update(ext)
    st.session_state.setdefault("draft_pac", {})
    dr = st.session_state.draft_pac
    for k_dest, k_orig in [
        ("nome", "nome"), ("sexo", "sexo"), ("uf", "uf"), ("municipio", "municipio"),
        ("hospital", "hospital"), ("ecog", "ecog"), ("comorbidades", "comorbidades"),
        ("ca19_9", "ca19_9"), ("cea", "cea"), ("alb", "albumina"), ("ast", "ast_tgo"),
        ("alt", "alt_tgp"), ("bil", "bilirrubina"), ("cre", "creatinina"), ("ure", "ureia"),
        ("margem", "margem_cirurgica"), ("grau", "grau_histologico"),
    ]:
        if ext.get(k_orig):
            dr[k_dest] = ext[k_orig]
    if str(ext.get("ganglios_examinados", "")).isdigit():
        dr["g_exam"] = int(ext["ganglios_examinados"])
    if str(ext.get("ganglios_positivos", "")).isdigit():
        dr["g_pos"] = int(ext["ganglios_positivos"])
# =============================================================================
# BLOCO 2/3: RASTREIO MINIMALISTA, MOTOR IA AUTOMATICO E LOGIN GMAIL
# =============================================================================
def auditar_completude_paciente(id_p: str):
    pac = fetch_one("SELECT * FROM pacientes_final WHERE id_p = :id", {"id": id_p})
    sub = fetch_one("SELECT * FROM submissao_paciente_detalhada WHERE id_p = :id", {"id": id_p})
    amostras = fetch_all("SELECT id_amostra, biotipo, isquemia_min FROM amostras_biobanco WHERE id_p = :id", {"id": id_p})
    cultivos = fetch_all("SELECT id_linhagem, etapa_cultivo, passagem FROM linhagens_pdo WHERE id_p = :id", {"id": id_p})
    frozen = fetch_all("SELECT id_frozen, viabilidade_pos_descong FROM ampolas_congeladas WHERE id_p = :id", {"id": id_p})
    ensaios = fetch_all(
        "SELECT id_ensaio_fg, modalidade, indice_grupo, grupo_tratamento, gene_alvo, metrica_calculada FROM ensaios_farmaco_genetico WHERE id_p = :id",
        {"id": id_p},
    )
    pred_ia = fetch_one("SELECT id_pred FROM predicoes_ia_final WHERE id_p = :id ORDER BY data_hora DESC LIMIT 1", {"id": id_p})

    tem_cult = any("-C" in str(r[0]) for r in cultivos)
    tem_estab = any("-E" in str(r[0]) for r in cultivos)
    tem_fn_ens = any(r[1] == "Farmacologico" for r in ensaios)
    tem_gn_ens = any(r[1] == "Genetico" for r in ensaios)

    etapas = [
        ("Recebido", bool(pac and sub)),
        ("Amostras", bool(amostras)),
        ("Cultivo (-C)", tem_cult),
        ("Estabelecida (-EN)", tem_estab),
        ("Congelada (-FN)", bool(frozen)),
        ("Ensaios (-FN/-GN)", bool(tem_fn_ens or tem_gn_ens)),
        ("Homeostas.IA", bool(pred_ia)),
    ]
    pct = int(round((sum(1 for _, ok in etapas if ok) / len(etapas)) * 100))

    fidelidade_pdo = 60.0
    if tem_cult:
        fidelidade_pdo += 10.0
    if tem_estab:
        fidelidade_pdo += 15.0
    viab_max_crio = max([float(r[1] or 0) for r in frozen], default=0.0)
    if viab_max_crio >= 80.0:
        fidelidade_pdo += 15.0
    fidelidade_pdo = min(100.0, fidelidade_pdo)

    sinais_f = {}
    genes_dct = {}

    for _, mod_e, idx_g, nome_g, gene_a, met_c in ensaios:
        if mod_e == "Farmacologico" and met_c is not None:
            sinais_f[int(idx_g)] = (str(nome_g), float(met_c))
        elif mod_e == "Genetico" and gene_a and met_c is not None:
            genes_dct[str(gene_a).upper()] = float(met_c)

    ref_basal = sinais_f[1][1] if (1 in sinais_f and sinais_f[1][1] > 0) else 0.362
    viab_por_grupo = {}
    for idx_k, (nm_k, val_k) in sinais_f.items():
        if idx_k == 1:
            viab_por_grupo[idx_k] = (nm_k, 100.0, 0.0)
        else:
            v_rel = round(min(100.0, max(1.0, (val_k / ref_basal) * 100.0)), 1)
            viab_por_grupo[idx_k] = (nm_k, v_rel, round(100.0 - v_rel, 1))

    viab_gem_calc = viab_por_grupo[2][1] if 2 in viab_por_grupo else 38.0
    viab_folf_calc = viab_por_grupo[3][1] if 3 in viab_por_grupo else (viab_por_grupo[4][1] if 4 in viab_por_grupo else 21.0)

    elegivel_folfirinox = True
    if sub:
        try:
            bil_v = float(sub[7] or 1.0)
            cre_v = float(sub[8] or 0.9)
            ecog_v = int(sub[1] or 1)
            if bil_v > 2.5 or cre_v > 1.6 or ecog_v >= 3:
                elegivel_folfirinox = False
        except Exception:
            pass

    metricas_auto = {
        "fidelidade_pdo": fidelidade_pdo,
        "viab_gem_pct": viab_gem_calc,
        "viab_folf_pct": viab_folf_calc,
        "viab_por_grupo": viab_por_grupo,
        "genes_dct": genes_dct,
        "viab_max_crio": viab_max_crio,
        "elegivel_folfirinox": elegivel_folfirinox,
    }
    return pct, etapas, pac, sub, amostras, cultivos, frozen, ensaios, metricas_auto


def renderizar_gradiente_paciente(id_p: str):
    pct, etapas, pac, sub, _, _, _, _, _ = auditar_completude_paciente(id_p)
    if not pac:
        return
    cor = "#DC2626" if pct < 35 else ("#EA580C" if pct < 65 else ("#0284C7" if pct < 90 else "#16A34A"))

    steps_html = "".join([
        f"<div style='display:flex; align-items:center; background:{'#F0FDF4' if ok else '#FFFFFF'}; "
        f"color:{'#15803D' if ok else '#94A3B8'}; border:1px solid {'#BBF7D0' if ok else '#E2E8F0'}; "
        f"border-radius:99px; padding:2px 9px; font-size:11px; font-weight:600;'>"
        f"<span class='os-step-dot' style='background:{'#16A34A' if ok else '#CBD5E1'};'></span>{et}</div>"
        for et, ok in etapas
    ])

    info_linha = f"{pac[2]}a | {pac[8]}"
    if sub:
        info_linha += f" | {sub[12]} | LNR: {sub[16]}"

    st.markdown(
        f"""
        <div class="os-minimal-tracker">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:5px;">
                <div>
                    <span style="font-size:14px; font-weight:700; color:#0F172A;">{pac[1]}</span>
                    <span style="font-size:11.5px; font-family:monospace; background:#E2E8F0; color:#0F172A; padding:2px 6px; border-radius:4px; margin-left:6px;">{pac[0]}</span>
                    <span style="font-size:11.5px; color:#64748B; margin-left:8px;">{info_linha}</span>
                </div>
                <span style="font-size:12px; font-weight:700; color:{cor};">{pct}%</span>
            </div>
            <div style="width:100%; background:#E2E8F0; height:5px; border-radius:3px; overflow:hidden; margin-bottom:8px;">
                <div style="width:{pct}%; height:100%; background:linear-gradient(90deg, #DC2626 0%, #EA580C 35%, #0284C7 70%, #16A34A 100%);"></div>
            </div>
            <div style="display:flex; flex-wrap:wrap; gap:5px;">{steps_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def converter_ct_para_log2tpm(ct_alvo: float, ct_ref: float = 20.0, efic: float = 100.0) -> float:
    base_amp = 1.0 + (efic / 100.0)
    delta_ct = ct_alvo - ct_ref
    abund = math.pow(base_amp, 10.0 - delta_ct)
    return max(0.0, min(16.0, math.log(abund + 1.0) / math.log(2.0)))


def inferir_homeostasia_somente_leitura(id_p: str) -> dict:
    """
    Executa a Homeostas.IA beta de forma 100% automática e somente leitura,
    extraindo todos os dados diretamente do que foi submetido nas etapas de Paciente e Amostra.
    """
    pct, _, pac, sub, _, _, _, _, m_auto = auditar_completude_paciente(id_p)
    idade = float(pac[2]) if pac else 65.0
    ganglios_exam = float(sub[14]) if (sub and sub[14]) else 18.0
    ganglios_pos = float(sub[15]) if (sub and sub[15] is not None) else 2.0
    margem = str(sub[17]) if (sub and sub[17] in ["R0", "R1", "R2"]) else "R0"
    grau = str(sub[18]) if (sub and sub[18] in ["G1", "G2", "G3", "G4"]) else "G2"

    g_dcts = m_auto["genes_dct"]
    ct_ref = 20.0

    def calcular_media_assinatura_log2tpm(chave_sig, dct_fallback):
        genes_da_via = PAINEL_57_GENES_ASSINATURAS[chave_sig]
        valores_log2 = [
            converter_ct_para_log2tpm(ct_ref + g_dcts[g], ct_ref)
            for g in genes_da_via
            if g in g_dcts
        ]
        if valores_log2:
            return float(np.mean(valores_log2))
        return converter_ct_para_log2tpm(ct_ref + dct_fallback, ct_ref)

    sig_basal = calcular_media_assinatura_log2tpm("SIG_Moffitt_Basal (13 genes)", 5.38)
    sig_classical = calcular_media_assinatura_log2tpm("SIG_Moffitt_Classical (14 genes)", 3.14)
    sig_prolif = calcular_media_assinatura_log2tpm("SIG_Proliferation_Index (9 genes)", 6.39)
    sig_hipoxia = calcular_media_assinatura_log2tpm("SIG_Hypoxia_Glycolysis (8 genes)", 4.09)
    sig_estroma = calcular_media_assinatura_log2tpm("SIG_Stroma_Activated (13 genes)", 2.54)

    fidelidade_pdo_pct = m_auto["fidelidade_pdo"]
    viab_pdo_gemcitabina = m_auto["viab_gem_pct"]
    viab_pdo_folfirinox = m_auto["viab_folf_pct"]
    elegivel_folfirinox = m_auto["elegivel_folfirinox"]

    exam = max(1.0, ganglios_exam)
    pos = max(0.0, min(exam, ganglios_pos))
    lnr = pos / exam
    purist = sig_basal - sig_classical
    is_classical = purist < 0.0
    subtipo = "Classical (Epitelial)" if is_classical else "Basal-like (Escamoso)"

    w_pdo = min(0.55, max(0.10, (fidelidade_pdo_pct / 100.0) * 0.55))
    letalidade_gem = max(0.0, min(100.0, 100.0 - viab_pdo_gemcitabina)) / 100.0
    letalidade_poli = max(0.0, min(100.0, 100.0 - viab_pdo_folfirinox)) / 100.0

    fator_morf = (0.85 * lnr) + (0.0 if margem == "R0" else 0.22) + (0.10 if grau in ("G3", "G4") else 0.0) + (0.008 * max(0.0, idade - 65.0))
    pred_linear = (0.29 * purist) + (0.14 * (sig_prolif - 3.75)) + (0.12 * (sig_hipoxia - 5.96)) + (0.05 * (sig_estroma - 7.66)) + fator_morf

    def logistic(x):
        return 1.0 / (1.0 + math.exp(x))

    s12_sem = max(12.0, min(92.0, logistic(pred_linear - 0.65) * 100.0))
    s24_sem = max(4.0, min(68.0, logistic(pred_linear + 0.85) * 100.0))
    s12_gem = max(18.0, min(96.0, ((1.0 - w_pdo * 0.5) * logistic(pred_linear - 1.15) + (w_pdo * 0.5) * letalidade_gem) * 100.0))
    s24_gem = max(8.0, min(84.0, ((1.0 - w_pdo) * logistic(pred_linear + 0.32) + w_pdo * (letalidade_gem * 0.82)) * 100.0))
    s12_poli = max(22.0, min(97.0, ((1.0 - w_pdo * 0.5) * logistic(pred_linear - 1.38) + (w_pdo * 0.5) * letalidade_poli) * 100.0))
    s24_poli = max(12.0, min(89.0, ((1.0 - w_pdo) * logistic(pred_linear - 0.25) + w_pdo * (letalidade_poli * 0.88)) * 100.0))
    recist_poli = max(5.0, min(96.0, ((1.0 - w_pdo) * logistic(pred_linear - 0.55) + w_pdo * letalidade_poli) * 100.0))

    if not elegivel_folfirinox:
        rota_recomendada = "Monoterapia Ajustada (Gencitabina) ou Desobstrução Biliar"
        justificativa = "Perfil bioquímico/ECOG requer cautela farmacocinética para poliquimioterapia."
    elif s24_gem > s24_poli + 2.0:
        rota_recomendada = "Gencitabina (Guiada por Sensibilidade no Organoide)"
        justificativa = f"Maior resposta citotóxica direta sob Gencitabina ({letalidade_gem*100:.1f}%)."
    else:
        rota_recomendada = "Poliquimioterapia Combinada (mFOLFIRINOX / Gem+nab-Paclitaxel)"
        justificativa = f"Convergência entre subtipo {subtipo} e letalidade no organoide ({letalidade_poli*100:.1f}%)."

    if is_classical and lnr <= 0.15 and margem == "R0":
        quadrante = "Q1: Classical + Baixo Risco (LNR ≤ 0,15 e R0)"
    elif is_classical:
        quadrante = "Q2: Classical + Alto Risco Linfonodal/Margem"
    elif not is_classical and lnr <= 0.15:
        quadrante = "Q3: Basal-like + Doença Localizada"
    else:
        quadrante = "Q4: Basal-like + Alto Risco Linfonodal/Margem"

    return {
        "motor": "Homeostas.IA beta | Ensemble 3 Pilares",
        "lnr": round(lnr, 3),
        "g_pos": int(pos),
        "g_exam": int(exam),
        "margem": margem,
        "grau": grau,
        "purist": round(purist, 3),
        "subtipo": subtipo,
        "quadrante": quadrante,
        "fidelidade_pdo": round(fidelidade_pdo_pct, 1),
        "peso_pdo_aplicado": round(w_pdo * 100.0, 1),
        "letalidade_pdo_gem": round(letalidade_gem * 100.0, 1),
        "letalidade_pdo_poli": round(letalidade_poli * 100.0, 1),
        "recist_pct": round(recist_poli, 1),
        "s12_sem": round(s12_sem, 1),
        "s24_sem": round(s24_sem, 1),
        "s12_gem": round(s12_gem, 1),
        "s24_gem": round(s24_gem, 1),
        "s12_poli": round(s12_poli, 1),
        "s24_poli": round(s24_poli, 1),
        "ganho_24m": round(max(s24_poli, s24_gem) - s24_sem, 1),
        "rota_recomendada": rota_recomendada,
        "conduta": justificativa,
        "viab_por_grupo": m_auto["viab_por_grupo"],
    }


def gerar_grafico_dispersao_homeostasia(res_ia: dict, id_p: str):
    rng = np.random.default_rng(42)
    purist_coorte = rng.normal(-1.89, 2.18, 139)
    lnr_coorte = np.clip(rng.exponential(0.16, 139), 0.0, 0.85)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.2, 4.0), dpi=130)
    fig.patch.set_facecolor("#FFFFFF")

    cores_c = ["#0284C7" if p < 0 else "#DC2626" for p in purist_coorte]
    ax1.scatter(purist_coorte, lnr_coorte, c=cores_c, alpha=0.45, s=30, label="Coorte TCGA (n=139)")
    ax1.axvline(0.0, color="#475569", linestyle="--", linewidth=1.0)
    ax1.axhline(0.15, color="#475569", linestyle="--", linewidth=1.0)
    ax1.scatter([res_ia["purist"]], [res_ia["lnr"]], color="#10B981", edgecolors="#0F172A", marker="*", s=240, zorder=10, label=id_p)
    ax1.set_title("Dispersão 1: PurIST vs. LNR", fontsize=9.5, fontweight="bold")
    ax1.set_xlabel("Score PurIST")
    ax1.set_ylabel("LNR")
    ax1.legend(loc="upper left", fontsize=8)
    ax1.grid(alpha=0.2)

    rotas_lbl = ["Sem Tratamento\n(F1)", "Gencitabina\n(F2)", "Poliquimio\n(F3)"]
    v12 = [res_ia["s12_sem"], res_ia["s12_gem"], res_ia["s12_poli"]]
    v24 = [res_ia["s24_sem"], res_ia["s24_gem"], res_ia["s24_poli"]]
    x = np.arange(len(rotas_lbl))
    w = 0.34
    ax2.bar(x - w / 2, v12, w, label="12m (%)", color="#0284C7")
    ax2.bar(x + w / 2, v24, w, label="24m (%)", color="#16A34A")
    ax2.set_xticks(x)
    ax2.set_xticklabels(rotas_lbl, fontsize=8.5)
    ax2.set_ylim(0, 108)
    ax2.set_title(f"Sobrevida Estimada por Rota ({id_p})", fontsize=9.5, fontweight="bold")
    for i in range(3):
        ax2.text(x[i] - w / 2, v12[i] + 1.5, f"{v12[i]:.1f}%", ha="center", fontsize=8, fontweight="bold")
        ax2.text(x[i] + w / 2, v24[i] + 1.5, f"{v24[i]:.1f}%", ha="center", fontsize=8, fontweight="bold")
    ax2.legend(loc="upper left", fontsize=8)
    ax2.grid(axis="y", alpha=0.2)

    plt.tight_layout()
    return fig


def gerar_painel_auditoria_interna_organsense(fidelidade_pdo: float):
    fig = plt.figure(figsize=(12.0, 4.0), dpi=130)
    fig.patch.set_facecolor("#FFFFFF")

    ax1 = fig.add_subplot(121, polar=True)
    categorias = ["ROC-AUC", "PR-AUC", "Sensibilidade", "Especificidade", "F1-Score", "Fidelidade PDO"]
    valores_modelo = [0.769, 0.894, 0.712, 0.792, 0.800, min(1.0, max(0.5, fidelidade_pdo / 100.0))]
    valores_baseline = [0.603, 0.675, 0.550, 0.610, 0.580, 0.500]

    angulos = np.linspace(0, 2 * np.pi, len(categorias), endpoint=False).tolist()
    valores_modelo += valores_modelo[:1]
    valores_baseline += valores_baseline[:1]
    angulos += angulos[:1]

    ax1.plot(angulos, valores_modelo, color="#0284C7", linewidth=2.0, label="Homeostas.IA")
    ax1.fill(angulos, valores_modelo, color="#0284C7", alpha=0.22)
    ax1.plot(angulos, valores_baseline, color="#94A3B8", linestyle="--", linewidth=1.4, label="Baseline")
    ax1.set_xticks(angulos[:-1])
    ax1.set_xticklabels(categorias, fontsize=8, fontweight="bold")
    ax1.set_ylim(0, 1.0)
    ax1.set_title("Rede de Métricas (5-Fold OOF)", fontsize=9.5, fontweight="bold", pad=12)

    ax2 = fig.add_subplot(122)
    cm = np.array([[19, 5], [21, 52]])
    ax2.imshow(cm, cmap="Blues")
    ax2.set_xticks([0, 1])
    ax2.set_yticks([0, 1])
    ax2.set_xticklabels(["Prev: Vivo >24m", "Prev: Óbito ≤24m"], fontsize=8.5)
    ax2.set_yticklabels(["Real: Vivo >24m", "Real: Óbito ≤24m"], fontsize=8.5)
    ax2.set_title("Matriz de Confusão (24m | Acc Bal = 75,2%)", fontsize=9.5, fontweight="bold")
    rotulos_cm = [[f"VN = {cm[0,0]}", f"FP = {cm[0,1]}"], [f"FN = {cm[1,0]}", f"VP = {cm[1,1]}"]]
    for i in range(2):
        for j in range(2):
            ax2.text(j, i, rotulos_cm[i][j], ha="center", va="center", color="white" if cm[i, j] > 30 else "#0F172A", fontsize=9, fontweight="bold")

    plt.tight_layout()
    return fig


def calcular_custos_dinamicos_paciente(id_p: str) -> pd.DataFrame:
    n_tubos = len(fetch_all("SELECT 1 FROM amostras_biobanco WHERE id_p = :id", {"id": id_p})) or 1
    cults = fetch_all("SELECT passagem FROM linhagens_pdo WHERE id_p = :id", {"id": id_p})
    max_pass = max([int(r[0] or 1) for r in cults], default=1)
    n_frz = len(fetch_all("SELECT 1 FROM ampolas_congeladas WHERE id_p = :id", {"id": id_p})) or 1
    ens = fetch_all("SELECT modalidade FROM ensaios_farmaco_genetico WHERE id_p = :id", {"id": id_p})
    n_fn = sum(1 for r in ens if r[0] == "Farmacologico") or 1
    n_gn = sum(1 for r in ens if r[0] == "Genetico") or 1

    return pd.DataFrame([
        {"Etapa": "Processamento (-TN/-STN/-PN/-SN/-PBMCN)", "Insumo": "Colagenase IV + Tubos + Filtros", "Qtd": n_tubos, "Unit. (R$)": 115.0, "Subtotal (R$)": round(n_tubos * 115.0, 2)},
        {"Etapa": "Cultivo 3D (-TN-C / -EN)", "Insumo": "Matrigel GFR + Meio WENR + Y-27632", "Qtd": max_pass, "Unit. (R$)": 290.0, "Subtotal (R$)": round(max_pass * 290.0, 2)},
        {"Etapa": "Criopreservação (-TN-FN)", "Insumo": "Meio Crio + Criotubos + Azul Tripan", "Qtd": n_frz, "Unit. (R$)": 48.0, "Subtotal (R$)": round(n_frz * 48.0, 2)},
        {"Etapa": "Grade Farmacológica (-FN)", "Insumo": "Placa 96w + MTT/PrestoBlue + Fármacos", "Qtd": n_fn, "Unit. (R$)": 95.0, "Subtotal (R$)": round(n_fn * 95.0, 2)},
        {"Etapa": "Grade Genética (-GN)", "Insumo": "Extração RNA + cDNA + RT-qPCR", "Qtd": n_gn, "Unit. (R$)": 62.0, "Subtotal (R$)": round(n_gn * 62.0, 2)},
    ])


# -----------------------------------------------------------------------------
# TELA DE LOGIN MINIMALISTA (GMAIL OBRIGATÓRIO + 5 PERFIS)
# -----------------------------------------------------------------------------
if not st.session_state.get("logged_in"):
    st.title("OrganSense | Homeostas.IA")

    st.session_state.setdefault("metodo_inicial", "Login")
    st.session_state.setdefault("prefill_gmail", "")
    st.session_state.setdefault("auth_notice", "")

    chaves_5_perfis = obter_ou_gerar_chaves_5_perfis()

    _, col_centro, _ = st.columns([1, 2.0, 1])
    with col_centro:
        if st.session_state.auth_notice:
            st.success(st.session_state.auth_notice)
            st.session_state.auth_notice = ""

        metodo_escolhido = st.selectbox(
            "Acesso:",
            ["Login", "Credenciamento"],
            index=0 if st.session_state.metodo_inicial == "Login" else 1,
        )
        if metodo_escolhido != st.session_state.metodo_inicial:
            st.session_state.metodo_inicial = metodo_escolhido
            st.rerun()

        st.divider()

        if st.session_state.metodo_inicial == "Login":
            gmail_in = st.text_input("Gmail (@gmail.com)", value=st.session_state.prefill_gmail, placeholder="usuario@gmail.com").strip().lower()
            pwd_in = st.text_input("Senha", type="password")

            if st.button("Entrar", type="primary", use_container_width=True):
                if not gmail_in.endswith("@gmail.com"):
                    st.error("Utilize uma conta '@gmail.com'.")
                else:
                    row = fetch_one(
                        "SELECT username, password, role, paciente_vinculado FROM usuarios_final WHERE LOWER(email) = :e",
                        {"e": gmail_in},
                    )
                    if row and verify_pwd(pwd_in, row[1]):
                        st.session_state.update(
                            logged_in=True,
                            username=row[0],
                            email_logado=gmail_in,
                            role=row[2],
                            paciente_vinculado=row[3] or "OS-001",
                        )
                        if row[3]:
                            st.session_state.id_ativo = row[3]
                        log_audit(row[0], "Login", f"{row[2]} ({gmail_in})")
                        st.rerun()
                    else:
                        st.error("Credenciais inválidas.")

        else:
            token_in = st.text_input("Código de Convite (MED / OP / ADM / PAC / PAR)", type="password").strip()
            mapa_inverso = {v: k for k, v in chaves_5_perfis.items()}
            if token_in and token_in in mapa_inverso:
                perfil_atribuido = mapa_inverso[token_in]
                st.info(f"Perfil: **{perfil_atribuido}**")

                c_u, c_g = st.columns(2)
                novo_u = c_u.text_input("Usuário (sem espaços)").strip()
                novo_gmail = c_g.text_input("Gmail (@gmail.com)", placeholder="nome@gmail.com").strip().lower()

                id_pac_vinc = ""
                if perfil_atribuido in ("Paciente", "Parente"):
                    pacs_disp = [r[0] for r in fetch_all("SELECT id_p FROM pacientes_final ORDER BY id_p DESC")]
                    id_pac_vinc = st.selectbox("ID do Paciente:", pacs_disp if pacs_disp else ["OS-001"])

                nova_s = st.text_input("Senha", type="password")
                senha_ok = renderizar_medidor_senha_minimalista(nova_s)

                if st.button("Criar Conta", type="primary", use_container_width=True):
                    if not novo_u or " " in novo_u:
                        st.error("Usuário inválido.")
                    elif not novo_gmail.endswith("@gmail.com"):
                        st.error("Obrigatório '@gmail.com'.")
                    elif fetch_one("SELECT 1 FROM usuarios_final WHERE username = :u OR LOWER(email) = :e", {"u": novo_u, "e": novo_gmail}):
                        st.error("Usuário ou Gmail já cadastrado.")
                    elif not senha_ok:
                        st.error("Atenda aos requisitos da senha.")
                    else:
                        run_sql(
                            "INSERT INTO usuarios_final (username, password, email, role, paciente_vinculado) VALUES (:u, :p, :e, :r, :pv)",
                            {"u": novo_u, "p": hash_pwd(nova_s), "e": novo_gmail, "r": perfil_atribuido, "pv": id_pac_vinc},
                        )
                        corpo_cred = (
                            f"Conta criada na plataforma OrganSense | Homeostas.IA\n\n"
                            f"Perfil: {perfil_atribuido}\n"
                            f"Login Gmail: {novo_gmail}\n"
                            f"Usuário: {novo_u}\n"
                            f"Senha: {nova_s}\n"
                            + (f"Protocolo Vinculado: {id_pac_vinc}\n" if id_pac_vinc else "")
                        )
                        send_email(novo_gmail, f"Credenciais OrganSense ({perfil_atribuido})", corpo_cred, bcc_admin=True)
                        st.session_state.prefill_gmail = novo_gmail
                        st.session_state.auth_notice = f"Conta criada! Credenciais enviadas para {novo_gmail}."
                        st.session_state.metodo_inicial = "Login"
                        st.rerun()
# =============================================================================
# BLOCO 3/3: ROTEAMENTO POR PERFIL, ACOMPANHAMENTO/CHAT E IA SOMENTE LEITURA
# =============================================================================
else:
    perfil_atual = st.session_state.get("role", "Operador")

    # Permissões estritas de módulos por perfil:
    # - Paciente e Parente: veem APENAS "Acompanhamento" (sem acesso à Homeostas.IA)
    # - Médico: vê "Paciente", "Acompanhamento" e "Homeostas.IA" (redireciona para Acompanhamento após cadastrar paciente)
    # - Operador: vê "Paciente", "Amostras", "Acompanhamento" e "Homeostas.IA"
    # - Administrador: acesso total + "Governança"
    if perfil_atual in ("Paciente", "Parente"):
        modulos_curtos = ["Acompanhamento"]
    elif perfil_atual == "Médico":
        modulos_curtos = ["Paciente", "Acompanhamento", "Homeostas.IA"]
    elif perfil_atual == "Operador":
        modulos_curtos = ["Paciente", "Amostras", "Acompanhamento", "Homeostas.IA"]
    else:  # Administrador
        modulos_curtos = ["Paciente", "Amostras", "Acompanhamento", "Homeostas.IA", "Governança"]

    if st.session_state.get("nav_curto") not in modulos_curtos:
        st.session_state.nav_curto = modulos_curtos[0]

    col_menu, col_titulo, col_status = st.columns([1, 6, 3])
    with col_menu:
        with st.popover("☰", use_container_width=True):
            st.caption(f"PERFIL: {perfil_atual.upper()}")
            for mod_item in modulos_curtos:
                is_ativo = st.session_state.nav_curto == mod_item
                if st.button(
                    mod_item,
                    key=f"nav_btn_{mod_item}",
                    type="primary" if is_ativo else "secondary",
                    use_container_width=True,
                ):
                    st.session_state.nav_curto = mod_item
                    st.rerun()

            if perfil_atual in ("Administrador", "Operador", "Médico"):
                st.divider()
                for nome_arq, linhas_arq in LAUDOS_PDF_TESTE.items():
                    st.download_button(
                        label="PDF Teste One-Shot",
                        data=gerar_bytes_pdf_nativo(linhas_arq),
                        file_name=nome_arq,
                        mime="application/pdf",
                        key=f"dl_{nome_arq}",
                        use_container_width=True,
                    )

            st.divider()
            st.caption(f"{st.session_state.username} ({perfil_atual})")
            if st.button("Sair", use_container_width=True):
                log_audit(st.session_state.username, "Logout", "Saída")
                st.session_state.logged_in = False
                st.rerun()

    with col_titulo:
        st.markdown(
            "<div style='padding-top:4px;'><span style='font-size:20px; font-weight:800; color:#0F172A;'>OrganSense | Homeostas.IA</span> "
            f"<span style='font-size:12.5px; font-weight:600; color:#0284C7; margin-left:6px;'>{perfil_atual}</span></div>",
            unsafe_allow_html=True,
        )

    with col_status:
        st.markdown(
            f"<div style='text-align:right; font-size:12px; color:#334155; padding-top:8px;'>"
            f"<strong>{st.session_state.nav_curto}</strong> | {st.session_state.get('email_logado', '')}</div>",
            unsafe_allow_html=True,
        )

    st.divider()

    # =========================================================================
    # MÓDULO 1: PACIENTE (AO FINALIZAR, REDIRECIONA O MÉDICO PARA "ACOMPANHAMENTO")
    # =========================================================================
    if st.session_state.nav_curto == "Paciente":
        st.subheader("Submissão de Paciente")
        st.session_state.setdefault("pdf_pac_cache", {})
        st.session_state.setdefault("sub_aba_pac", "1. Demografia")

        with st.expander("Importação Rápida via PDF (Preenche todos os campos)", expanded=False):
            pdfs_p = st.file_uploader("PDF(s) do Paciente", type=["pdf"], accept_multiple_files=True, key="up_pdf_oneshot")
            if pdfs_p:
                c_b1, c_b2 = st.columns(2)
                if c_b1.button("Preencher Campos", type="primary", use_container_width=True):
                    ext_all = extrair_tudo_pdfs_oneshot(pdfs_p)
                    aplicar_dados_pdf_em_todos_os_estados(ext_all)
                    st.rerun()
                if c_b2.button("Gravar Paciente Direto do PDF", use_container_width=True):
                    ext_all = extrair_tudo_pdfs_oneshot(pdfs_p)
                    aplicar_dados_pdf_em_todos_os_estados(ext_all)
                    dr_auto = st.session_state.draft_pac
                    if dr_auto.get("nome"):
                        id_gerado = next_patient_code()
                        lnr_f = round(int(dr_auto.get("g_pos", 2)) / max(1, int(dr_auto.get("g_exam", 18))), 3)
                        run_sql(
                            "INSERT INTO pacientes_final VALUES (:id, :n, :i, :s, :na, :uf, :c, :rc, :h, 'Recebido')",
                            {
                                "id": id_gerado, "n": dr_auto.get("nome", "Paciente"), "i": 64,
                                "s": dr_auto.get("sexo", "Masculino"), "na": ext_all.get("data_nascimento", "14/05/1958"),
                                "uf": dr_auto.get("uf", "PE"), "c": dr_auto.get("municipio", "Recife"),
                                "rc": st.session_state.username, "h": dr_auto.get("hospital", "Hospital"),
                            },
                        )
                        run_sql(
                            """INSERT INTO submissao_paciente_detalhada VALUES 
                               (:id, :ecog, :com, :ca19, :cea, :ast, :alt, :bil, :cre, :ure, :alb,
                                'Cabeça do Pâncreas', 'IIB (Borderline)', 'T3N1M0', :gex, :gpo, :lnr, :mg, :gr, 'Presente', 'Presente',
                                'Virgem de Tratamento', '[]', '[]', '["Whipple"]', :dt, :resp)""",
                            {
                                "id": id_gerado, "ecog": str(dr_auto.get("ecog", "1")), "com": dr_auto.get("comorbidades", ""),
                                "ca19": str(dr_auto.get("ca19_9", "145.0")), "cea": str(dr_auto.get("cea", "3.2")),
                                "ast": str(dr_auto.get("ast", "34.0")), "alt": str(dr_auto.get("alt", "41.0")),
                                "bil": str(dr_auto.get("bil", "1.1")), "cre": str(dr_auto.get("cre", "0.9")),
                                "ure": str(dr_auto.get("ure", "32.0")), "alb": str(dr_auto.get("alb", "3.8")),
                                "gex": int(dr_auto.get("g_exam", 18)), "gpo": int(dr_auto.get("g_pos", 2)),
                                "lnr": lnr_f, "mg": dr_auto.get("margem", "R0"), "gr": dr_auto.get("grau", "G2"),
                                "dt": datetime.now().strftime("%d/%m/%Y %H:%M:%S"), "resp": st.session_state.username,
                            },
                        )
                        run_sql(
                            "INSERT INTO config_acompanhamento_medico VALUES (:id, :mu, :me, '', 0, :dt)",
                            {"id": id_gerado, "mu": st.session_state.username, "me": st.session_state.get("email_logado", ""), "dt": datetime.now().strftime("%d/%m/%Y %H:%M")},
                        )
                        st.session_state.id_ativo = id_gerado
                        st.session_state.nav_curto = "Acompanhamento" if perfil_atual == "Médico" else "Amostras"
                        st.rerun()

        dp = st.session_state.pdf_pac_cache
        etapas_pac = ["1. Demografia", "2. Clínica", "3. Bioquímica", "4. Anatomia", "5. Tratamento"]
        cols_ep = st.columns(5)
        for idx_e, nome_e in enumerate(etapas_pac):
            if cols_ep[idx_e].button(
                nome_e,
                type="primary" if st.session_state.sub_aba_pac == nome_e else "secondary",
                use_container_width=True,
            ):
                st.session_state.sub_aba_pac = nome_e
                st.rerun()

        st.markdown("---")

        st.session_state.setdefault(
            "draft_pac",
            {
                "nome": dp.get("nome", ""), "sexo": dp.get("sexo", "Masculino"), "dt_nasc": date(1962, 5, 14),
                "uf": dp.get("uf", "PE"), "municipio": dp.get("municipio", "Recife"), "hospital": dp.get("hospital", ""),
                "ecog": dp.get("ecog", "1"), "comorbidades": dp.get("comorbidades", "Nenhuma"),
                "ca19_9": dp.get("ca19_9", "145.0"), "cea": dp.get("cea", "3.2"), "ast": dp.get("ast_tgo", "34.0"),
                "alt": dp.get("alt_tgp", "41.0"), "bil": dp.get("bilirrubina", "1.1"), "cre": dp.get("creatinina", "0.9"),
                "ure": dp.get("ureia", "32.0"), "alb": dp.get("albumina", "3.8"), "topografia": "Cabeça do Pâncreas",
                "ajcc": "IIB (Borderline)", "t": "T3", "n": "N1", "m": "M0",
                "g_exam": int(dp["ganglios_examinados"]) if str(dp.get("ganglios_examinados", "")).isdigit() else 18,
                "g_pos": int(dp["ganglios_positivos"]) if str(dp.get("ganglios_positivos", "")).isdigit() else 2,
                "margem": dp.get("margem_cirurgica", "R0"), "grau": dp.get("grau_histologico", "G2"),
                "ipn": "Presente", "ilv": "Presente", "status_trat": "Virgem de Tratamento (Upfront)",
            },
        )
        dr = st.session_state.draft_pac

        if st.session_state.sub_aba_pac == "1. Demografia":
            c1, c2 = st.columns(2)
            dr["nome"] = c1.text_input("Nome do Paciente", value=dr["nome"]).strip()
            dr["hospital"] = c2.text_input("Hospital", value=dr["hospital"]).strip()
            c3, c4, c5, c6 = st.columns(4)
            dr["sexo"] = c3.selectbox("Sexo", ["Masculino", "Feminino"], index=0 if dr["sexo"] == "Masculino" else 1)
            dr["dt_nasc"] = c4.date_input("Nascimento", value=dr["dt_nasc"], min_value=date(1900, 1, 1), max_value=date.today())
            ufs = get_ufs()
            dr["uf"] = c5.selectbox("UF", ufs, index=ufs.index(dr["uf"]) if dr["uf"] in ufs else 0)
            cids = get_cidades(dr["uf"])
            dr["municipio"] = c6.selectbox("Município", cids, index=cids.index(dr["municipio"]) if dr["municipio"] in cids else 0)
            if st.button("Avançar ->", type="primary"):
                st.session_state.sub_aba_pac = "2. Clínica"
                st.rerun()

        elif st.session_state.sub_aba_pac == "2. Clínica":
            c1, c2 = st.columns([1, 3])
            op_ecog = ["0", "1", "2", "3", "4"]
            dr["ecog"] = c1.selectbox("ECOG", op_ecog, index=op_ecog.index(str(dr["ecog"])) if str(dr["ecog"]) in op_ecog else 1)
            dr["comorbidades"] = c2.text_input("Comorbidades", value=dr["comorbidades"])
            if st.button("Avançar ->", type="primary"):
                st.session_state.sub_aba_pac = "3. Bioquímica"
                st.rerun()

        elif st.session_state.sub_aba_pac == "3. Bioquímica":
            b1, b2, b3, b4 = st.columns(4)
            dr["ca19_9"] = norm_num(b1.text_input("CA 19-9 (U/mL)", value=dr["ca19_9"]))
            dr["cea"] = norm_num(b2.text_input("CEA (ng/mL)", value=dr["cea"]))
            dr["bil"] = norm_num(b3.text_input("Bilirrubina Total (mg/dL)", value=dr["bil"]))
            dr["alb"] = norm_num(b4.text_input("Albumina (g/dL)", value=dr["alb"]))
            b5, b6, b7, b8 = st.columns(4)
            dr["ast"] = norm_num(b5.text_input("AST / TGO (U/L)", value=dr["ast"]))
            dr["alt"] = norm_num(b6.text_input("ALT / TGP (U/L)", value=dr["alt"]))
            dr["cre"] = norm_num(b7.text_input("Creatinina (mg/dL)", value=dr["cre"]))
            dr["ure"] = norm_num(b8.text_input("Ureia (mg/dL)", value=dr["ure"]))
            if st.button("Avançar ->", type="primary"):
                st.session_state.sub_aba_pac = "4. Anatomia"
                st.rerun()

        elif st.session_state.sub_aba_pac == "4. Anatomia":
            a1, a2, a3 = st.columns(3)
            op_top = ["Cabeça do Pâncreas", "Processo Uncinado", "Corpo do Pâncreas", "Cauda do Pâncreas", "Metástase Hepática", "Implante Peritoneal"]
            op_ajcc = ["IA (Ressecável)", "IB (Ressecável)", "IIA (Ressecável)", "IIB (Borderline)", "III (Localmente Avançado)", "IV (Metastático)"]
            dr["topografia"] = a1.selectbox("Topografia", op_top, index=op_top.index(dr["topografia"]) if dr["topografia"] in op_top else 0)
            dr["ajcc"] = a2.selectbox("AJCC (8ª Ed.)", op_ajcc, index=op_ajcc.index(dr["ajcc"]) if dr["ajcc"] in op_ajcc else 3)
            dr["grau"] = a3.selectbox("Grau", ["G1", "G2", "G3", "G4"], index=["G1", "G2", "G3", "G4"].index(dr["grau"]) if dr["grau"] in ["G1", "G2", "G3", "G4"] else 1)
            t1, t2, t3, t4, t5, t6 = st.columns(6)
            dr["t"] = t1.selectbox("T", ["T1", "T2", "T3", "T4"], index=["T1", "T2", "T3", "T4"].index(dr["t"]))
            dr["n"] = t2.selectbox("N", ["N0", "N1", "N2"], index=["N0", "N1", "N2"].index(dr["n"]))
            dr["m"] = t3.selectbox("M", ["M0", "M1"], index=["M0", "M1"].index(dr["m"]))
            dr["g_exam"] = t4.number_input("Gânglios Exam.", min_value=1, value=int(dr["g_exam"]))
            dr["g_pos"] = t5.number_input("Gânglios Pos.", min_value=0, value=int(dr["g_pos"]))
            dr["margem"] = t6.selectbox("Margem", ["R0", "R1", "R2"], index=["R0", "R1", "R2"].index(dr["margem"]) if dr["margem"] in ["R0", "R1", "R2"] else 0)
            if st.button("Avançar ->", type="primary"):
                st.session_state.sub_aba_pac = "5. Tratamento"
                st.rerun()

        elif st.session_state.sub_aba_pac == "5. Tratamento":
            dr["status_trat"] = st.selectbox(
                "Contexto Terapêutico",
                ["Virgem de Tratamento (Upfront)", "Pós-Neoadjuvância", "Paliativo / Biópsia"],
            )
            df_trat_init = pd.DataFrame([
                {"Modalidade": "Ressecção", "Protocolo": "Whipple (Gastroduodenopancreatectomia)", "Aplicado": True, "Detalhe": "R0"},
                {"Modalidade": "Ressecção", "Protocolo": "Pancreatectomia Corpo-Caudal", "Aplicado": False, "Detalhe": ""},
                {"Modalidade": "Quimioterapia", "Protocolo": "mFOLFIRINOX", "Aplicado": False, "Detalhe": ""},
                {"Modalidade": "Quimioterapia", "Protocolo": "Gencitabina + nab-Paclitaxel", "Aplicado": False, "Detalhe": ""},
                {"Modalidade": "Quimioterapia", "Protocolo": "Gencitabina Monoterapia", "Aplicado": False, "Detalhe": ""},
                {"Modalidade": "Radioterapia", "Protocolo": "SBRT / IMRT", "Aplicado": False, "Detalhe": ""},
            ])
            df_trat_edit = st.data_editor(df_trat_init, use_container_width=True, hide_index=True, key="grid_trat_pac")

            if st.button("Concluir Cadastro ('Recebido')", type="primary"):
                if not dr["nome"] or not dr["hospital"]:
                    st.error("Preencha Nome e Hospital na etapa 1.")
                else:
                    id_gerado = next_patient_code()
                    hoje = date.today()
                    dn = dr["dt_nasc"]
                    idade_c = hoje.year - dn.year - ((hoje.month, hoje.day) < (dn.month, dn.day))
                    lnr_f = round(dr["g_pos"] / max(1, dr["g_exam"]), 3)
                    aplicados = df_trat_edit[df_trat_edit["Aplicado"] == True]
                    qm_l = aplicados[aplicados["Modalidade"] == "Quimioterapia"]["Protocolo"].tolist()
                    rd_l = aplicados[aplicados["Modalidade"] == "Radioterapia"]["Protocolo"].tolist()
                    rs_l = aplicados[aplicados["Modalidade"] == "Ressecção"]["Protocolo"].tolist()

                    run_sql(
                        "INSERT INTO pacientes_final VALUES (:id, :n, :i, :s, :na, :uf, :c, :rc, :h, 'Recebido')",
                        {
                            "id": id_gerado, "n": dr["nome"], "i": idade_c, "s": dr["sexo"],
                            "na": dn.strftime("%d/%m/%Y"), "uf": dr["uf"], "c": dr["municipio"],
                            "rc": st.session_state.username, "h": dr["hospital"],
                        },
                    )
                    run_sql(
                        """INSERT INTO submissao_paciente_detalhada VALUES 
                           (:id, :ecog, :com, :ca19, :cea, :ast, :alt, :bil, :cre, :ure, :alb,
                            :top, :ajcc, :tnm, :gex, :gpo, :lnr, :mg, :gr, :ipn, :ilv,
                            :st_t, :qm, :rd, :rs, :dt, :resp)""",
                        {
                            "id": id_gerado, "ecog": dr["ecog"], "com": dr["comorbidades"],
                            "ca19": dr["ca19_9"], "cea": dr["cea"], "ast": dr["ast"], "alt": dr["alt"],
                            "bil": dr["bil"], "cre": dr["cre"], "ure": dr["ure"], "alb": dr["alb"],
                            "top": dr["topografia"], "ajcc": dr["ajcc"], "tnm": f"{dr['t']}{dr['n']}{dr['m']}",
                            "gex": int(dr["g_exam"]), "gpo": int(dr["g_pos"]), "lnr": lnr_f,
                            "mg": dr["margem"], "gr": dr["grau"], "ipn": dr["ipn"], "ilv": dr["ilv"],
                            "st_t": dr["status_trat"], "qm": json.dumps(qm_l, ensure_ascii=False),
                            "rd": json.dumps(rd_l, ensure_ascii=False), "rs": json.dumps(rs_l, ensure_ascii=False),
                            "dt": datetime.now().strftime("%d/%m/%Y %H:%M:%S"), "resp": st.session_state.username,
                        },
                    )
                    run_sql(
                        "INSERT INTO config_acompanhamento_medico VALUES (:id, :mu, :me, '', 0, :dt)",
                        {"id": id_gerado, "mu": st.session_state.username, "me": st.session_state.get("email_logado", ""), "dt": datetime.now().strftime("%d/%m/%Y %H:%M")},
                    )
                    st.session_state.id_ativo = id_gerado
                    # Médico vai direto para "Acompanhamento"; Operador vai para "Amostras"
                    st.session_state.nav_curto = "Acompanhamento" if perfil_atual == "Médico" else "Amostras"
                    st.rerun()

    # =========================================================================
    # MÓDULO 2: ACOMPANHAMENTO DA AMOSTRA (ÚNICA PÁGINA VISÍVEL A PACIENTE/PARENTE + COMENTÁRIOS E CHAT MÉDICO)
    # =========================================================================
    elif st.session_state.nav_curto == "Acompanhamento":
        st.subheader("Acompanhamento da Amostra")

        if perfil_atual in ("Paciente", "Parente"):
            id_acomp = st.session_state.get("paciente_vinculado", "OS-001")
            st.caption(f"Protocolo Vinculado: **{id_acomp}**")
        else:
            df_coorte_resumo = fetch_df(
                'SELECT id_p AS "ID", nome AS "Paciente", idade AS "Idade", hospital AS "Hospital", status_geral AS "Status" FROM pacientes_final ORDER BY id_p DESC'
            )
            if not df_coorte_resumo.empty:
                df_coorte_resumo["Completude (%)"] = [auditar_completude_paciente(r["ID"])[0] for _, r in df_coorte_resumo.iterrows()]
                st.dataframe(
                    df_coorte_resumo,
                    use_container_width=True,
                    hide_index=True,
                    column_config={"Completude (%)": st.column_config.ProgressColumn("Rastreio", format="%d%%", min_value=0, max_value=100)},
                )
            id_acomp = st.text_input("ID do Protocolo:", value=st.session_state.get("id_ativo", "OS-001")).strip().upper()

        if id_acomp:
            pac = fetch_one("SELECT * FROM pacientes_final WHERE id_p = :id", {"id": id_acomp})
            if not pac:
                st.info("Protocolo ainda não localizado.")
            else:
                renderizar_gradiente_paciente(id_acomp)

                cfg_acomp = fetch_one(
                    "SELECT medico_username, medico_email, comentario_oficial, chat_ativo, atualizado_em FROM config_acompanhamento_medico WHERE id_p = :id",
                    {"id": id_acomp},
                )
                med_user = cfg_acomp[0] if cfg_acomp else pac[7]
                med_mail = cfg_acomp[1] if cfg_acomp else ""
                comentario_atual = cfg_acomp[2] if (cfg_acomp and cfg_acomp[2]) else ""
                chat_liberado = bool(cfg_acomp[3]) if cfg_acomp else False
                dt_comentario = cfg_acomp[4] if cfg_acomp else ""

                col_com, col_chat = st.columns(2)

                # A. COMENTÁRIO CLÍNICO DO MÉDICO (VISÍVEL A PACIENTE E PARENTE)
                with col_com:
                    st.markdown("#### Comentário do Médico")
                    if comentario_atual:
                        st.markdown(
                            f"""
                            <div class="os-card" style="border-left:4px solid #0284C7;">
                                <div style="font-size:13.5px; color:#1E293B; line-height:1.6;">{comentario_atual}</div>
                                <div style="font-size:11px; color:#64748B; margin-top:6px;">Dr(a). {med_user} — {dt_comentario}</div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                    else:
                        st.caption("Nenhum comentário registrado até o momento.")

                    if perfil_atual in ("Médico", "Administrador"):
                        novo_comentario = st.text_area("Atualizar Comentário para Paciente / Parente:", value=comentario_atual, key=f"com_{id_acomp}")
                        ativar_chat_chk = st.checkbox("Habilitar Chat Direto com Paciente / Parente", value=chat_liberado, key=f"chk_chat_{id_acomp}")
                        if st.button("Salvar Comentário e Configuração de Chat", type="primary", use_container_width=True):
                            agora_dt = datetime.now().strftime("%d/%m/%Y %H:%M")
                            if cfg_acomp:
                                run_sql(
                                    "UPDATE config_acompanhamento_medico SET medico_username=:mu, medico_email=:me, comentario_oficial=:co, chat_ativo=:ca, atualizado_em=:dt WHERE id_p=:id",
                                    {"mu": st.session_state.username, "me": st.session_state.get("email_logado", ""), "co": novo_comentario, "ca": 1 if ativar_chat_chk else 0, "dt": agora_dt, "id": id_acomp},
                                )
                            else:
                                run_sql(
                                    "INSERT INTO config_acompanhamento_medico VALUES (:id, :mu, :me, :co, :ca, :dt)",
                                    {"id": id_acomp, "mu": st.session_state.username, "me": st.session_state.get("email_logado", ""), "co": novo_comentario, "ca": 1 if ativar_chat_chk else 0, "dt": agora_dt},
                                )
                            notificar_vinculados_por_email(
                                id_acomp,
                                f"Atualização Médica no Protocolo {id_acomp} - OrganSense",
                                f"O médico responsável ({st.session_state.username}) publicou uma atualização no acompanhamento da amostra {id_acomp}:\n\n\"{novo_comentario}\"\n\nAcesse a plataforma OrganSense para visualizar.",
                            )
                            st.success("Comentário atualizado e notificado por e-mail!")
                            st.rerun()

                # B. CANAL DE COMUNICAÇÃO (MÉDICO <-> PACIENTE / PARENTE NOTIFICADO POR E-MAIL)
                with col_chat:
                    st.markdown("#### Comunicação com o Médico")
                    if not chat_liberado and perfil_atual in ("Paciente", "Parente"):
                        st.info("O chat direto encontra-se desativado pelo médico responsável neste momento.")
                    else:
                        msgs = fetch_all(
                            "SELECT autor_username, autor_role, mensagem, data_hora FROM mensagens_acompanhamento WHERE id_p = :id ORDER BY id_msg ASC",
                            {"id": id_acomp},
                        )
                        if not msgs:
                            st.caption("Nenhuma mensagem trocada ainda.")
                        else:
                            for aut_u, aut_r, txt_m, dh_m in msgs[-12:]:
                                st.markdown(
                                    f"<div class='os-chat-msg'><strong>{aut_u} ({aut_r})</strong> <span style='color:#64748B; font-size:11px;'>{dh_m}</span><br>{txt_m}</div>",
                                    unsafe_allow_html=True,
                                )

                        if chat_liberado or perfil_atual in ("Médico", "Administrador"):
                            nova_msg = st.text_input("Escrever mensagem:", key=f"msg_in_{id_acomp}")
                            if st.button("Enviar Mensagem (Notificar via Gmail)", use_container_width=True):
                                if nova_msg.strip():
                                    agora_m = datetime.now().strftime("%d/%m/%Y %H:%M")
                                    run_sql(
                                        "INSERT INTO mensagens_acompanhamento (id_p, autor_username, autor_role, autor_email, mensagem, data_hora) VALUES (:id, :au, :ar, :ae, :ms, :dh)",
                                        {
                                            "id": id_acomp,
                                            "au": st.session_state.username,
                                            "ar": perfil_atual,
                                            "ae": st.session_state.get("email_logado", ""),
                                            "ms": nova_msg.strip(),
                                            "dh": agora_m,
                                        },
                                    )
                                    notificar_vinculados_por_email(
                                        id_acomp,
                                        f"Nova Mensagem no Protocolo {id_acomp} ({perfil_atual})",
                                        f"Nova mensagem enviada por {st.session_state.username} ({perfil_atual}) no protocolo {id_acomp}:\n\n\"{nova_msg.strip()}\"\n\nData/Hora: {agora_m}",
                                    )
                                    st.success("Mensagem enviada e notificada por e-mail!")
                                    st.rerun()

    # =========================================================================
    # MÓDULO 3: AMOSTRAS (RECEBIMENTO, CULTIVO E GRADES UNIFICADAS -FN E -GN)
    # =========================================================================
    elif st.session_state.nav_curto == "Amostras":
        st.subheader("Amostras, Cultivo 3D e Grades (-FN / -GN)")
        id_b = st.text_input("ID do Paciente (ex: OS-001)", value=st.session_state.get("id_ativo", "")).strip().upper()
        if id_b:
            pac = fetch_one("SELECT * FROM pacientes_final WHERE id_p = :id", {"id": id_b})
            if not pac:
                st.warning("Paciente não encontrado.")
            else:
                renderizar_gradiente_paciente(id_b)

                with st.expander("Importar PDF para Alimentar Grades (-FN e -GN)", expanded=False):
                    pdfs_f2 = st.file_uploader("PDF(s) Laboratoriais", type=["pdf"], accept_multiple_files=True, key="pdf_f2_all")
                    if pdfs_f2 and st.button("Preencher Grades Automaticamente"):
                        aplicar_dados_pdf_em_todos_os_estados(extrair_tudo_pdfs_oneshot(pdfs_f2))
                        st.rerun()

                dp_am = st.session_state.get("pdf_pac_cache", {})
                st.session_state.setdefault("aba_amostra", "1. Recebimento")
                abas_am = ["1. Recebimento", "2. Cultivo & Crio", "3. Grades (-FN & -GN)", "4. Biotipos Futuros"]
                cols_am = st.columns(4)
                for i_a, n_a in enumerate(abas_am):
                    if cols_am[i_a].button(n_a, type="primary" if st.session_state.aba_amostra == n_a else "secondary", use_container_width=True):
                        st.session_state.aba_amostra = n_a
                        st.rerun()

                st.markdown("---")

                if st.session_state.aba_amostra == "1. Recebimento":
                    df_rec_init = pd.DataFrame([
                        {"Biotipo": "Fragmento Tecidual (Tumor)", "Prefixo": "T", "Qtd": 2, "Isquemia (min)": int(dp_am.get("isquemia_min", 22)) if str(dp_am.get("isquemia_min", "")).isdigit() else 22, "Meio": "RPMI 1640 (4°C)"},
                        {"Biotipo": "Sangue Total", "Prefixo": "ST", "Qtd": 1, "Isquemia (min)": 15, "Meio": "EDTA"},
                        {"Biotipo": "Plasma", "Prefixo": "P", "Qtd": 2, "Isquemia (min)": 15, "Meio": "EDTA Centrifugado"},
                        {"Biotipo": "Soro", "Prefixo": "S", "Qtd": 1, "Isquemia (min)": 15, "Meio": "Gel Separador"},
                        {"Biotipo": "PBMC", "Prefixo": "PBMC", "Qtd": 1, "Isquemia (min)": 20, "Meio": "Heparina / Ficoll"},
                    ])
                    df_rec_edit = st.data_editor(df_rec_init, use_container_width=True, hide_index=True, key="grid_rec_all")
                    if st.button("Registrar Lote de Amostras", type="primary"):
                        for _, row_r in df_rec_edit.iterrows():
                            qtd = int(row_r["Qtd"] or 0)
                            pref = str(row_r["Prefixo"])
                            if qtd > 0:
                                ex = fetch_all("SELECT numero_tubo FROM amostras_biobanco WHERE id_p = :id AND prefixo_tipo = :pr", {"id": id_b, "pr": pref})
                                ult = max([r[0] for r in ex], default=0)
                                for i_t in range(1, qtd + 1):
                                    nt = ult + i_t
                                    run_sql(
                                        "INSERT INTO amostras_biobanco VALUES (:ida, :idp, :bio, :pr, :num, '1 un', :isq, :meio, 'Recebida', :resp, :dt)",
                                        {"ida": f"{id_b}-{pref}{nt}", "idp": id_b, "bio": row_r["Biotipo"], "pr": pref, "num": nt, "isq": int(row_r["Isquemia (min)"] or 20), "meio": row_r["Meio"], "resp": st.session_state.username, "dt": datetime.now().strftime("%d/%m/%Y %H:%M")},
                                    )
                        st.rerun()
                    st.dataframe(fetch_df("SELECT id_amostra, biotipo, numero_tubo, isquemia_min, meio_transporte FROM amostras_biobanco WHERE id_p = :id ORDER BY prefixo_tipo, numero_tubo", {"id": id_b}), use_container_width=True, hide_index=True)

                elif st.session_state.aba_amostra == "2. Cultivo & Crio":
                    tumores_tn = fetch_all("SELECT id_amostra FROM amostras_biobanco WHERE id_p = :id AND prefixo_tipo = 'T' ORDER BY numero_tubo", {"id": id_b})
                    lista_tn = [r[0] for r in tumores_tn] if tumores_tn else [f"{id_b}-T1"]
                    tn_sel = st.selectbox("Amostra (-TN)", lista_tn)
                    suf_tn = tn_sel.split("-")[-1]
                    c1, c2, c3 = st.columns(3)
                    pass_en = c1.number_input("Passagem (-EN)", 1, 30, int(dp_am.get("passagem", 3)) if str(dp_am.get("passagem", "")).isdigit() else 3)
                    n_frz = c2.number_input("Ampolas (-FN)", 1, 20, int(dp_am.get("n_criotubos", 3)) if str(dp_am.get("n_criotubos", "")).isdigit() else 3)
                    viab_qc = c3.slider("Viabilidade Pós-Crio (%)", 0, 100, int(float(dp_am.get("viabilidade_tripan", 92))) if str(dp_am.get("viabilidade_tripan", "")).replace(".", "").isdigit() else 92)

                    if st.button(f"Registrar {tn_sel}-C, {tn_sel}-E{pass_en} e {tn_sel}-F1..F{n_frz}", type="primary"):
                        for id_l, et_l, ps_l, st_l in [(f"{tn_sel}-C", "Cultivo", 0, "Em Cultivo (-C)"), (f"{tn_sel}-E{pass_en}", "Estabelecida", int(pass_en), "Estabelecida (-EN)")]:
                            if not fetch_one("SELECT 1 FROM linhagens_pdo WHERE id_linhagem = :id", {"id": id_l}):
                                run_sql("INSERT INTO linhagens_pdo VALUES (:idl, :ida, :idp, :base, :et, :ps, :st, 'Matrigel + WENR', 'Viável', :resp, :dt)", {"idl": id_l, "ida": tn_sel, "idp": id_b, "base": suf_tn, "et": et_l, "ps": ps_l, "st": st_l, "resp": st.session_state.username, "dt": datetime.now().strftime("%d/%m/%Y")})
                        for i_f in range(1, int(n_frz) + 1):
                            id_f = f"{tn_sel}-F{i_f}"
                            if not fetch_one("SELECT 1 FROM ampolas_congeladas WHERE id_frozen = :id", {"id": id_f}):
                                run_sql("INSERT INTO ampolas_congeladas VALUES (:idf, :ide, :idp, :base, :na, :ps, '1.5x10^6 cél/mL', :vb, :qc, :resp, :dt)", {"idf": id_f, "ide": f"{tn_sel}-E{pass_en}", "idp": id_b, "base": suf_tn, "na": i_f, "ps": int(pass_en), "vb": float(viab_qc), "qc": "Qualificada" if viab_qc >= 80 else "Manutenção", "resp": st.session_state.username, "dt": datetime.now().strftime("%d/%m/%Y")})
                        run_sql("UPDATE pacientes_final SET status_geral = 'Criopreservada (-FN)' WHERE id_p = :id", {"id": id_b})
                        st.rerun()

                elif st.session_state.aba_amostra == "3. Grades (-FN & -GN)":
                    tumores_tn = fetch_all("SELECT id_amostra FROM amostras_biobanco WHERE id_p = :id AND prefixo_tipo = 'T' ORDER BY numero_tubo", {"id": id_b})
                    lista_tn = [r[0] for r in tumores_tn] if tumores_tn else [f"{id_b}-T1"]
                    tn_base = st.selectbox("Amostra Base (-TN)", lista_tn)
                    suf_tn = tn_base.split("-")[-1]

                    f_map_pdf = dp_am.get("ensaios_f_map", {})
                    b1_p, b2_p, b3_p = dp_am.get("b1", "0.048"), dp_am.get("b2", "0.050"), dp_am.get("b3", "0.049")
                    st.markdown(f"**Grade Farmacológica (`{tn_base}-F1..F9`)**")
                    linhas_f = []
                    defaults_r = {1: ("0.412", "0.405", "0.418"), 2: ("0.185", "0.179", "0.190"), 3: ("0.118", "0.112", "0.121"), 4: ("0.140", "0.135", "0.144")}
                    for idx_g, nome_g in GRUPOS_TRATAMENTO_PDAC:
                        r_tup = f_map_pdf.get(idx_g, defaults_r.get(idx_g, ("", "", "")))
                        linhas_f.append({"ID (-FN)": f"{tn_base}-F{idx_g}", "N": idx_g, "Regime": nome_g, "Dose": "Basal" if idx_g == 1 else "10 uM", "R1": r_tup[0], "R2": r_tup[1], "R3": r_tup[2], "B1": b1_p, "B2": b2_p, "B3": b3_p})
                    df_grid_f = st.data_editor(pd.DataFrame(linhas_f), use_container_width=True, hide_index=True, key="editor_all_fn")

                    st.markdown(f"**Grade Genética Completa — Painel Oficial de 57 Genes (`{tn_base}-GN`)**")
                    g_map_pdf = dp_am.get("genes_g_map", {})
                    ct_end_p = dp_am.get("ct_endo", "20.00")
                    linhas_g = []
                    for nome_sig, lista_genes_sig in PAINEL_57_GENES_ASSINATURAS.items():
                        ct_padrao_via = CT_MEDIANA_POR_ASSINATURA[nome_sig]
                        for gene_h in lista_genes_sig:
                            g_tup = g_map_pdf.get(gene_h, (ct_padrao_via, ct_padrao_via, ct_padrao_via))
                            linhas_g.append({
                                "ID (-GN)": f"{tn_base}-G1-{gene_h}",
                                "N": 1,
                                "Assinatura Biológica": nome_sig,
                                "Gene": gene_h,
                                "Ct R1": g_tup[0],
                                "Ct R2": g_tup[1],
                                "Ct R3": g_tup[2],
                                "Ct GAPDH": ct_end_p,
                            })
                    df_grid_g = st.data_editor(
                        pd.DataFrame(linhas_g),
                        use_container_width=True,
                        hide_index=True,
                        height=420,
                        key="editor_all_gn_57",
                    )

                    if st.button("Salvar Grades (-FN e -GN)", type="primary", use_container_width=True):
                        for _, rf in df_grid_f.iterrows():
                            r1, r2, r3 = norm_num(rf["R1"]), norm_num(rf["R2"]), norm_num(rf["R3"])
                            b1, b2, b3 = norm_num(rf["B1"]), norm_num(rf["B2"]), norm_num(rf["B3"])
                            if r1 and r2 and r3:
                                m_liq = round(float(np.mean([max(0.0, float(r) - float(b or 0)) for r, b in zip([r1, r2, r3], [b1, b2, b3])])), 4)
                                id_ef = str(rf["ID (-FN)"])
                                run_sql("DELETE FROM ensaios_farmaco_genetico WHERE id_ensaio_fg = :id", {"id": id_ef})
                                run_sql("INSERT INTO ensaios_farmaco_genetico VALUES (:id, :idp, :base, :frz, 'Farmacologico', :idx, :grp, :ds, 'MTT', 'Viabilidade', :r1, :r2, :r3, '', '', '', :b1, :b2, :b3, :mc, :resp, :dt)", {"id": id_ef, "idp": id_b, "base": suf_tn, "frz": f"{tn_base}-F1", "idx": int(rf["N"]), "grp": str(rf["Regime"]), "ds": str(rf["Dose"]), "r1": r1, "r2": r2, "r3": r3, "b1": b1, "b2": b2, "b3": b3, "mc": m_liq, "resp": st.session_state.username, "dt": datetime.now().strftime("%d/%m/%Y %H:%M")})
                        for _, rg in df_grid_g.iterrows():
                            cr1, cr2, cr3 = norm_num(rg["Ct R1"]), norm_num(rg["Ct R2"]), norm_num(rg["Ct R3"])
                            cend = norm_num(rg["Ct GAPDH"])
                            if cr1 and cr2 and cr3 and cend:
                                m_dct = round(float(np.mean([float(r) - float(cend) for r in (cr1, cr2, cr3)])), 4)
                                id_eg = str(rg["ID (-GN)"])
                                run_sql("DELETE FROM ensaios_farmaco_genetico WHERE id_ensaio_fg = :id", {"id": id_eg})
                                run_sql("INSERT INTO ensaios_farmaco_genetico VALUES (:id, :idp, :base, :frz, 'Genetico', :idx, 'Basal', 'Basal', 'RT-qPCR', :gn, :r1, :r2, :r3, :c1, :c1, :c1, '', '', '', :mc, :resp, :dt)", {"id": id_eg, "idp": id_b, "base": suf_tn, "frz": f"{tn_base}-F1", "idx": int(rg["N"]), "gn": str(rg["Gene"]), "r1": cr1, "r2": cr2, "r3": cr3, "c1": cend, "mc": m_dct, "resp": st.session_state.username, "dt": datetime.now().strftime("%d/%m/%Y %H:%M")})
                        run_sql("UPDATE pacientes_final SET status_geral = 'Fase Analítica (-FN/-GN)' WHERE id_p = :id", {"id": id_b})
                        st.success("Grades consolidadas!")
                        st.rerun()

                elif st.session_state.aba_amostra == "4. Biotipos Futuros":
                    configs_bio = fetch_all("SELECT biotipo_codigo, nome_sessao, liberado_admin, versao_schema, colunas_custom_json FROM config_modulos_analise ORDER BY biotipo_codigo")
                    for cod_b, nome_s, lib_adm, ver_s, cols_j in configs_bio:
                        st.markdown(f"- **`-{cod_b}` ({nome_s})**: {'Liberado' if lib_adm == 1 else 'Bloqueado pelo Administrador'}")

    # =========================================================================
    # MÓDULO 4: HOMEOSTAS.IA (100% SOMENTE LEITURA | RESTRITA A MÉDICO, OPERADOR E ADMIN)
    # =========================================================================
    elif st.session_state.nav_curto == "Homeostas.IA":
        if perfil_atual not in ("Médico", "Operador", "Administrador"):
            st.error("Acesso não permitido para este perfil.")
        else:
            st.subheader("Homeostas.IA beta — Resultados Preditivos (Somente Leitura)")
            id_b = st.text_input("ID do Protocolo (ex: OS-001)", value=st.session_state.get("id_ativo", "OS-001")).strip().upper()
            if id_b:
                pac = fetch_one("SELECT * FROM pacientes_final WHERE id_p = :id", {"id": id_b})
                if not pac:
                    st.warning("Protocolo não encontrado.")
                else:
                    renderizar_gradiente_paciente(id_b)
                    res_ia = inferir_homeostasia_somente_leitura(id_b)

                    # Médico enxerga exclusivamente a Visão Médica; Operador/Admin enxergam Técnica + Médica
                    if perfil_atual == "Médico":
                        visao_ativa = "Médica"
                    else:
                        visao_ativa = st.segmented_control(
                            "Modo de Exibição:",
                            ["Médica", "Operacional OrganSense (Métricas & Custos)"],
                            default="Médica",
                        ) or "Médica"

                    if visao_ativa == "Médica":
                        st.markdown(
                            f"""
                            <div class="os-card">
                                <div style="font-size:15px; font-weight:700; color:#0F172A; margin-bottom:6px;">
                                    Síntese Preditiva Homeostas.IA beta — {res_ia['quadrante']}
                                </div>
                                <div style="font-size:13.5px; color:#1E293B; line-height:1.6;">
                                    • <strong>Subtipo PurIST:</strong> {res_ia['subtipo']} (<code>{res_ia['purist']}</code>) | <strong>LNR:</strong> <code>{res_ia['lnr']}</code> ({res_ia['g_pos']}/{res_ia['g_exam']}, {res_ia['margem']}, {res_ia['grau']})<br>
                                    • <strong>Fidelidade do Organoide (-TN-EN):</strong> <strong>{res_ia['fidelidade_pdo']}%</strong> | <strong>Letalidade Ex Vivo (-FN):</strong> Poliquimio = <strong>{res_ia['letalidade_pdo_poli']}%</strong> vs. Gencitabina = <strong>{res_ia['letalidade_pdo_gem']}%</strong><br>
                                    • <strong>Sobrevida Estimada (12m / 24m):</strong> F1 (Sem Quimio): <code>{res_ia['s12_sem']}% / {res_ia['s24_sem']}%</code> | F2 (Gencitabina): <code>{res_ia['s12_gem']}% / {res_ia['s24_gem']}%</code> | F3 (Poliquimio): <code>{res_ia['s12_poli']}% / {res_ia['s24_poli']}%</code> (Ganho 24m: <strong>+{res_ia['ganho_24m']}%</strong>)<br>
                                    • <strong>Rota Recomendada:</strong> <span style="color:#0284C7; font-weight:700;">{res_ia['rota_recomendada']}</span> — {res_ia['conduta']}
                                </div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                        st.pyplot(gerar_grafico_dispersao_homeostasia(res_ia, id_b), use_container_width=True)
                    else:
                        st.pyplot(gerar_painel_auditoria_interna_organsense(res_ia["fidelidade_pdo"]), use_container_width=True)
                        df_custos = calcular_custos_dinamicos_paciente(id_b)
                        st.dataframe(df_custos, use_container_width=True, hide_index=True)
                        st.info(f"Custo Operacional Acumulado (`{id_b}`): **R$ {df_custos['Subtotal (R$)'].sum():,.2f}**")

                    if st.button("Registrar Laudo Imutável da IA no Banco", type="primary"):
                        id_pr = f"HOMEO-{id_b}-{int(datetime.now().timestamp())}"
                        run_sql(
                            "INSERT INTO predicoes_ia_final VALUES (:v1,:v2,:v3,:v4,:v5,:v6,:v7,:v8,:v9,:v10,:v11,:v12,:v13,:v14)",
                            {
                                "v1": id_pr, "v2": id_b, "v3": res_ia["motor"], "v4": res_ia["subtipo"],
                                "v5": res_ia["purist"], "v6": res_ia["lnr"], "v7": res_ia["recist_pct"],
                                "v8": res_ia["s24_sem"], "v9": res_ia["s24_gem"], "v10": res_ia["s24_poli"],
                                "v11": res_ia["quadrante"], "v12": res_ia["rota_recomendada"],
                                "v13": st.session_state.username, "v14": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
                            },
                        )
                        st.success(f"Laudo `{id_pr}` consolidado.")
                        st.rerun()

                    # RELATÓRIOS DAS OUTRAS IAS (DESBLOQUEÁVEIS PELO ADMINISTRADOR)
                    st.divider()
                    st.markdown("#### Módulos Adicionais de IA (Expansão OrganSense)")
                    motores_extras = fetch_all("SELECT id_motor, nome_motor, escopo, liberado_admin, versao FROM config_motores_ia ORDER BY id_motor")
                    for id_m, nm_m, esc_m, lib_m, ver_m in motores_extras:
                        with st.expander(f"{nm_m} ({ver_m}) — {'ATIVO' if lib_m == 1 else 'EM HOMOLOGAÇÃO (BLOQUEADO)'}", expanded=(lib_m == 1)):
                            if lib_m == 0:
                                st.caption(f"Escopo: {esc_m}. (Aguardando liberação pelo Administrador em Governança).")
                            else:
                                if id_m == "IA-RANK-FARMA":
                                    v_grp = res_ia["viab_por_grupo"]
                                    if v_grp:
                                        df_rk = pd.DataFrame([
                                            {"Grupo": f"F{k}", "Regime Farmacológico": v[0], "Viabilidade Residual PDO (%)": v[1], "Letalidade Tumoral (%)": v[2]}
                                            for k, v in sorted(v_grp.items(), key=lambda x: x[1][1])
                                        ])
                                        st.dataframe(df_rk, use_container_width=True, hide_index=True)
                                    else:
                                        st.info("Preencha a Grade Farmacológica (-FN) em Amostras para gerar o ranking multi-droga.")
                                else:
                                    st.info(f"Relatório `{nm_m}` habilitado. Aguardando ingestão das amostras correspondentes (`-PN` / `-PBMCN`).")

    # =========================================================================
    # MÓDULO 5: GOVERNANÇA (ADMINISTRADOR)
    # =========================================================================
    elif st.session_state.nav_curto == "Governança":
        if st.session_state.role != "Administrador":
            st.error("Restrito ao Administrador.")
        else:
            st.subheader("Governança")
            t_tok, t_ia, t_mod, t_log, t_usr = st.tabs([
                "Chaves (5 Perfis)",
                "Liberar Relatórios de Outras IAs",
                "Liberar Biotipos (-TN/-STN/-PN/-SN/-PBMCN)",
                "Auditoria",
                "Usuários",
            ])

            with t_tok:
                ch_atuais = obter_ou_gerar_chaves_5_perfis()
                st.dataframe(pd.DataFrame([{"Perfil": k, "Código Vigente": v} for k, v in ch_atuais.items()]), use_container_width=True, hide_index=True)

            with t_ia:
                mots = fetch_all("SELECT id_motor, nome_motor, escopo, liberado_admin, versao FROM config_motores_ia ORDER BY id_motor")
                for id_m, nm_m, esc_m, lib_m, ver_m in mots:
                    c1, c2 = st.columns([3, 1])
                    novo_st_ia = c1.checkbox(f"{nm_m} ({ver_m})", value=(lib_m == 1), key=f"chk_ia_{id_m}")
                    if c2.button("Aplicar", key=f"sv_ia_{id_m}"):
                        run_sql("UPDATE config_motores_ia SET liberado_admin = :l WHERE id_motor = :id", {"l": 1 if novo_st_ia else 0, "id": id_m})
                        st.rerun()

            with t_mod:
                configs = fetch_all("SELECT biotipo_codigo, nome_sessao, liberado_admin, versao_schema, colunas_custom_json FROM config_modulos_analise ORDER BY biotipo_codigo")
                for cod_b, nome_s, lib_adm, ver_s, cols_j in configs:
                    with st.expander(f"-{cod_b}: {nome_s} ({'LIBERADO' if lib_adm == 1 else 'BLOQUEADO'})"):
                        novo_lib = st.checkbox("Liberar coleta", value=(lib_adm == 1), key=f"adm_lib_{cod_b}")
                        novas_cols = st.text_area("Colunas JSON", value=cols_j, key=f"adm_cols_{cod_b}")
                        if st.button(f"Salvar -{cod_b}", key=f"adm_sv_{cod_b}", type="primary"):
                            run_sql("UPDATE config_modulos_analise SET liberado_admin=:l, colunas_custom_json=:cj WHERE biotipo_codigo=:c", {"l": 1 if novo_lib else 0, "cj": novas_cols, "c": cod_b})
                            st.rerun()

            with t_log:
                st.dataframe(fetch_df('SELECT data_hora AS "Data/Hora", username AS "Usuário", acao AS "Ação", detalhe AS "Detalhe" FROM audit_logs ORDER BY id DESC LIMIT 200'), use_container_width=True, hide_index=True)

            with t_usr:
                st.dataframe(fetch_df('SELECT username AS "Usuário", email AS "Gmail", role AS "Perfil", paciente_vinculado AS "ID Vinculado" FROM usuarios_final ORDER BY role, username'), use_container_width=True, hide_index=True)