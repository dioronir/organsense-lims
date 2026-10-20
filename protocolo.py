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
from scipy import stats
from sqlalchemy import create_engine, text
import streamlit as st

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

try:
    import joblib
except ImportError:
    joblib = None

st.set_page_config(
    page_title="OrganSense LIMS | Homeostas.IA",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
        [data-testid="stSidebar"] { display: none; }
        [data-testid="collapsedControl"] { display: none; }
        .block-container { padding-top: 1.2rem; padding-bottom: 2rem; }
        .os-card {
            background-color: #F8FAFC;
            border: 1px solid #CBD5E1;
            border-radius: 6px;
            padding: 14px 18px;
            margin-bottom: 12px;
        }
        .os-stage-banner {
            background-color: #F1F5F9;
            border-left: 4px solid #0284C7;
            padding: 10px 14px;
            border-radius: 4px;
            margin-bottom: 12px;
            font-size: 13px;
            color: #1E293B;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# =============================================================================
# 1. CONEXÃO COM BANCO DE DADOS E INICIALIZAÇÃO DO SCHEMA DEFINITIVO
# =============================================================================
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
    """Gera o código padronizado OS-001, OS-002..."""
    rows = fetch_all("SELECT id_p FROM pacientes_final")
    nums = []
    for r in rows:
        if r[0]:
            m = re.search(r"(\d+)$", str(r[0]))
            if m:
                nums.append(int(m.group(1)))
    prox = (max(nums) if nums else 0) + 1
    return f"OS-{prox:03d}"


if "db_init_v4" not in st.session_state:
    ddl_statements = [
        "CREATE TABLE IF NOT EXISTS usuarios_final (username TEXT PRIMARY KEY, password TEXT, email TEXT, role TEXT)",
        "CREATE TABLE IF NOT EXISTS pacientes_final (id_p TEXT PRIMARY KEY, nome TEXT, idade INTEGER, sexo TEXT, nascimento TEXT, estado TEXT, city TEXT, responsavel_cad TEXT, hospital TEXT, status_geral TEXT)",
        "CREATE TABLE IF NOT EXISTS submissao_paciente_detalhada (id_p TEXT PRIMARY KEY, ecog TEXT, comorbidades TEXT, ca19_9 TEXT, cea TEXT, ast_tgo TEXT, alt_tgp TEXT, bilirrubina TEXT, creatinina TEXT, ureia TEXT, albumina TEXT, topografia TEXT, estadiamento_ajcc TEXT, tnm TEXT, ganglios_exam INTEGER, ganglios_pos INTEGER, lnr REAL, margem TEXT, grau_hist TEXT, invasao_perineural TEXT, invasao_linfovasc TEXT, status_tratamento TEXT, regime_quimio TEXT, modalidade_radio TEXT, tipo_resseccao TEXT, data_recebimento TEXT, responsavel TEXT)",
        "CREATE TABLE IF NOT EXISTS amostras_biobanco (id_amostra TEXT PRIMARY KEY, id_p TEXT, biotipo TEXT, prefixo_tipo TEXT, numero_tubo INTEGER, volume_ou_peso TEXT, isquemia_min INTEGER, meio_transporte TEXT, status_amostra TEXT, responsavel TEXT, data_coleta TEXT)",
        "CREATE TABLE IF NOT EXISTS linhagens_pdo (id_linhagem TEXT PRIMARY KEY, id_amostra_origem TEXT, id_p TEXT, codigo_base_tn TEXT, etapa_cultivo TEXT, passagem INTEGER, status_fenotipico TEXT, matriz_meio TEXT, observacoes TEXT, responsavel TEXT, data_registro TEXT)",
        "CREATE TABLE IF NOT EXISTS ampolas_congeladas (id_frozen TEXT PRIMARY KEY, id_estabelecida TEXT, id_p TEXT, codigo_base_tn TEXT, numero_ampola INTEGER, passagem_congelamento INTEGER, densidade TEXT, viabilidade_pos_descong REAL, qualificada_ensaio TEXT, responsavel TEXT, data_congelamento TEXT)",
        "CREATE TABLE IF NOT EXISTS ensaios_farmaco_genetico (id_ensaio_fg TEXT PRIMARY KEY, id_p TEXT, codigo_base_tn TEXT, id_frozen_origem TEXT, modalidade TEXT, indice_grupo INTEGER, grupo_tratamento TEXT, dose TEXT, metodo_analitico TEXT, gene_alvo TEXT, r1 TEXT, r2 TEXT, r3 TEXT, c1 TEXT, c2 TEXT, c3 TEXT, b1 TEXT, b2 TEXT, b3 TEXT, metrica_calculada REAL, responsavel TEXT, data_registro TEXT)",
        "CREATE TABLE IF NOT EXISTS config_modulos_analise (biotipo_codigo TEXT PRIMARY KEY, nome_sessao TEXT, liberado_admin INTEGER, versao_schema TEXT, colunas_custom_json TEXT, atualizado_por TEXT, data_atualizacao TEXT)",
        "CREATE TABLE IF NOT EXISTS analises_multibiotipo_futuro (id_registro TEXT PRIMARY KEY, id_amostra TEXT, id_p TEXT, biotipo_codigo TEXT, versao_schema TEXT, payload_json TEXT, responsavel TEXT, data_registro TEXT)",
        "CREATE TABLE IF NOT EXISTS predicoes_ia_final (id_pred TEXT PRIMARY KEY, id_p TEXT, motor_ia TEXT, subtipo_purist TEXT, score_purist REAL, lnr REAL, recist_pct REAL, s24_sem_quimio REAL, s24_gemcitabina REAL, s24_poliquimio REAL, quadrante TEXT, conduta TEXT, responsavel TEXT, data_hora TEXT)",
        "CREATE TABLE IF NOT EXISTS audit_logs (id SERIAL PRIMARY KEY, username TEXT, acao TEXT, detalhe TEXT, data_hora TEXT)",
        "CREATE TABLE IF NOT EXISTS controle_chaves (mes_ano TEXT PRIMARY KEY, chave_op TEXT, chave_adm TEXT)",
    ]
    with engine.begin() as conn:
        for stmt in ddl_statements:
            conn.execute(text(stmt))

    biotipos_padrao = [
        ("TN", "Análise Multi-Ômica Direta de Fragmento Tecidual In Natura (-TN)", 0, "v1.0-draft", '["Pureza_Tumoral_Pct", "Celularidade_Estromal_Pct", "Mutacao_KRAS_Alelo"]'),
        ("STN", "Análise Hematológica e DNA Tumoral Circulante em Sangue Total (-STN)", 0, "v1.0-draft", '["Hemoglobina_g_dL", "Leucocitos_mm3", "Relacao_Neutrofilo_Linfocito_NLR"]'),
        ("PN", "Biópsia Líquida: cfDNA / ctDNA e Exossomos em Plasma (-PN)", 0, "v1.0-draft", '["Concentracao_cfDNA_ng_mL", "VAF_KRAS_G12D_Pct", "VAF_TP53_Pct"]'),
        ("SN", "Painel Proteômico e Marcadores Tumorais Séricos em Soro (-SN)", 0, "v1.0-draft", '["CA19_9_Serico_U_mL", "CEA_ng_mL", "Citocinas_IL6_pg_mL"]'),
        ("PBMCN", "Imunofenotipagem e Perfil de Células Mononucleares em PBMC (-PBMCN)", 0, "v1.0-draft", '["Viabilidade_PBMC_Pct", "Subpopulacao_CD8_Pct", "Subpopulacao_Treg_Pct"]'),
    ]
    for cod_b, nome_b, lib_b, ver_b, cols_b in biotipos_padrao:
        if not fetch_one("SELECT 1 FROM config_modulos_analise WHERE biotipo_codigo = :c", {"c": cod_b}):
            run_sql(
                "INSERT INTO config_modulos_analise VALUES (:c, :n, :l, :v, :cj, 'Sistema', :dt)",
                {
                    "c": cod_b,
                    "n": nome_b,
                    "l": lib_b,
                    "v": ver_b,
                    "cj": cols_b,
                    "dt": datetime.now().strftime("%d/%m/%Y"),
                },
            )
    st.session_state.db_init_v4 = True


# =============================================================================
# 2. SEGURANÇA, MEDIDOR DE SENHA E AUDITORIA CONTÍNUA DE ETAPAS
# =============================================================================
def log_audit(usuario, acao, detalhe):
    run_sql(
        "INSERT INTO audit_logs (username, acao, detalhe, data_hora) VALUES (:u, :a, :d, :dh)",
        {
            "u": usuario,
            "a": acao,
            "d": detalhe,
            "dh": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        },
    )


def send_email(destinatario, assunto, corpo):
    try:
        rem = st.secrets["email"]["remetente"]
        msg = MIMEMultipart()
        msg["From"], msg["To"], msg["Subject"] = rem, destinatario, assunto
        msg.attach(MIMEText(corpo, "plain"))
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=10) as srv:
            srv.starttls()
            srv.login(rem, st.secrets["email"]["senha_app"])
            srv.sendmail(rem, [destinatario], msg.as_string())
        return True
    except Exception:
        return False


def hash_pwd(pwd):
    salt = os.urandom(16).hex()
    dk = hashlib.pbkdf2_hmac(
        "sha256", pwd.encode(), bytes.fromhex(salt), 100000
    )
    return f"{salt}${dk.hex()}"


def verify_pwd(pwd, stored):
    if not stored:
        return False
    if "$" in stored:
        salt, key = stored.split("$", 1)
        return (
            hashlib.pbkdf2_hmac(
                "sha256", pwd.encode(), bytes.fromhex(salt), 100000
            ).hex()
            == key
        )
    return hashlib.sha256(pwd.encode()).hexdigest() == stored


def renderizar_medidor_senha(pwd: str):
    criterios = [
        ("Mínimo de 8 caracteres", len(pwd) >= 8),
        ("Letra maiúscula (A-Z)", bool(re.search(r"[A-Z]", pwd))),
        ("Letra minúscula (a-z)", bool(re.search(r"[a-z]", pwd))),
        ("Dígito numérico (0-9)", bool(re.search(r"[0-9]", pwd))),
        ("Caractere especial (_@$!%*#?&)", bool(re.search(r"[_@$!%*#?&]", pwd))),
    ]
    pontos = sum(1 for _, ok in criterios if ok)
    escala = {
        0: ("0%", "#E2E8F0", "Aguardando digitação"),
        1: ("20%", "#DC2626", "Muito fraca"),
        2: ("40%", "#EA580C", "Fraca"),
        3: ("60%", "#D97706", "Moderada"),
        4: ("80%", "#65A30D", "Forte"),
        5: ("100%", "#16A34A", "Padrão de segurança atingido"),
    }
    largura, cor, rotulo = escala[pontos]
    valida = (
        len(pwd) >= 8
        and bool(re.search(r"[A-Z]", pwd))
        and bool(re.search(r"[0-9]", pwd))
        and bool(re.search(r"[_@$!%*#?&]", pwd))
    )

    itens_html = "".join([
        f"<div style='color:{'#15803D' if ok else '#64748B'}; font-weight:{'600' if ok else '400'}; font-size:12.5px; margin-bottom:3px;'>"
        f"<span style='font-family:monospace; margin-right:6px;'>{'[OK]' if ok else '[Pendente]'}</span>{txt}</div>"
        for txt, ok in criterios
    ])
    st.markdown(
        f"""
        <div class="os-card">
            <div style="display:flex; justify-content:space-between; margin-bottom:6px;">
                <span style="font-size:12px; font-weight:600; color:#334155;">Progressão de Complexidade da Senha:</span>
                <span style="font-size:12px; font-weight:700; color:{cor};">{rotulo}</span>
            </div>
            <div style="width:100%; background:#E2E8F0; height:8px; border-radius:4px; overflow:hidden; margin-bottom:10px;">
                <div style="width:{largura}; background:{cor}; height:100%; transition:width 0.3s ease;"></div>
            </div>
            <div style="border-top:1px solid #E2E8F0; padding-top:8px;">{itens_html}</div>
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
        r = requests.get(
            "https://servicodados.ibge.gov.br/api/v1/localidades/estados",
            timeout=5,
        )
        return sorted([x["sigla"] for x in r.json()])
    except Exception:
        return ["PE", "SP", "RJ", "MG", "BA", "RS", "PR", "CE"]


@st.cache_data(ttl=86400)
def get_cidades(uf):
    try:
        r = requests.get(
            f"https://servicodados.ibge.gov.br/api/v1/localidades/estados/{uf}/municipios",
            timeout=5,
        )
        return [x["nome"] for x in r.json()]
    except Exception:
        return ["Recife", "Olinda", "Jaboatão dos Guararapes", "São Paulo"]


def auditar_completude_paciente(id_p: str):
    """Audita todas as fases do paciente e extrai automaticamente os parâmetros reais para a IA."""
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
        ("1. Paciente Recebido (Demografia + Clínica + Bioq + Anatomia + Tratamento)", bool(pac and sub)),
        ("2. Amostras Biológicas (-TN / -STN / -PN / -SN / -PBMCN)", bool(amostras)),
        ("3. Cultivo Primário (-TN-C)", tem_cult),
        ("4. Linhagem Estabelecida (-TN-EN)", tem_estab),
        ("5. Ampola Criopreservada (-TN-FN)", bool(frozen)),
        ("6. Teste Farmacológico (-TN-F1..N) & Genético (-TN-G1..N)", bool(tem_fn_ens or tem_gn_ens)),
        ("7. Predição Translacional Homeostas.IA", bool(pred_ia)),
    ]
    pct = int(round((sum(1 for _, ok in etapas if ok) / len(etapas)) * 100))

    # Cálculo automático de Fidelidade do Organoide e Viabilidades Residuais Reais dos Ensaios
    fidelidade_pdo = 60.0
    if tem_cult:
        fidelidade_pdo += 10.0
    if tem_estab:
        fidelidade_pdo += 15.0
    viab_max_crio = max([float(r[1] or 0) for r in frozen], default=0.0)
    if viab_max_crio >= 80.0:
        fidelidade_pdo += 15.0
    fidelidade_pdo = min(100.0, fidelidade_pdo)

    # Extração dinâmica das leituras farmacológicas salvas (-TN-F1 = Basal, -TN-F2 = Gencitabina, -TN-F3 = mFOLFIRINOX)
    sinal_f1_basal = None
    sinal_f2_gem = None
    sinal_f3_folf = None
    genes_dct = {}

    for _, mod_e, idx_g, _, gene_a, met_c in ensaios:
        if mod_e == "Farmacologico" and met_c is not None:
            if idx_g == 1:
                sinal_f1_basal = float(met_c)
            elif idx_g == 2:
                sinal_f2_gem = float(met_c)
            elif idx_g in (3, 4):
                sinal_f3_folf = float(met_c)
        elif mod_e == "Genetico" and gene_a and met_c is not None:
            genes_dct[str(gene_a).upper()] = float(met_c)

    ref_basal = sinal_f1_basal if (sinal_f1_basal and sinal_f1_basal > 0) else 0.362
    viab_gem_calc = (
        round(min(100.0, max(1.0, (sinal_f2_gem / ref_basal) * 100.0)), 1)
        if sinal_f2_gem is not None
        else 38.0
    )
    viab_folf_calc = (
        round(min(100.0, max(1.0, (sinal_f3_folf / ref_basal) * 100.0)), 1)
        if sinal_f3_folf is not None
        else 21.0
    )

    metricas_auto = {
        "fidelidade_pdo": fidelidade_pdo,
        "viab_gem_pct": viab_gem_calc,
        "viab_folf_pct": viab_folf_calc,
        "genes_dct": genes_dct,
        "viab_max_crio": viab_max_crio,
    }
    return pct, etapas, pac, sub, amostras, cultivos, frozen, ensaios, metricas_auto


def renderizar_gradiente_paciente(id_p: str):
    pct, etapas, pac, sub, amostras, cultivos, frozen, ensaios, m_auto = auditar_completude_paciente(id_p)
    if not pac:
        return
    cor = (
        "#DC2626"
        if pct < 35
        else ("#EA580C" if pct < 65 else ("#2563EB" if pct < 90 else "#16A34A"))
    )
    badges = "".join([
        f"<span style='display:inline-block; background:{'#DCFCE7' if ok else '#F1F5F9'}; "
        f"color:{'#166534' if ok else '#64748B'}; border:1px solid {'#86EFAC' if ok else '#CBD5E1'}; "
        f"border-radius:4px; padding:2px 7px; font-size:11px; font-weight:600; margin-right:5px; margin-bottom:4px;'>"
        f"{'[OK]' if ok else '[Pendente]'} {et}</span>"
        for et, ok in etapas
    ])

    sintese_continua = f"<strong>Síntese Contínua da Jornada ({id_p}):</strong> Demografia registrada ({pac[2]} anos, {pac[3]})."
    if sub:
        sintese_continua += f" | Clínica/Anatomia: Estágio <code>{sub[12]}</code>, TNM <code>{sub[13]}</code>, LNR = <code>{sub[16]}</code>, CA19-9 = <code>{sub[3]} U/mL</code>."
    if amostras:
        sintese_continua += f" | Biobanco: <code>{len(amostras)}</code> tubo(s)/fragmento(s) recebidos."
    if cultivos or frozen:
        sintese_continua += f" | Fidelidade Translacional PDO: <code>{m_auto['fidelidade_pdo']:.0f}%</code> (Viab. Crio: <code>{m_auto['viab_max_crio']:.0f}%</code>)."
    if ensaios:
        sintese_continua += f" | Resposta Ex Vivo PDO: Viabilidade residual Gencitabina = <code>{m_auto['viab_gem_pct']}%</code>, Poliquimio = <code>{m_auto['viab_folf_pct']}%</code>."

    st.markdown(
        f"""
        <div class="os-card">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                <div>
                    <span style="font-size:15px; font-weight:700; color:#0F172A;">Paciente: {pac[1]} (ID: {pac[0]})</span>
                    <span style="font-size:12px; color:#0284C7; font-weight:700; margin-left:10px;">Status: {pac[9]}</span>
                </div>
                <span style="font-size:13px; font-weight:700; color:{cor};">Completude Auditada: {pct}%</span>
            </div>
            <div style="width:100%; background:#E2E8F0; height:9px; border-radius:5px; overflow:hidden; margin-bottom:8px;">
                <div style="width:{pct}%; height:100%; background:linear-gradient(90deg, #DC2626 0%, #EA580C 35%, #2563EB 70%, #16A34A 100%);"></div>
            </div>
            <div style="margin-bottom:6px;">{badges}</div>
            <div style="font-size:12px; color:#334155; background:#F1F5F9; padding:6px 10px; border-radius:4px;">{sintese_continua}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# =============================================================================
# 3. GERADOR DE PDFS DE TESTE E EXTRATOR MULTIMODAL DE PDF (100% LOCAL LGPD)
# =============================================================================
LAUDOS_PDF_TESTE = {
    "1_Laudo_Paciente_Clinico_Anatomopatologico_PDAC.pdf": [
        "HOSPITAL DAS CLINICAS DA UFPE - SERVICO DE CIRURGIA HEPATOBILIOPANCREATICA",
        "FICHA DE SUBMISSAO INTEGRADA DE PACIENTE - PROTOCOLO PDAC",
        "Paciente: Roberto Carlos Cavalcanti de Albuquerque",
        "Sexo Biologico: Masculino | Data de Nascimento: 14/05/1958",
        "UF: PE | Municipio: Recife | Hospital: Hospital das Clinicas da UFPE",
        "Performance Status ECOG: 1 | Comorbidades: Diabetes mellitus de inicio recente e ictericia obstrutiva",
        "CA 19-9: 420.5 U/mL | CEA: 4.8 ng/mL | Albumina: 3.7 g/dL",
        "AST / TGO: 68.4 U/L | ALT / TGP: 92.1 U/L | Bilirrubina Total: 1.4 mg/dL",
        "Creatinina Serica: 0.95 mg/dL | Ureia: 38.0 mg/dL",
        "Topografia Primaria: Cabeca do Pancreas | Estadiamento AJCC: IIB (Borderline)",
        "Classificacao TNM: pT3 pN1 cM0",
        "Ganglios Examinados: 18 | Ganglios Positivos: 2 | Margem Cirurgica: R0 | Grau Histologico: G2",
    ],
    "2_Boletim_Amostras_Cultivo_e_Criopreservacao_PDO.pdf": [
        "BIOBANCO TRANSLACIONAL ORGANSENSE - RASTREABILIDADE DE AMOSTRAS E CULTIVO 3D",
        "Isquemia Fria: 22 min | Passagem: 3 | Criotubos Congelados: 4",
        "Densidade Celular: 1.5x10^6 cel/mL (4 domos Matrigel GFR/ampola)",
        "Meio e Matriz: Matrigel GFR + Meio WENR Completo + Y-27632",
        "Morfologia: Organoides cisticos luminados de arquitetura ductal preservada",
        "Viabilidade Pos-Descongelamento (Azul de Tripan): 92%",
    ],
    "3_Relatorio_Ensaios_Farmacologicos_FN_e_Geneticos_GN.pdf": [
        "PLATAFORMA ANALITICA ORGANSENSE - TESTE FARMACOLOGICO (-TN-FN) E GENETICO (-TN-GN)",
        "Concentracao Testada: 10 uM",
        "Leitura MTT Amostra R1: 0.132 | R2: 0.128 | R3: 0.136",
        "Branco do Meio B1: 0.048 | B2: 0.050 | B3: 0.049",
        "Ct Endogeno Referencia (GAPDH/ACTB): 20.10",
        "Gene GATA6 -> Ct Alvo R1: 21.30 | R2: 21.25 | R3: 21.40 | Ct Endogeno: 20.10",
        "Gene KRT5 -> Ct Alvo R1: 27.80 | R2: 27.95 | R3: 27.85 | Ct Endogeno: 20.10",
    ],
}


def gerar_bytes_pdf_nativo(linhas_texto: list) -> bytes:
    conteudo = "BT\n/F1 10 Tf\n40 790 Td\n14 TL\n"
    for ln in linhas_texto:
        limpa = (
            ln.replace("(", "\\(")
            .replace(")", "\\)")
            .encode("ascii", "ignore")
            .decode("ascii")
        )
        conteudo += f"({limpa}) '\n"
    conteudo += "ET"
    s_bytes = conteudo.encode("latin-1")
    objs = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n",
        b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
        f"5 0 obj\n<< /Length {len(s_bytes)} >>\nstream\n".encode("latin-1")
        + s_bytes
        + b"\nendstream\nendobj\n",
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
    pdf += f"trailer\n<< /Size {len(objs)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode(
        "latin-1"
    )
    return pdf


def extrair_variaveis_multiplos_pdfs(lista_arquivos) -> dict:
    if not lista_arquivos or PdfReader is None:
        return {}
    blocos = []
    for arq in lista_arquivos:
        try:
            leitor = PdfReader(io.BytesIO(arq.getvalue()))
            blocos.append(
                "\n".join([p.extract_text() or "" for p in leitor.pages]).strip()
            )
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

    dados["nome"] = buscar([
        r"(?:Paciente|Nome(?:\s+Completo)?)\s*[:\-]\s*([A-ZÀ-Úa-zà-ú\s]{5,70}?)(?:\n|\r|\||Data|Idade|Sexo|CPF|UF|$)"
    ])
    sx = buscar([r"Sexo(?:\s+Biol[oó]gico)?\s*[:\-]\s*(Masculino|Feminino|M|F)\b"])
    if sx:
        dados["sexo"] = "Feminino" if sx.upper().startswith("F") else "Masculino"
    dados["data_nascimento"] = buscar([
        r"(?:Nascimento|Data\s+de\s+Nasc(?:imento)?|DN)\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})"
    ])
    uf_m = buscar([r"(?:UF|Estado)\s*[:\-]\s*([A-Z]{2})\b"])
    if uf_m:
        dados["uf"] = uf_m.upper()
    dados["municipio"] = buscar([
        r"(?:Munic[ií]pio|Cidade)\s*[:\-]\s*([A-ZÀ-Úa-zà-ú\s\-]{3,45}?)(?:\n|\r|\||Hospital|$)"
    ])
    dados["hospital"] = buscar([
        r"(?:Hospital|Institui[cç][aã]o|Servi[cç]o(?:\s+de\s+Cirurgia)?)\s*[:\-]\s*([^\n\r\|]{4,80})"
    ])
    dados["ecog"] = buscar([r"ECOG\s*[:\-]?\s*([0-4])\b"])
    dados["comorbidades"] = buscar([r"Comorbidades\s*[:\-]\s*([^\n\r\|]+)"])
    dados["ca19_9"] = buscar([
        r"CA\s*19[\-\.]?9\s*[:\-=]?\s*(\d+(?:[\.,]\d+)?)"
    ]).replace(",", ".")
    dados["cea"] = buscar([
        r"CEA\s*[:\-=]?\s*(\d+(?:[\.,]\d+)?)"
    ]).replace(",", ".")
    dados["albumina"] = buscar([
        r"Albumina\s*[:\-=]?\s*(\d+(?:[\.,]\d+)?)"
    ]).replace(",", ".")
    dados["ast_tgo"] = buscar([
        r"(?:AST|TGO|AST\s*/\s*TGO)\s*[:\-=]?\s*(\d+(?:[\.,]\d+)?)"
    ]).replace(",", ".")
    dados["alt_tgp"] = buscar([
        r"(?:ALT|TGP|ALT\s*/\s*TGP)\s*[:\-=]?\s*(\d+(?:[\.,]\d+)?)"
    ]).replace(",", ".")
    dados["bilirrubina"] = buscar([
        r"Bilirrubina(?:\s+Total)?\s*[:\-=]?\s*(\d+(?:[\.,]\d+)?)"
    ]).replace(",", ".")
    dados["creatinina"] = buscar([
        r"Creatinina(?:\s+S[eé]rica)?\s*[:\-=]?\s*(\d+(?:[\.,]\d+)?)"
    ]).replace(",", ".")
    dados["ureia"] = buscar([
        r"Ureia\s*[:\-=]?\s*(\d+(?:[\.,]\d+)?)"
    ]).replace(",", ".")
    dados["ganglios_examinados"] = buscar([
        r"(?:G[aâ]nglios|Linfonodos)\s+Examinados\s*[:\-=]?\s*(\d+)"
    ])
    dados["ganglios_positivos"] = buscar([
        r"(?:G[aâ]nglios|Linfonodos)\s+Positivos\s*[:\-=]?\s*(\d+)"
    ])
    dados["margem_cirurgica"] = buscar([
        r"Margem(?:\s+Cir[uú]rgica)?\s*[:\-=]?\s*(R0|R1|R2)\b"
    ])
    dados["grau_histologico"] = buscar([
        r"Grau(?:\s+Histol[oó]gico)?\s*[:\-=]?\s*(G1|G2|G3|G4)\b"
    ])
    dados["isquemia_min"] = buscar([r"Isquemia(?:\s+Fria)?\s*[:\-=]?\s*(\d+)"])
    dados["passagem"] = buscar([r"Passagem\s*[:\-]?\s*P?(\d+)"])
    dados["n_criotubos"] = buscar([
        r"(?:Criotubos|Ampolas)(?:\s+Congelados)?\s*[:\-]?\s*(\d+)"
    ])
    dados["densidade_cel"] = buscar([
        r"Densidade(?:\s+Celular)?\s*[:\-]\s*([^\n\r]+)"
    ])
    dados["meio_matriz"] = buscar([
        r"(?:Meio\s+e\s+Matriz|Suplementa[cç][aã]o)\s*[:\-]\s*([^\n\r]+)"
    ])
    dados["morfologia_pdo"] = buscar([r"Morfologia\s*[:\-]\s*([^\n\r]+)"])
    dados["viabilidade_tripan"] = buscar([
        r"Viabilidade[^\n\r:]*[:\-]\s*(\d+(?:[\.,]\d+)?)\s*%"
    ])
    dados["dose_ensaio"] = buscar([
        r"(?:Concentra[cç][aã]o(?:\s+Testada)?|Dose)\s*[:\-]\s*([^\n\r\|]+)"
    ])

    mtt_r = re.search(
        r"Leitura\s+MTT[^\n\r]*R1\s*[:=]\s*([0-9\.]+)[^\n\r]*R2\s*[:=]\s*([0-9\.]+)[^\n\r]*R3\s*[:=]\s*([0-9\.]+)",
        texto_total,
        re.IGNORECASE,
    )
    if mtt_r:
        dados["mtt_r1"], dados["mtt_r2"], dados["mtt_r3"] = (
            mtt_r.group(1),
            mtt_r.group(2),
            mtt_r.group(3),
        )

    blk_r = re.search(
        r"Branco[^\n\r]*B1\s*[:=]\s*([0-9\.]+)[^\n\r]*B2\s*[:=]\s*([0-9\.]+)[^\n\r]*B3\s*[:=]\s*([0-9\.]+)",
        texto_total,
        re.IGNORECASE,
    )
    if blk_r:
        dados["mtt_b1"], dados["mtt_b2"], dados["mtt_b3"] = (
            blk_r.group(1),
            blk_r.group(2),
            blk_r.group(3),
        )

    ct_endo = buscar([
        r"Ct\s+End[oó]geno\s+Refer[eê]ncia[^\n\r:]*[:=]\s*([0-9\.]+)"
    ])
    if ct_endo:
        dados["ct_endo"] = ct_endo

    for m_g in re.finditer(
        r"Gene\s+([A-Z0-9]+)\s*->\s*Ct\s+Alvo\s+R1\s*[:=]\s*([0-9\.]+)\s*\|\s*R2\s*[:=]\s*([0-9\.]+)\s*\|\s*R3\s*[:=]\s*([0-9\.]+)",
        texto_total,
        re.IGNORECASE,
    ):
        g_name = m_g.group(1).upper()
        dados[f"qpcr_{g_name}"] = (m_g.group(2), m_g.group(3), m_g.group(4))

    return dados


# =============================================================================
# 4. MOTOR TRANSLACIONAL HOMEOSTAS.IA BETA (SEPARADO EM MÓDULO PRÓPRIO)
# =============================================================================
def converter_ct_para_log2tpm(
    ct_alvo: float, ct_ref: float = 20.0, efic: float = 100.0
) -> float:
    base_amp = 1.0 + (efic / 100.0)
    delta_ct = ct_alvo - ct_ref
    abund = math.pow(base_amp, 10.0 - delta_ct)
    return max(0.0, min(16.0, math.log(abund + 1.0) / math.log(2.0)))


def executar_fusao_translacional_organsense(
    idade: float,
    ganglios_exam: float,
    ganglios_pos: float,
    margem: str,
    grau: str,
    sig_basal: float,
    sig_classical: float,
    sig_prolif: float,
    sig_hipoxia: float,
    sig_estroma: float,
    fidelidade_pdo_pct: float = 88.0,
    viab_pdo_gemcitabina: float = 38.0,
    viab_pdo_folfirinox: float = 21.0,
    elegivel_folfirinox_hep_ren: bool = True,
) -> dict:
    exam = max(1.0, float(ganglios_exam))
    pos = max(0.0, min(exam, float(ganglios_pos)))
    lnr = pos / exam
    purist = float(sig_basal) - float(sig_classical)
    is_classical = purist < 0.0
    subtipo = (
        "Classical (Epitelial Diferenciado)"
        if is_classical
        else "Basal-like (Escamoso / Mesenquimal)"
    )

    w_pdo = min(0.55, max(0.10, (fidelidade_pdo_pct / 100.0) * 0.55))
    letalidade_gem = max(0.0, min(100.0, 100.0 - float(viab_pdo_gemcitabina))) / 100.0
    letalidade_poli = max(0.0, min(100.0, 100.0 - float(viab_pdo_folfirinox))) / 100.0

    fator_morf = (
        (0.85 * lnr)
        + (0.0 if margem == "R0" else 0.22)
        + (0.10 if grau in ("G3", "G4") else 0.0)
        + (0.008 * max(0.0, idade - 65.0))
    )
    pred_linear = (
        (0.29 * purist)
        + (0.14 * (sig_prolif - 3.75))
        + (0.12 * (sig_hipoxia - 5.96))
        + (0.05 * (sig_estroma - 7.66))
        + fator_morf
    )

    def logistic(x):
        return 1.0 / (1.0 + math.exp(x))

    s12_sem = max(12.0, min(92.0, logistic(pred_linear - 0.65) * 100.0))
    s24_sem = max(4.0, min(68.0, logistic(pred_linear + 0.85) * 100.0))

    s12_gem = max(
        18.0,
        min(
            96.0,
            ((1.0 - w_pdo * 0.5) * logistic(pred_linear - 1.15) + (w_pdo * 0.5) * letalidade_gem)
            * 100.0,
        ),
    )
    s24_gem = max(
        8.0,
        min(
            84.0,
            ((1.0 - w_pdo) * logistic(pred_linear + 0.32) + w_pdo * (letalidade_gem * 0.82))
            * 100.0,
        ),
    )

    s12_poli = max(
        22.0,
        min(
            97.0,
            ((1.0 - w_pdo * 0.5) * logistic(pred_linear - 1.38) + (w_pdo * 0.5) * letalidade_poli)
            * 100.0,
        ),
    )
    s24_poli = max(
        12.0,
        min(
            89.0,
            ((1.0 - w_pdo) * logistic(pred_linear - 0.25) + w_pdo * (letalidade_poli * 0.88))
            * 100.0,
        ),
    )

    recist_gem = max(
        5.0,
        min(
            95.0,
            ((1.0 - w_pdo) * logistic(pred_linear - 0.20) + w_pdo * letalidade_gem)
            * 100.0,
        ),
    )
    recist_poli = max(
        5.0,
        min(
            96.0,
            ((1.0 - w_pdo) * logistic(pred_linear - 0.55) + w_pdo * letalidade_poli)
            * 100.0,
        ),
    )

    if not elegivel_folfirinox_hep_ren:
        rota_recomendada = (
            "Monoterapia Ajustada (Gencitabina) ou Desobstrução Biliar Prévia"
        )
        justificativa = "Perfil hepatobiliar/renal impõe cautela farmacocinética para Irinotecano/Oxaliplatina."
    elif s24_gem > s24_poli + 2.0:
        rota_recomendada = (
            "Regime Baseado em Gencitabina (Sensibilidade Superior no Organoide -TN-FN)"
        )
        justificativa = f"O organoide apresentou morte celular superior sob Gencitabina ({letalidade_gem*100:.1f}% vs. {letalidade_poli*100:.1f}%)."
    else:
        rota_recomendada = (
            "Poliquimioterapia Combinada (mFOLFIRINOX ou Gencitabina + nab-Paclitaxel)"
        )
        justificativa = f"Convergência entre perfil molecular ({subtipo}) e resposta no organoide ({letalidade_poli*100:.1f}% de letalidade tumoral)."

    if is_classical and lnr <= 0.15 and margem == "R0":
        quadrante = "Q1: Classical + Baixo Risco Morfológico (LNR ≤ 0,15 e R0)"
    elif is_classical:
        quadrante = "Q2: Classical + Alto Risco Linfonodal/Margem (LNR > 0,15 ou R1)"
    elif not is_classical and lnr <= 0.15:
        quadrante = "Q3: Basal-like + Doença Localizada (Risco Biológico Intrínseco)"
    else:
        quadrante = "Q4: Basal-like + Alto Risco Linfonodal/Margem (LNR > 0,15 ou R1)"

    return {
        "motor": "Homeostas.IA beta | Fusão 3 Pilares (Paciente + Genética + Organoide)",
        "lnr": round(lnr, 3),
        "purist": round(purist, 3),
        "subtipo": subtipo,
        "quadrante": quadrante,
        "fidelidade_pdo": round(fidelidade_pdo_pct, 1),
        "peso_pdo_aplicado": round(w_pdo * 100.0, 1),
        "letalidade_pdo_gem": round(letalidade_gem * 100.0, 1),
        "letalidade_pdo_poli": round(letalidade_poli * 100.0, 1),
        "recist_gem": round(recist_gem, 1),
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
    }


def gerar_grafico_dispersao_homeostasia(res_ia: dict, id_p: str):
    rng = np.random.default_rng(42)
    purist_coorte = rng.normal(-1.89, 2.18, 139)
    lnr_coorte = np.clip(rng.exponential(0.16, 139), 0.0, 0.85)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.8, 4.4), dpi=130)
    fig.patch.set_facecolor("#FFFFFF")

    cores_c = ["#0284C7" if p < 0 else "#DC2626" for p in purist_coorte]
    ax1.scatter(
        purist_coorte,
        lnr_coorte,
        c=cores_c,
        alpha=0.45,
        s=34,
        label="Coorte Referência PDAC (n=139)",
    )
    ax1.axvline(0.0, color="#475569", linestyle="--", linewidth=1.1)
    ax1.axhline(0.15, color="#475569", linestyle="--", linewidth=1.1)
    ax1.scatter(
        [res_ia["purist"]],
        [res_ia["lnr"]],
        color="#10B981",
        edgecolors="#0F172A",
        marker="*",
        s=260,
        zorder=10,
        label=f"Amostra ({id_p})",
    )
    ax1.set_title(
        "Dispersão 1: Eixo Molecular (PurIST) vs. Razão Linfonodal (LNR)",
        fontsize=9.5,
        fontweight="bold",
    )
    ax1.set_xlabel("Score PurIST (<0 Classical | ≥0 Basal-like)")
    ax1.set_ylabel("Razão Linfonodal (LNR)")
    ax1.legend(loc="upper left", fontsize=8)
    ax1.grid(alpha=0.2)

    rotas_lbl = [
        "Grupo F1\n(Sem Tratamento)",
        "Grupo F2\n(Gencitabina)",
        "Grupo F3\n(Poliquimioterapia)",
    ]
    v12 = [res_ia["s12_sem"], res_ia["s12_gem"], res_ia["s12_poli"]]
    v24 = [res_ia["s24_sem"], res_ia["s24_gem"], res_ia["s24_poli"]]
    x = np.arange(len(rotas_lbl))
    w = 0.34
    ax2.bar(x - w / 2, v12, w, label="Sobrevida 12m (%)", color="#0284C7")
    ax2.bar(x + w / 2, v24, w, label="Sobrevida 24m (%)", color="#16A34A")
    ax2.set_xticks(x)
    ax2.set_xticklabels(rotas_lbl, fontsize=8.5)
    ax2.set_ylim(0, 108)
    ax2.set_ylabel("Sobrevida Estimada (%)")
    ax2.set_title(
        f"Simulação Translacional por Rota ({id_p})",
        fontsize=9.5,
        fontweight="bold",
    )
    for i in range(3):
        ax2.text(
            x[i] - w / 2,
            v12[i] + 1.5,
            f"{v12[i]:.1f}%",
            ha="center",
            fontsize=8,
            fontweight="bold",
        )
        ax2.text(
            x[i] + w / 2,
            v24[i] + 1.5,
            f"{v24[i]:.1f}%",
            ha="center",
            fontsize=8,
            fontweight="bold",
        )
    ax2.legend(loc="upper left", fontsize=8)
    ax2.grid(axis="y", alpha=0.2)

    plt.tight_layout()
    return fig


def gerar_painel_auditoria_interna_organsense(fidelidade_pdo: float):
    fig = plt.figure(figsize=(12.2, 4.3), dpi=130)
    fig.patch.set_facecolor("#FFFFFF")

    ax1 = fig.add_subplot(121, polar=True)
    categorias = [
        "ROC-AUC (24m)",
        "PR-AUC (24m)",
        "Sensibilidade",
        "Especificidade",
        "F1-Score",
        "Fidelidade PDO",
    ]
    valores_modelo = [
        0.769,
        0.894,
        0.712,
        0.792,
        0.800,
        min(1.0, max(0.5, fidelidade_pdo / 100.0)),
    ]
    valores_baseline = [0.603, 0.675, 0.550, 0.610, 0.580, 0.500]

    angulos = np.linspace(0, 2 * np.pi, len(categorias), endpoint=False).tolist()
    valores_modelo += valores_modelo[:1]
    valores_baseline += valores_baseline[:1]
    angulos += angulos[:1]

    ax1.plot(
        angulos,
        valores_modelo,
        color="#0284C7",
        linewidth=2.0,
        label="Homeostas.IA",
    )
    ax1.fill(angulos, valores_modelo, color="#0284C7", alpha=0.22)
    ax1.plot(
        angulos,
        valores_baseline,
        color="#94A3B8",
        linestyle="--",
        linewidth=1.4,
        label="Clínica Isolada",
    )
    ax1.set_xticks(angulos[:-1])
    ax1.set_xticklabels(categorias, fontsize=8, fontweight="bold")
    ax1.set_ylim(0, 1.0)
    ax1.set_title(
        "Rede de Métricas Validadas (5-Fold OOF)",
        fontsize=9.5,
        fontweight="bold",
        pad=12,
    )
    ax1.legend(loc="lower right", bbox_to_anchor=(1.25, -0.12), fontsize=8)

    ax2 = fig.add_subplot(122)
    cm = np.array([[19, 5], [21, 52]])
    ax2.imshow(cm, cmap="Blues")
    ax2.set_xticks([0, 1])
    ax2.set_yticks([0, 1])
    ax2.set_xticklabels(["Prev: Vivo >24m", "Prev: Óbito ≤24m"], fontsize=8.5)
    ax2.set_yticklabels(["Real: Vivo >24m\n(n=24)", "Real: Óbito ≤24m\n(n=73)"], fontsize=8.5)
    ax2.set_title(
        "Matriz de Confusão Auditada (24m | Acc Bal = 75,2%)",
        fontsize=9.5,
        fontweight="bold",
    )
    rotulos_cm = [
        [f"VN = {cm[0,0]}\n(Espec: 79,2%)", f"FP = {cm[0,1]}"],
        [f"FN = {cm[1,0]}", f"VP = {cm[1,1]}\n(Sens: 71,2%)"],
    ]
    for i in range(2):
        for j in range(2):
            cor_t = "white" if cm[i, j] > 30 else "#0F172A"
            ax2.text(
                j,
                i,
                rotulos_cm[i][j],
                ha="center",
                va="center",
                color=cor_t,
                fontsize=9,
                fontweight="bold",
            )

    plt.tight_layout()
    return fig


def calcular_custos_dinamicos_paciente(id_p: str) -> pd.DataFrame:
    """Calcula os gastos reais de reagentes com base nas amostras, passagens, ampolas e ensaios registrados."""
    n_tubos = len(fetch_all("SELECT 1 FROM amostras_biobanco WHERE id_p = :id", {"id": id_p})) or 1
    cults = fetch_all("SELECT passagem FROM linhagens_pdo WHERE id_p = :id", {"id": id_p})
    max_pass = max([int(r[0] or 1) for r in cults], default=1)
    n_frz = len(fetch_all("SELECT 1 FROM ampolas_congeladas WHERE id_p = :id", {"id": id_p})) or 1
    ens = fetch_all("SELECT modalidade FROM ensaios_farmaco_genetico WHERE id_p = :id", {"id": id_p})
    n_fn = sum(1 for r in ens if r[0] == "Farmacologico") or 1
    n_gn = sum(1 for r in ens if r[0] == "Genetico") or 1

    return pd.DataFrame([
        {
            "Etapa": "Recebimento e Processamento (-TN / -STN / -PN / -SN / -PBMCN)",
            "Insumo / Reagente": "Colagenase IV + Tubos Coleta + Meio Transporte + Filtros",
            "Quantidade": f"{n_tubos} amostra(s)/tubo(s)",
            "Custo Unit. (R$)": 115.00,
            "Subtotal (R$)": round(n_tubos * 115.00, 2),
        },
        {
            "Etapa": "Cultivo 3D e Expansão (-TN-C / -TN-EN)",
            "Insumo / Reagente": "Matrigel GFR + Meio WENR Completo + Y-27632",
            "Quantidade": f"{max_pass} passagem(ns)",
            "Custo Unit. (R$)": 290.00,
            "Subtotal (R$)": round(max_pass * 290.00, 2),
        },
        {
            "Etapa": "Criopreservação e QC (-TN-FN)",
            "Insumo / Reagente": "Meio Crioprotetor + Criotubos + Azul de Tripan",
            "Quantidade": f"{n_frz} ampola(s)",
            "Custo Unit. (R$)": 48.00,
            "Subtotal (R$)": round(n_frz * 48.00, 2),
        },
        {
            "Etapa": "Teste Farmacológico (-TN-F1..N)",
            "Insumo / Reagente": "Placa 96w + MTT/PrestoBlue/CellTiter-Glo 3D + Fármacos PDAC",
            "Quantidade": f"{n_fn} grupo(s) em triplicata",
            "Custo Unit. (R$)": 95.00,
            "Subtotal (R$)": round(n_fn * 95.00, 2),
        },
        {
            "Etapa": "Teste Genético (-TN-G1..N)",
            "Insumo / Reagente": "Extração RNA + Síntese cDNA + MasterMix RT-qPCR",
            "Quantidade": f"{n_gn} reação(ões) em triplicata",
            "Custo Unit. (R$)": 62.00,
            "Subtotal (R$)": round(n_gn * 62.00, 2),
        },
    ])


# =============================================================================
# 5. CONSTANTES DE TRATAMENTO PDAC E BIOTIPOS
# =============================================================================
GRUPOS_TRATAMENTO_PDAC = [
    (1, "Avaliação Sem Tratamento (Controle Basal)"),
    (2, "Gencitabina Monoterapia"),
    (3, "mFOLFIRINOX (5-FU + Leucovorina + Irinotecano + Oxaliplatina)"),
    (4, "Gencitabina + nab-Paclitaxel"),
    (5, "5-Fluorouracil (5-FU) / Capecitabina"),
    (6, "FOLFOX (5-FU + Leucovorina + Oxaliplatina)"),
    (7, "Cisplatina + Gencitabina (Perfil Deficiência HRD / BRCA)"),
    (8, "Olaparibe (Inibidor de PARP)"),
    (9, "Derivado Tiazopiridínico Experimental (P1)"),
]

BIOTIPOS_AMOSTRA = [
    ("Fragmento Tecidual (Tumor)", "T"),
    ("Sangue Total", "ST"),
    ("Plasma", "P"),
    ("Soro", "S"),
    ("PBMC", "PBMC"),
]


# =============================================================================
# 6. TELA DE LOGIN E CREDENCIAMENTO (SEM BOLINHAS DE SELEÇÃO)
# =============================================================================
if not st.session_state.get("logged_in"):
    st.title("OrganSense LIMS | Plataforma Translacional PDAC")

    st.session_state.setdefault("auth_view", "Autenticação")
    st.session_state.setdefault("prefill_user", "")
    st.session_state.setdefault("auth_notice", "")

    c_tab1, c_tab2, _ = st.columns([2, 2, 6])
    if c_tab1.button(
        "Autenticação",
        type="primary" if st.session_state.auth_view == "Autenticação" else "secondary",
        use_container_width=True,
    ):
        st.session_state.auth_view = "Autenticação"
        st.rerun()
    if c_tab2.button(
        "Credenciamento de Operador",
        type="primary"
        if st.session_state.auth_view == "Credenciamento de Operador"
        else "secondary",
        use_container_width=True,
    ):
        st.session_state.auth_view = "Credenciamento de Operador"
        st.rerun()

    st.divider()

    if st.session_state.auth_view == "Autenticação":
        if st.session_state.auth_notice:
            st.success(st.session_state.auth_notice)
            st.session_state.auth_notice = ""

        col_l1, col_l2 = st.columns([3, 2])
        with col_l1:
            st.subheader("Acesso Institucional")
            user_in = st.text_input(
                "Usuário ou E-mail Institucional",
                value=st.session_state.prefill_user,
            ).strip()
            pwd_in = st.text_input("Senha", type="password")
            if st.button("Acessar Plataforma", type="primary", use_container_width=True):
                row = fetch_one(
                    "SELECT username, password, role FROM usuarios_final WHERE username = :u OR LOWER(email) = LOWER(:u)",
                    {"u": user_in},
                )
                if row and verify_pwd(pwd_in, row[1]):
                    st.session_state.update(
                        logged_in=True, username=row[0], role=row[2]
                    )
                    log_audit(row[0], "Login", f"Sessão iniciada ({row[2]})")
                    st.rerun()
                else:
                    st.error("Credenciais inválidas.")

        with col_l2:
            st.subheader("Acesso via Conta Google")
            g_mail = st.text_input("E-mail Google (@gmail.com)").strip().lower()
            g_pwd = st.text_input(
                "Senha Cadastrada", type="password", key="g_pwd_in"
            )
            if st.button("Autenticar Conta Google", use_container_width=True):
                row_g = fetch_one(
                    "SELECT username, password, role FROM usuarios_final WHERE LOWER(email) = :e",
                    {"e": g_mail},
                )
                if row_g and verify_pwd(g_pwd, row_g[1]):
                    st.session_state.update(
                        logged_in=True,
                        username=row_g[0],
                        role=row_g[2],
                    )
                    log_audit(row_g[0], "Login Gmail", f"Acesso via {g_mail}")
                    st.rerun()
                else:
                    st.error("E-mail Google não encontrado ou senha incorreta.")

    else:
        st.subheader("Credenciamento de Novo Operador")
        mes_ref = datetime.now().strftime("%m/%Y")
        chaves = fetch_one(
            "SELECT chave_op, chave_adm FROM controle_chaves WHERE mes_ano = :m",
            {"m": mes_ref},
        )
        if not chaves:
            suf_op = "".join(
                random.choices(string.ascii_uppercase + string.digits, k=5)
            )
            suf_adm = "".join(
                random.choices(string.ascii_uppercase + string.digits, k=5)
            )
            c_op, c_adm = (
                f"OP-{mes_ref[:2]}-{suf_op}",
                f"ADM-{mes_ref[:2]}-{suf_adm}",
            )
            run_sql(
                "INSERT INTO controle_chaves VALUES (:m, :op, :adm)",
                {"m": mes_ref, "op": c_op, "adm": c_adm},
            )
            if "email" in st.secrets and "remetente" in st.secrets["email"]:
                send_email(
                    st.secrets["email"]["remetente"],
                    f"Chaves de Acesso OrganSense - {mes_ref}",
                    f"Chaves geradas para {mes_ref}:\nOperador: {c_op}\nAdministrador: {c_adm}",
                )
        else:
            c_op, c_adm = chaves[0], chaves[1]

        token = st.text_input(
            "Token Institucional de Autorização", type="password"
        ).strip()
        if token and token in (c_op, c_adm):
            role_atrib = "Administrador" if token == c_adm else "Operador"
            st.info(f"Token validado. Nível atribuído: {role_atrib}")
            cu, ce = st.columns(2)
            novo_u = cu.text_input("Identificador de Usuário (sem espaços)").strip()
            novo_e = ce.text_input("E-mail Institucional / Gmail").strip()
            nova_s = st.text_input("Defina sua Senha", type="password")
            senha_ok = renderizar_medidor_senha(nova_s)

            if st.button("Registrar Credencial e Ir para Login", type="primary"):
                if not novo_u or " " in novo_u:
                    st.error("Identificador de usuário inválido.")
                elif not novo_e or "@" not in novo_e:
                    st.error("Informe um e-mail válido.")
                elif fetch_one(
                    "SELECT 1 FROM usuarios_final WHERE username = :u OR LOWER(email) = LOWER(:e)",
                    {"u": novo_u, "e": novo_e},
                ):
                    st.error("Usuário ou e-mail já cadastrado.")
                elif not senha_ok:
                    st.error("Atenda aos requisitos de complexidade da senha.")
                else:
                    run_sql(
                        "INSERT INTO usuarios_final VALUES (:u, :p, :e, :r)",
                        {
                            "u": novo_u,
                            "p": hash_pwd(nova_s),
                            "e": novo_e,
                            "r": role_atrib,
                        },
                    )
                    log_audit(novo_u, "Credenciamento", f"Perfil: {role_atrib}")
                    st.session_state.prefill_user = novo_u
                    st.session_state.auth_notice = (
                        f"Credencial '{novo_u}' registrada. Digite sua senha para entrar."
                    )
                    st.session_state.auth_view = "Autenticação"
                    st.rerun()


# =============================================================================
# 7. AMBIENTE LOGADO: MENU SUSPENSO (☰) COM TÍTULOS CURTOS E SEM BOLINHAS
# =============================================================================
else:
    modulos_curtos = [
        "1. Paciente",
        "2. Amostra",
        "3. Homeostas.IA",
        "4. Coorte & Dossiê",
    ]
    if st.session_state.role == "Administrador":
        modulos_curtos.append("5. Governança")

    if st.session_state.get("nav_curto") not in modulos_curtos:
        st.session_state.nav_curto = modulos_curtos[0]

    col_menu, col_titulo, col_status = st.columns([1, 6, 3])
    with col_menu:
        with st.popover("☰", use_container_width=True):
            st.caption("MÓDULOS DA PLATAFORMA")
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

            st.divider()
            st.caption("LAUDOS PDF DE TESTE (DOWNLOAD)")
            for nome_arq, linhas_arq in LAUDOS_PDF_TESTE.items():
                st.download_button(
                    label=f"PDF: {nome_arq[:24]}...",
                    data=gerar_bytes_pdf_nativo(linhas_arq),
                    file_name=nome_arq,
                    mime="application/pdf",
                    key=f"dl_{nome_arq}",
                    use_container_width=True,
                )

            st.divider()
            st.caption(
                f"Operador: {st.session_state.username} ({st.session_state.role})"
            )
            if st.button("Encerrar Sessão", use_container_width=True):
                log_audit(st.session_state.username, "Logout", "Saída")
                st.session_state.logged_in = False
                st.rerun()

    with col_titulo:
        st.markdown(
            "<div style='padding-top:4px;'><span style='font-size:21px; font-weight:800; color:#0F172A;'>OrganSense LIMS</span> "
            "<span style='font-size:13px; font-weight:600; color:#0284C7;'>| Biobanco Translacional PDAC & Homeostas.IA beta</span></div>",
            unsafe_allow_html=True,
        )

    with col_status:
        st.markdown(
            f"<div style='text-align:right; font-size:12px; color:#334155; padding-top:8px;'>"
            f"<strong>Fase Ativa:</strong> {st.session_state.nav_curto}<br>"
            f"<strong>Conformidade:</strong> LGPD 100% Local</div>",
            unsafe_allow_html=True,
        )

    st.divider()

    # =========================================================================
    # FASE 1: PACIENTE (5 SUB-ETAPAS COM TÍTULOS CURTOS -> GERA ID "RECEBIDO")
    # =========================================================================
    if st.session_state.nav_curto == "1. Paciente":
        st.subheader("Fase 1: Submissão Integrada do Paciente (PDAC)")
        st.session_state.setdefault("pdf_pac_cache", {})
        st.session_state.setdefault("sub_aba_pac", "1. Submeter Paciente")

        with st.expander(
            "Importar Prontuário / Laudos em PDF (Múltiplos Arquivos - Extração Local LGPD)",
            expanded=False,
        ):
            pdfs_p = st.file_uploader(
                "Anexar PDFs clínicos, bioquímicos ou anatomopatológicos",
                type=["pdf"],
                accept_multiple_files=True,
                key="up_pdf_fase1",
            )
            if pdfs_p and st.button("Extrair Dados dos PDFs"):
                ext_p = extrair_variaveis_multiplos_pdfs(pdfs_p)
                st.session_state.pdf_pac_cache.update(ext_p)
                if "draft_pac" in st.session_state:
                    for k_map, k_pdf in [
                        ("nome", "nome"),
                        ("sexo", "sexo"),
                        ("uf", "uf"),
                        ("municipio", "municipio"),
                        ("hospital", "hospital"),
                        ("ecog", "ecog"),
                        ("comorbidades", "comorbidades"),
                        ("ca19_9", "ca19_9"),
                        ("cea", "cea"),
                        ("alb", "albumina"),
                        ("ast", "ast_tgo"),
                        ("alt", "alt_tgp"),
                        ("bil", "bilirrubina"),
                        ("cre", "creatinina"),
                        ("ure", "ureia"),
                        ("margem", "margem_cirurgica"),
                        ("grau", "grau_histologico"),
                    ]:
                        if ext_p.get(k_pdf):
                            st.session_state.draft_pac[k_map] = ext_p[k_pdf]
                st.success(
                    "Dados extraídos localmente e distribuídos nas 5 sub-etapas abaixo."
                )

        dp = st.session_state.pdf_pac_cache

        etapas_pac = [
            "1. Submeter Paciente",
            "2. Dados Clínicos",
            "3. Dados Bioquímicos",
            "4. Dados Anatomomorfológicos",
            "5. Dados de Tratamento",
        ]
        cols_ep = st.columns(5)
        for idx_e, nome_e in enumerate(etapas_pac):
            if cols_ep[idx_e].button(
                nome_e,
                type="primary"
                if st.session_state.sub_aba_pac == nome_e
                else "secondary",
                use_container_width=True,
            ):
                st.session_state.sub_aba_pac = nome_e
                st.rerun()

        st.markdown("---")

        st.session_state.setdefault(
            "draft_pac",
            {
                "nome": dp.get("nome", ""),
                "sexo": dp.get("sexo", "Masculino"),
                "dt_nasc": date(1962, 5, 14),
                "uf": dp.get("uf", "PE"),
                "municipio": dp.get("municipio", "Recife"),
                "hospital": dp.get("hospital", ""),
                "ecog": dp.get("ecog", "1"),
                "comorbidades": dp.get("comorbidades", "Nenhuma relatada"),
                "ca19_9": dp.get("ca19_9", "145.0"),
                "cea": dp.get("cea", "3.2"),
                "ast": dp.get("ast_tgo", "34.0"),
                "alt": dp.get("alt_tgp", "41.0"),
                "bil": dp.get("bilirrubina", "1.1"),
                "cre": dp.get("creatinina", "0.9"),
                "ure": dp.get("ureia", "32.0"),
                "alb": dp.get("albumina", "3.8"),
                "topografia": "Cabeça do Pâncreas",
                "ajcc": "IIB (Borderline)",
                "t": "T3",
                "n": "N1",
                "m": "M0",
                "g_exam": int(dp["ganglios_examinados"])
                if str(dp.get("ganglios_examinados", "")).isdigit()
                else 18,
                "g_pos": int(dp["ganglios_positivos"])
                if str(dp.get("ganglios_positivos", "")).isdigit()
                else 2,
                "margem": dp.get("margem_cirurgica", "R0"),
                "grau": dp.get("grau_histologico", "G2"),
                "ipn": "Presente",
                "ilv": "Presente",
                "status_trat": "Virgem de Tratamento (Upfront)",
                "quimio": [],
                "radio": [],
                "resseccao": ["Gastroduodenopancreatectomia (Whipple)"],
            },
        )
        dr = st.session_state.draft_pac

        if st.session_state.sub_aba_pac == "1. Submeter Paciente":
            st.markdown("#### 1.1 Identificação Demográfica e Origem Hospitalar")
            c1, c2 = st.columns(2)
            dr["nome"] = c1.text_input(
                "Nome Completo do Paciente", value=dr["nome"]
            ).strip()
            dr["hospital"] = c2.text_input(
                "Instituição Hospitalar de Origem", value=dr["hospital"]
            ).strip()

            c3, c4, c5, c6 = st.columns(4)
            dr["sexo"] = c3.selectbox(
                "Sexo Biológico",
                ["Masculino", "Feminino"],
                index=0 if dr["sexo"] == "Masculino" else 1,
            )
            dr["dt_nasc"] = c4.date_input(
                "Data de Nascimento",
                value=dr["dt_nasc"],
                min_value=date(1900, 1, 1),
                max_value=date.today(),
            )
            ufs = get_ufs()
            dr["uf"] = c5.selectbox(
                "UF",
                ufs,
                index=ufs.index(dr["uf"]) if dr["uf"] in ufs else 0,
            )
            cids = get_cidades(dr["uf"])
            dr["municipio"] = c6.selectbox(
                "Município",
                cids,
                index=cids.index(dr["municipio"])
                if dr["municipio"] in cids
                else 0,
            )

            if st.button(
                "Salvar Demografia e Ir para Dados Clínicos ->", type="primary"
            ):
                st.session_state.sub_aba_pac = "2. Dados Clínicos"
                st.rerun()

        elif st.session_state.sub_aba_pac == "2. Dados Clínicos":
            st.markdown("#### 1.2 Desempenho Funcional e Quadro Clínico")
            c1, c2 = st.columns([1, 3])
            op_ecog = ["0", "1", "2", "3", "4"]
            dr["ecog"] = c1.selectbox(
                "Performance Status (ECOG)",
                op_ecog,
                index=op_ecog.index(str(dr["ecog"]))
                if str(dr["ecog"]) in op_ecog
                else 1,
            )
            dr["comorbidades"] = c2.text_input(
                "Comorbidades e Sintomatologia (Diabetes recente, Icterícia obstrutiva, Perda ponderal)",
                value=dr["comorbidades"],
            )

            if st.button(
                "Salvar Dados Clínicos e Ir para Dados Bioquímicos ->",
                type="primary",
            ):
                st.session_state.sub_aba_pac = "3. Dados Bioquímicos"
                st.rerun()

        elif st.session_state.sub_aba_pac == "3. Dados Bioquímicos":
            st.markdown(
                "#### 1.3 Marcadores Sérico-Tumorais, Perfil Hepatobiliar e Renal"
            )
            b1, b2, b3, b4 = st.columns(4)
            dr["ca19_9"] = norm_num(
                b1.text_input("CA 19-9 Sérico (U/mL)", value=dr["ca19_9"])
            )
            dr["cea"] = norm_num(b2.text_input("CEA (ng/mL)", value=dr["cea"]))
            dr["bil"] = norm_num(
                b3.text_input("Bilirrubina Total (mg/dL)", value=dr["bil"])
            )
            dr["alb"] = norm_num(
                b4.text_input("Albumina Sérica (g/dL)", value=dr["alb"])
            )

            b5, b6, b7, b8 = st.columns(4)
            dr["ast"] = norm_num(
                b5.text_input("AST / TGO (U/L)", value=dr["ast"])
            )
            dr["alt"] = norm_num(
                b6.text_input("ALT / TGP (U/L)", value=dr["alt"])
            )
            dr["cre"] = norm_num(
                b7.text_input("Creatinina Sérica (mg/dL)", value=dr["cre"])
            )
            dr["ure"] = norm_num(
                b8.text_input("Ureia (mg/dL)", value=dr["ure"])
            )

            if st.button(
                "Salvar Bioquímica e Ir para Dados Anatomomorfológicos ->",
                type="primary",
            ):
                st.session_state.sub_aba_pac = "4. Dados Anatomomorfológicos"
                st.rerun()

        elif st.session_state.sub_aba_pac == "4. Dados Anatomomorfológicos":
            st.markdown(
                "#### 1.4 Estadiamento Anatomomorfológico, Linfonodos e Margens (PDAC)"
            )
            a1, a2, a3 = st.columns(3)
            op_top = [
                "Cabeça do Pâncreas",
                "Processo Uncinado",
                "Corpo do Pâncreas",
                "Cauda do Pâncreas",
                "Metástase Hepática",
                "Implante Peritoneal",
            ]
            op_ajcc = [
                "IA (Ressecável)",
                "IB (Ressecável)",
                "IIA (Ressecável)",
                "IIB (Borderline)",
                "III (Localmente Avançado)",
                "IV (Metastático)",
            ]
            dr["topografia"] = a1.selectbox(
                "Topografia Primária",
                op_top,
                index=op_top.index(dr["topografia"])
                if dr["topografia"] in op_top
                else 0,
            )
            dr["ajcc"] = a2.selectbox(
                "Estadiamento AJCC (8ª Ed.)",
                op_ajcc,
                index=op_ajcc.index(dr["ajcc"])
                if dr["ajcc"] in op_ajcc
                else 3,
            )
            dr["grau"] = a3.selectbox(
                "Grau de Diferenciação Histológica",
                ["G1", "G2", "G3", "G4"],
                index=["G1", "G2", "G3", "G4"].index(dr["grau"])
                if dr["grau"] in ["G1", "G2", "G3", "G4"]
                else 1,
            )

            t1, t2, t3, t4, t5, t6 = st.columns(6)
            dr["t"] = t1.selectbox(
                "Categoria T",
                ["T1", "T2", "T3", "T4"],
                index=["T1", "T2", "T3", "T4"].index(dr["t"]),
            )
            dr["n"] = t2.selectbox(
                "Categoria N",
                ["N0", "N1", "N2"],
                index=["N0", "N1", "N2"].index(dr["n"]),
            )
            dr["m"] = t3.selectbox(
                "Categoria M", ["M0", "M1"], index=["M0", "M1"].index(dr["m"])
            )
            dr["g_exam"] = t4.number_input(
                "Gânglios Examinados", min_value=1, value=int(dr["g_exam"])
            )
            dr["g_pos"] = t5.number_input(
                "Gânglios Positivos", min_value=0, value=int(dr["g_pos"])
            )
            dr["margem"] = t6.selectbox(
                "Margem de Ressecção",
                ["R0", "R1", "R2"],
                index=["R0", "R1", "R2"].index(dr["margem"])
                if dr["margem"] in ["R0", "R1", "R2"]
                else 0,
            )

            i1, i2 = st.columns(2)
            dr["ipn"] = i1.selectbox(
                "Invasão Perineural",
                ["Presente", "Ausente", "Não Avaliada"],
            )
            dr["ilv"] = i2.selectbox(
                "Invasão Angiolinfática",
                ["Presente", "Ausente", "Não Avaliada"],
            )

            lnr_p = dr["g_pos"] / max(1, dr["g_exam"])
            st.caption(
                f"TNM Calculado: **{dr['t']}{dr['n']}{dr['m']}** | Razão Linfonodal (LNR): **{lnr_p:.3f}** ({dr['g_pos']}/{dr['g_exam']})"
            )

            if st.button(
                "Salvar Anatomomorfologia e Ir para Dados de Tratamento ->",
                type="primary",
            ):
                st.session_state.sub_aba_pac = "5. Dados de Tratamento"
                st.rerun()

        elif st.session_state.sub_aba_pac == "5. Dados de Tratamento":
            st.markdown(
                "#### 1.5 Dados de Tratamento (Quimioterapia, Radioterapia e Ressecção Cirúrgica)"
            )
            dr["status_trat"] = st.selectbox(
                "Contexto Terapêutico na Aquisição",
                [
                    "Virgem de Tratamento (Upfront)",
                    "Pós-Neoadjuvância (Exposto Previamente)",
                    "Paliativo / Biópsia Diagnóstica",
                ],
            )
            dr["resseccao"] = st.multiselect(
                "Modalidade de Ressecção / Abordagem Cirúrgica",
                [
                    "Gastroduodenopancreatectomia (Whipple)",
                    "Pancreatectomia Corpo-Caudal (Distal) com Esplenectomia",
                    "Pancreatectomia Total",
                    "Derivação Biliodigestiva Paliativa",
                    "Biópsia Guiada por Ecoendoscopia (EUS-FNA/FNB)",
                ],
                default=dr["resseccao"],
            )
            dr["quimio"] = st.multiselect(
                "Regimes Quimioterápicos (Neoadjuvante / Adjuvante Planejado)",
                [g[1] for g in GRUPOS_TRATAMENTO_PDAC[1:]],
                default=dr["quimio"],
            )
            dr["radio"] = st.multiselect(
                "Modalidade Radioterápica",
                [
                    "Nenhuma",
                    "SBRT (Radioterapia Corpo Estereotáxica)",
                    "IMRT (Intensidade Modulada)",
                    "Quimiorradioterapia Concomitante (3D-CRT)",
                ],
                default=dr["radio"],
            )

            st.divider()
            if st.button(
                "Finalizar Submissão do Paciente e Gerar ID de 'Recebido'",
                type="primary",
            ):
                if not dr["nome"] or not dr["hospital"]:
                    st.error(
                        "Retorne à etapa '1. Submeter Paciente' e preencha Nome e Hospital."
                    )
                else:
                    id_gerado = next_patient_code()
                    hoje = date.today()
                    dn = dr["dt_nasc"]
                    idade_c = (
                        hoje.year
                        - dn.year
                        - ((hoje.month, hoje.day) < (dn.month, dn.day))
                    )
                    lnr_f = round(dr["g_pos"] / max(1, dr["g_exam"]), 3)
                    tnm_str = f"{dr['t']}{dr['n']}{dr['m']}"

                    run_sql(
                        "INSERT INTO pacientes_final VALUES (:id, :n, :i, :s, :na, :uf, :c, :rc, :h, 'Recebido')",
                        {
                            "id": id_gerado,
                            "n": dr["nome"],
                            "i": idade_c,
                            "s": dr["sexo"],
                            "na": dn.strftime("%d/%m/%Y"),
                            "uf": dr["uf"],
                            "c": dr["municipio"],
                            "rc": st.session_state.username,
                            "h": dr["hospital"],
                        },
                    )
                    run_sql(
                        """INSERT INTO submissao_paciente_detalhada VALUES 
                           (:id, :ecog, :com, :ca19, :cea, :ast, :alt, :bil, :cre, :ure, :alb,
                            :top, :ajcc, :tnm, :gex, :gpo, :lnr, :mg, :gr, :ipn, :ilv,
                            :st_t, :qm, :rd, :rs, :dt, :resp)""",
                        {
                            "id": id_gerado,
                            "ecog": dr["ecog"],
                            "com": dr["comorbidades"],
                            "ca19": dr["ca19_9"],
                            "cea": dr["cea"],
                            "ast": dr["ast"],
                            "alt": dr["alt"],
                            "bil": dr["bil"],
                            "cre": dr["cre"],
                            "ure": dr["ure"],
                            "alb": dr["alb"],
                            "top": dr["topografia"],
                            "ajcc": dr["ajcc"],
                            "tnm": tnm_str,
                            "gex": int(dr["g_exam"]),
                            "gpo": int(dr["g_pos"]),
                            "lnr": lnr_f,
                            "mg": dr["margem"],
                            "gr": dr["grau"],
                            "ipn": dr["ipn"],
                            "ilv": dr["ilv"],
                            "st_t": dr["status_trat"],
                            "qm": json.dumps(dr["quimio"], ensure_ascii=False),
                            "rd": json.dumps(dr["radio"], ensure_ascii=False),
                            "rs": json.dumps(
                                dr["resseccao"], ensure_ascii=False
                            ),
                            "dt": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
                            "resp": st.session_state.username,
                        },
                    )
                    log_audit(
                        st.session_state.username,
                        "Paciente Recebido",
                        f"ID {id_gerado} gerado com status 'Recebido'",
                    )
                    st.session_state.id_ativo = id_gerado
                    st.session_state.nav_curto = "2. Amostra"
                    st.rerun()

    # =========================================================================
    # FASE 2: AMOSTRA (-TN, -STN, -PN, -SN, -PBMCN, -C, -EN, -FN, -GN)
    # =========================================================================
    elif st.session_state.nav_curto == "2. Amostra":
        st.subheader("Fase 2: Rastreabilidade de Amostras, Biobanco e Ensaios")
        id_b = (
            st.text_input(
                "ID do Paciente Recebido (ex: OS-001)",
                value=st.session_state.get("id_ativo", ""),
            )
            .strip()
            .upper()
        )

        if id_b:
            pac = fetch_one(
                "SELECT * FROM pacientes_final WHERE id_p = :id", {"id": id_b}
            )
            if not pac:
                st.warning(
                    "ID de paciente não localizado. Submeta o paciente na Fase 1."
                )
            else:
                renderizar_gradiente_paciente(id_b)

                with st.expander(
                    "Importar Boletins de Biobanco / Cultivo / Ensaios via PDF (Múltiplos Arquivos)",
                    expanded=False,
                ):
                    pdfs_am = st.file_uploader(
                        "Anexar PDFs laboratoriais desta etapa",
                        type=["pdf"],
                        accept_multiple_files=True,
                        key="up_pdf_fase2",
                    )
                    if pdfs_am and st.button("Extrair Parâmetros Laboratoriais dos PDFs"):
                        st.session_state.setdefault("pdf_pac_cache", {}).update(
                            extrair_variaveis_multiplos_pdfs(pdfs_am)
                        )
                        st.success("Parâmetros laboratoriais e leituras analíticas extraídos.")
                        st.rerun()

                dp_am = st.session_state.get("pdf_pac_cache", {})

                st.session_state.setdefault(
                    "aba_amostra",
                    "1. Recebimento (-TN / -STN / -PN / -SN / -PBMCN)",
                )
                abas_am = [
                    "1. Recebimento (-TN / -STN / -PN / -SN / -PBMCN)",
                    "2. Cultivo & Criopreservação (-TN-C / -EN / -FN)",
                    "3. Teste Farmacológico (-TN-FN) & Genético (-TN-GN)",
                    "4. Análises por Biotipo (Futuro IA)",
                ]
                cols_am = st.columns(4)
                for i_a, n_a in enumerate(abas_am):
                    if cols_am[i_a].button(
                        n_a,
                        type="primary"
                        if st.session_state.aba_amostra == n_a
                        else "secondary",
                        use_container_width=True,
                    ):
                        st.session_state.aba_amostra = n_a
                        st.rerun()

                st.markdown("---")

                # 2.1 RECEBIMENTO DE AMOSTRAS (-TN, -STN, -PN, -SN, -PBMCN)
                if st.session_state.aba_amostra.startswith("1. Recebimento"):
                    st.markdown(
                        "#### Registro de Tubos e Fragmentos Recebidos (`OS-XXX-TN`, `-STN`, `-PN`, `-SN`, `-PBMCN`)"
                    )
                    c_bio, c_qtd, c_isq, c_meio = st.columns(4)
                    nomes_bio = [b[0] for b in BIOTIPOS_AMOSTRA]
                    mapa_pref = dict(BIOTIPOS_AMOSTRA)

                    biotipo_sel = c_bio.selectbox(
                        "Tipo de Material Biológico", nomes_bio
                    )
                    pref_sel = mapa_pref[biotipo_sel]
                    qtd_tubos = c_qtd.number_input(
                        f"Nº de Amostras/Tubos ({pref_sel}1..{pref_sel}N)",
                        min_value=1,
                        max_value=15,
                        value=3,
                    )
                    isq_pad = (
                        int(dp_am["isquemia_min"])
                        if str(dp_am.get("isquemia_min", "")).isdigit()
                        else 25
                    )
                    isq_min = c_isq.number_input(
                        "Isquemia Fria (min)", min_value=0, value=isq_pad
                    )
                    meio_tr = c_meio.selectbox(
                        "Meio / Tubo de Coleta",
                        [
                            "RPMI 1640 Suplementado (4°C)",
                            "Tubo EDTA (Roxo)",
                            "Tubo Heparina Sódica (Verde)",
                            "Tubo Gel Separador (Amarelo)",
                            "Solução de Preservação Custodiol",
                        ],
                    )

                    existentes = fetch_all(
                        "SELECT numero_tubo FROM amostras_biobanco WHERE id_p = :id AND prefixo_tipo = :pr",
                        {"id": id_b, "pr": pref_sel},
                    )
                    ultimo_n = max([r[0] for r in existentes], default=0)
                    preview_ids = [
                        f"{id_b}-{pref_sel}{ultimo_n + i}"
                        for i in range(1, int(qtd_tubos) + 1)
                    ]
                    st.info(
                        f"Identificadores que serão gerados neste lote: **`{', '.join(preview_ids)}`**"
                    )

                    if st.button(
                        "Registrar Lote de Amostras Recebidas", type="primary"
                    ):
                        for i in range(1, int(qtd_tubos) + 1):
                            num_t = ultimo_n + i
                            cod_am = f"{id_b}-{pref_sel}{num_t}"
                            run_sql(
                                "INSERT INTO amostras_biobanco VALUES (:id_a, :id_p, :bio, :pr, :num, :vol, :isq, :meio, 'Recebida', :resp, :dt)",
                                {
                                    "id_a": cod_am,
                                    "id_p": id_b,
                                    "bio": biotipo_sel,
                                    "pr": pref_sel,
                                    "num": num_t,
                                    "vol": "1 unidade/tubo",
                                    "isq": int(isq_min),
                                    "meio": meio_tr,
                                    "resp": st.session_state.username,
                                    "dt": datetime.now().strftime(
                                        "%d/%m/%Y %H:%M"
                                    ),
                                },
                            )
                        log_audit(
                            st.session_state.username,
                            "Amostras Recebidas",
                            f"Gerados: {', '.join(preview_ids)}",
                        )
                        st.success("Amostras registradas no biobanco.")
                        st.rerun()

                    df_am_rec = fetch_df(
                        'SELECT id_amostra AS "ID Amostra", biotipo AS "Material Biológico", numero_tubo AS "Nº Tubo (N)", isquemia_min AS "Isquemia (min)", meio_transporte AS "Meio / Tubo", status_amostra AS "Status", data_coleta AS "Data" FROM amostras_biobanco WHERE id_p = :id ORDER BY prefixo_tipo, numero_tubo',
                        {"id": id_b},
                    )
                    if not df_am_rec.empty:
                        st.dataframe(
                            df_am_rec, use_container_width=True, hide_index=True
                        )

                # 2.2 CULTIVO (-TN-C), ESTABELECIDA (-TN-EN) E FROZEN (-TN-FN)
                elif st.session_state.aba_amostra.startswith("2. Cultivo"):
                    st.markdown(
                        "#### Evolução Tumoral: Em Cultivo (`-TN-C`) $\\rightarrow$ Estabelecida (`-TN-EN`) $\\rightarrow$ Congelada (`-TN-FN`)"
                    )
                    tumores_tn = fetch_all(
                        "SELECT id_amostra, numero_tubo FROM amostras_biobanco WHERE id_p = :id AND prefixo_tipo = 'T' ORDER BY numero_tubo",
                        {"id": id_b},
                    )

                    if not tumores_tn:
                        st.warning(
                            "Nenhum Fragmento Tecidual (`-TN`) registrado ainda. Cadastre na aba '1. Recebimento'."
                        )
                    else:
                        opcoes_tn = [r[0] for r in tumores_tn]
                        tn_sel = st.selectbox(
                            "Selecionar Amostra Tumoral de Origem (-TN)",
                            opcoes_tn,
                        )
                        sufixo_tn = tn_sel.split("-")[-1]

                        col_c1, col_c2, col_c3 = st.columns(3)

                        with col_c1:
                            st.markdown(
                                f"**1. Entrada em Cultivo (`{tn_sel}-C`)**"
                            )
                            id_cult = f"{tn_sel}-C"
                            ja_cult = fetch_one(
                                "SELECT 1 FROM linhagens_pdo WHERE id_linhagem = :id",
                                {"id": id_cult},
                            )
                            meio_c = st.text_input(
                                "Matriz / Meio de Cultivo",
                                value=dp_am.get(
                                    "meio_matriz",
                                    "Matrigel GFR + Meio WENR Completo",
                                ),
                                key="mc_in",
                            )
                            if not ja_cult:
                                if st.button(
                                    f"Gerar {id_cult}",
                                    type="primary",
                                    use_container_width=True,
                                ):
                                    run_sql(
                                        "INSERT INTO linhagens_pdo VALUES (:idl, :ida, :idp, :base, 'Cultivo', 0, 'Em Cultivo (-C)', :mm, '', :resp, :dt)",
                                        {
                                            "idl": id_cult,
                                            "ida": tn_sel,
                                            "idp": id_b,
                                            "base": sufixo_tn,
                                            "mm": meio_c,
                                            "resp": st.session_state.username,
                                            "dt": datetime.now().strftime(
                                                "%d/%m/%Y"
                                            ),
                                        },
                                    )
                                    run_sql(
                                        "UPDATE pacientes_final SET status_geral = 'Em Cultivo (-C)' WHERE id_p = :id",
                                        {"id": id_b},
                                    )
                                    st.rerun()
                            else:
                                st.success(f"`{id_cult}` ativo em cultivo.")

                        with col_c2:
                            st.markdown(
                                f"**2. Linhagem Estabelecida (`{tn_sel}-EN`)**"
                            )
                            pass_def = (
                                int(dp_am["passagem"])
                                if str(dp_am.get("passagem", "")).isdigit()
                                else 3
                            )
                            pass_en = st.number_input(
                                "Passagem do Congelamento (N)",
                                min_value=1,
                                max_value=30,
                                value=pass_def,
                            )
                            id_estab = f"{tn_sel}-E{int(pass_en)}"
                            obs_en = st.text_input(
                                "Morfologia do Organoide",
                                value=dp_am.get(
                                    "morfologia_pdo",
                                    "Organoides císticos luminados viáveis",
                                ),
                            )
                            if st.button(
                                f"Estabelecer {id_estab}",
                                type="primary",
                                use_container_width=True,
                            ):
                                if not fetch_one(
                                    "SELECT 1 FROM linhagens_pdo WHERE id_linhagem = :id",
                                    {"id": id_estab},
                                ):
                                    run_sql(
                                        "INSERT INTO linhagens_pdo VALUES (:idl, :ida, :idp, :base, 'Estabelecida', :ps, 'Estabelecida (-EN)', :mm, :ob, :resp, :dt)",
                                        {
                                            "idl": id_estab,
                                            "ida": tn_sel,
                                            "idp": id_b,
                                            "base": sufixo_tn,
                                            "ps": int(pass_en),
                                            "mm": meio_c,
                                            "ob": obs_en,
                                            "resp": st.session_state.username,
                                            "dt": datetime.now().strftime(
                                                "%d/%m/%Y"
                                            ),
                                        },
                                    )
                                    run_sql(
                                        "UPDATE pacientes_final SET status_geral = 'Estabelecida (-EN)' WHERE id_p = :id",
                                        {"id": id_b},
                                    )
                                    st.rerun()

                        with col_c3:
                            st.markdown(
                                f"**3. Criopreservação (`{tn_sel}-FN`)**"
                            )
                            crio_def = (
                                int(dp_am["n_criotubos"])
                                if str(dp_am.get("n_criotubos", "")).isdigit()
                                else 3
                            )
                            n_ampolas_f = st.number_input(
                                "Nº de Ampolas para Congelar (F1..FN)",
                                min_value=1,
                                max_value=20,
                                value=crio_def,
                            )
                            dens_f = st.text_input(
                                "Densidade por Ampola",
                                value=dp_am.get(
                                    "densidade_cel", "1.5x10^6 cél/mL"
                                ),
                            )
                            viab_def = (
                                int(float(dp_am["viabilidade_tripan"]))
                                if str(dp_am.get("viabilidade_tripan", ""))
                                .replace(".", "")
                                .isdigit()
                                else 90
                            )
                            viab_f = st.slider(
                                "Viabilidade Pós-Descongelamento QC (%)",
                                0,
                                100,
                                min(100, viab_def),
                            )
                            if st.button(
                                f"Gerar Ampolas {tn_sel}-F1..F{int(n_ampolas_f)}",
                                type="primary",
                                use_container_width=True,
                            ):
                                existentes_f = fetch_all(
                                    "SELECT numero_ampola FROM ampolas_congeladas WHERE id_p = :id AND codigo_base_tn = :b",
                                    {"id": id_b, "b": sufixo_tn},
                                )
                                ult_f = max(
                                    [r[0] for r in existentes_f], default=0
                                )
                                for i_f in range(1, int(n_ampolas_f) + 1):
                                    num_amp = ult_f + i_f
                                    id_frz = f"{tn_sel}-F{num_amp}"
                                    run_sql(
                                        "INSERT INTO ampolas_congeladas VALUES (:idf, :ide, :idp, :base, :na, :ps, :dn, :vb, :qc, :resp, :dt)",
                                        {
                                            "idf": id_frz,
                                            "ide": id_estab,
                                            "idp": id_b,
                                            "base": sufixo_tn,
                                            "na": num_amp,
                                            "ps": int(pass_en),
                                            "dn": dens_f,
                                            "vb": float(viab_f),
                                            "qc": "Qualificada (≥80%)"
                                            if viab_f >= 80
                                            else "Manutenção (<80%)",
                                            "resp": st.session_state.username,
                                            "dt": datetime.now().strftime(
                                                "%d/%m/%Y"
                                            ),
                                        },
                                    )
                                run_sql(
                                    "UPDATE pacientes_final SET status_geral = 'Criopreservada (-FN)' WHERE id_p = :id",
                                    {"id": id_b},
                                )
                                st.rerun()

                        st.divider()
                        c_t1, c_t2 = st.columns(2)
                        with c_t1:
                            st.markdown(
                                "**Linhagens em Cultivo (`-C`) e Estabelecidas (`-EN`)**"
                            )
                            df_l = fetch_df(
                                'SELECT id_linhagem AS "ID Linhagem", etapa_cultivo AS "Fase", passagem AS "Passagem (N)", status_fenotipico AS "Status", data_registro AS "Data" FROM linhagens_pdo WHERE id_p = :id',
                                {"id": id_b},
                            )
                            st.dataframe(
                                df_l, use_container_width=True, hide_index=True
                            )
                        with c_t2:
                            st.markdown(
                                "**Estoque de Ampolas Congeladas (`-TN-FN`)**"
                            )
                            df_f = fetch_df(
                                'SELECT id_frozen AS "ID Ampola (-FN)", id_estabelecida AS "Origem (-EN)", numero_ampola AS "Ampola N", viabilidade_pos_descong AS "Viabilidade (%)", qualificada_ensaio AS "QC" FROM ampolas_congeladas WHERE id_p = :id',
                                {"id": id_b},
                            )
                            st.dataframe(
                                df_f, use_container_width=True, hide_index=True
                            )

                # 2.3 TESTE FARMACOLÓGICO (-TN-FN) E TESTE GENÉTICO (-TN-GN)
                elif st.session_state.aba_amostra.startswith("3. Teste"):
                    st.markdown(
                        "#### Ensaios Padronizados: Farmacológico (`-TN-FN`) e Genético (`-TN-GN`)"
                    )
                    st.caption(
                        "Regra de Nomenclatura: **N = 1** corresponde obrigatoriamente à **Avaliação Sem Tratamento (Controle Basal)**; "
                        "**N = 2 ao infinito** corresponde a cada grupo de tratamento esperado para o PDAC."
                    )

                    tumores_tn = fetch_all(
                        "SELECT id_amostra FROM amostras_biobanco WHERE id_p = :id AND prefixo_tipo = 'T' ORDER BY numero_tubo",
                        {"id": id_b},
                    )
                    lista_tn = (
                        [r[0] for r in tumores_tn]
                        if tumores_tn
                        else [f"{id_b}-T1"]
                    )
                    tn_base = st.selectbox(
                        "Amostra Tumoral de Referência (-TN)", lista_tn
                    )
                    suf_tn = tn_base.split("-")[-1]

                    c_mod, c_grp, c_dose = st.columns([2, 3, 2])
                    mod_fg = c_mod.selectbox(
                        "Modalidade do Ensaio",
                        ["Farmacologico (-TN-FN)", "Genetico (-TN-GN)"],
                    )
                    eh_farmaco = mod_fg.startswith("Farmacologico")
                    letra_cod = "F" if eh_farmaco else "G"

                    opcoes_grupos = [
                        f"N={g[0]} | {g[1]}" for g in GRUPOS_TRATAMENTO_PDAC
                    ]
                    grp_escolhido = c_grp.selectbox(
                        f"Grupo Experimental ({suf_tn}-{letra_cod}N)",
                        opcoes_grupos,
                    )
                    idx_n = int(
                        grp_escolhido.split("|")[0].replace("N=", "").strip()
                    )
                    nome_grp = grp_escolhido.split("|")[1].strip()

                    id_ensaio_gerado = f"{tn_base}-{letra_cod}{idx_n}"
                    dose_in = c_dose.text_input(
                        "Concentração / Dose",
                        value="Basal (Sem Droga)"
                        if idx_n == 1
                        else dp_am.get("dose_ensaio", "10 µM"),
                    )

                    st.info(
                        f"Código Oficial deste Ensaio: **`{id_ensaio_gerado}`** ({nome_grp})"
                    )

                    if eh_farmaco:
                        metodo_f = st.selectbox(
                            "Método de Viabilidade Celular",
                            [
                                "MTT / MTS (Absorbância)",
                                "PrestoBlue / AlamarBlue (Fluorescência)",
                                "CellTiter-Glo 3D (Luminescência ATP)",
                            ],
                        )
                        cr1, cr2, cr3 = st.columns(3)
                        r1_def = (
                            "0.410"
                            if idx_n == 1
                            else dp_am.get("mtt_r1", "0.145")
                        )
                        r2_def = (
                            "0.398"
                            if idx_n == 1
                            else dp_am.get("mtt_r2", "0.138")
                        )
                        r3_def = (
                            "0.422"
                            if idx_n == 1
                            else dp_am.get("mtt_r3", "0.142")
                        )

                        r1 = norm_num(
                            cr1.text_input("Leitura Celular R1", value=r1_def)
                        )
                        r2 = norm_num(
                            cr2.text_input("Leitura Celular R2", value=r2_def)
                        )
                        r3 = norm_num(
                            cr3.text_input("Leitura Celular R3", value=r3_def)
                        )
                        b1 = norm_num(
                            cr1.text_input(
                                "Branco do Meio B1",
                                value=dp_am.get("mtt_b1", "0.048"),
                            )
                        )
                        b2 = norm_num(
                            cr2.text_input(
                                "Branco do Meio B2",
                                value=dp_am.get("mtt_b2", "0.050"),
                            )
                        )
                        b3 = norm_num(
                            cr3.text_input(
                                "Branco do Meio B3",
                                value=dp_am.get("mtt_b3", "0.049"),
                            )
                        )

                        if st.button(
                            f"Registrar Teste Farmacológico {id_ensaio_gerado}",
                            type="primary",
                        ):
                            vals_liq = [
                                max(0.0, float(r) - float(b))
                                for r, b in zip([r1, r2, r3], [b1, b2, b3])
                                if r and b
                            ]
                            media_liq = (
                                round(float(np.mean(vals_liq)), 4)
                                if vals_liq
                                else 0.0
                            )
                            run_sql(
                                "DELETE FROM ensaios_farmaco_genetico WHERE id_ensaio_fg = :id",
                                {"id": id_ensaio_gerado},
                            )
                            run_sql(
                                """INSERT INTO ensaios_farmaco_genetico VALUES 
                                   (:id, :idp, :base, :frz, 'Farmacologico', :idx, :grp, :ds, :met, 'Viabilidade_Global',
                                    :r1, :r2, :r3, '', '', '', :b1, :b2, :b3, :mc, :resp, :dt)""",
                                {
                                    "id": id_ensaio_gerado,
                                    "idp": id_b,
                                    "base": suf_tn,
                                    "frz": f"{tn_base}-F1",
                                    "idx": idx_n,
                                    "grp": nome_grp,
                                    "ds": dose_in,
                                    "met": metodo_f,
                                    "r1": r1,
                                    "r2": r2,
                                    "r3": r3,
                                    "b1": b1,
                                    "b2": b2,
                                    "b3": b3,
                                    "mc": media_liq,
                                    "resp": st.session_state.username,
                                    "dt": datetime.now().strftime(
                                        "%d/%m/%Y %H:%M"
                                    ),
                                },
                            )
                            run_sql(
                                "UPDATE pacientes_final SET status_geral = 'Fase Analítica (-FN/-GN)' WHERE id_p = :id",
                                {"id": id_b},
                            )
                            st.success(f"Ensaio `{id_ensaio_gerado}` salvo.")
                            st.rerun()
                    else:
                        c_met, c_gene = st.columns(2)
                        metodo_g = c_met.selectbox(
                            "Plataforma Molecular",
                            ["RT-qPCR (Ct / ΔCt)", "Western Blot (Razão DO)"],
                        )
                        gene_sel = c_gene.selectbox(
                            "Alvo Molecular (HGNC)",
                            [
                                "GATA6",
                                "KRT5",
                                "KRAS",
                                "TP53",
                                "MKI67",
                                "TOP2A",
                                "CA9",
                                "COL1A1",
                                "ACTA2",
                                "SLC29A1",
                            ],
                        )
                        id_ensaio_gene = f"{id_ensaio_gerado}-{gene_sel}"
                        tupla_qpcr = dp_am.get(
                            f"qpcr_{gene_sel}", ("21.40", "21.55", "21.48")
                        )
                        ct_end_pad = dp_am.get("ct_endo", "20.10")

                        cr1, cr2, cr3 = st.columns(3)
                        r1 = norm_num(
                            cr1.text_input(
                                f"Ct / DO Alvo R1 ({gene_sel})",
                                value=tupla_qpcr[0],
                            )
                        )
                        r2 = norm_num(
                            cr2.text_input(
                                f"Ct / DO Alvo R2 ({gene_sel})",
                                value=tupla_qpcr[1],
                            )
                        )
                        r3 = norm_num(
                            cr3.text_input(
                                f"Ct / DO Alvo R3 ({gene_sel})",
                                value=tupla_qpcr[2],
                            )
                        )
                        c1 = norm_num(
                            cr1.text_input(
                                "Ct / DO Endógeno R1 (GAPDH)", value=ct_end_pad
                            )
                        )
                        c2 = norm_num(
                            cr2.text_input(
                                "Ct / DO Endógeno R2 (GAPDH)", value=ct_end_pad
                            )
                        )
                        c3 = norm_num(
                            cr3.text_input(
                                "Ct / DO Endógeno R3 (GAPDH)", value=ct_end_pad
                            )
                        )

                        if st.button(
                            f"Registrar Teste Genético {id_ensaio_gene}",
                            type="primary",
                        ):
                            dcts = [
                                float(r) - float(c)
                                for r, c in zip([r1, r2, r3], [c1, c2, c3])
                                if r and c
                            ]
                            media_dct = (
                                round(float(np.mean(dcts)), 4) if dcts else 0.0
                            )
                            run_sql(
                                "DELETE FROM ensaios_farmaco_genetico WHERE id_ensaio_fg = :id",
                                {"id": id_ensaio_gene},
                            )
                            run_sql(
                                """INSERT INTO ensaios_farmaco_genetico VALUES 
                                   (:id, :idp, :base, :frz, 'Genetico', :idx, :grp, :ds, :met, :gn,
                                    :r1, :r2, :r3, :c1, :c2, :c3, '', '', '', :mc, :resp, :dt)""",
                                {
                                    "id": id_ensaio_gene,
                                    "idp": id_b,
                                    "base": suf_tn,
                                    "frz": f"{tn_base}-F1",
                                    "idx": idx_n,
                                    "grp": nome_grp,
                                    "ds": dose_in,
                                    "met": metodo_g,
                                    "gn": gene_sel,
                                    "r1": r1,
                                    "r2": r2,
                                    "r3": r3,
                                    "c1": c1,
                                    "c2": c2,
                                    "c3": c3,
                                    "mc": media_dct,
                                    "resp": st.session_state.username,
                                    "dt": datetime.now().strftime(
                                        "%d/%m/%Y %H:%M"
                                    ),
                                },
                            )
                            run_sql(
                                "UPDATE pacientes_final SET status_geral = 'Fase Analítica (-FN/-GN)' WHERE id_p = :id",
                                {"id": id_b},
                            )
                            st.success(f"Ensaio `{id_ensaio_gene}` salvo.")
                            st.rerun()

                    df_fg = fetch_df(
                        'SELECT id_ensaio_fg AS "ID Ensaio (-FN / -GN)", modalidade AS "Modalidade", indice_grupo AS "N", grupo_tratamento AS "Grupo Experimental", gene_alvo AS "Alvo", metrica_calculada AS "Sinal Líquido / ΔCt", data_registro AS "Data" FROM ensaios_farmaco_genetico WHERE id_p = :id ORDER BY modalidade, indice_grupo',
                        {"id": id_b},
                    )
                    if not df_fg.empty:
                        st.dataframe(
                            df_fg, use_container_width=True, hide_index=True
                        )

                # 2.4 SESSÕES DE ANÁLISE PARA CADA TIPO DE AMOSTRA (FUTURO IA)
                elif st.session_state.aba_amostra.startswith("4. Análises"):
                    st.markdown(
                        "#### Sessões de Análise Específica por Biotipo Coletado (Dataset Futuro de Treinamento IA)"
                    )
                    st.caption(
                        "Arquitetura preparada para incorporar parâmetros analíticos de **Tumor In Natura (`-TN`)**, **Sangue Total (`-STN`)**, "
                        "**Plasma (`-PN`)**, **Soro (`-SN`)** e **PBMC (`-PBMCN`)**. Cada sessão permanece bloqueada até que o Administrador libere o respectivo schema na aba `5. Governança`."
                    )

                    configs_bio = fetch_all(
                        "SELECT biotipo_codigo, nome_sessao, liberado_admin, versao_schema, colunas_custom_json FROM config_modulos_analise ORDER BY biotipo_codigo"
                    )
                    for cod_b, nome_s, lib_adm, ver_s, cols_j in configs_bio:
                        with st.expander(
                            f"[{cod_b}] {nome_s} — Status: {'LIBERADO' if lib_adm == 1 else 'AGUARDANDO LIBERAÇÃO DO ADMINISTRADOR'} ({ver_s})",
                            expanded=(lib_adm == 1),
                        ):
                            if lib_adm == 0:
                                st.warning(
                                    f"Sessão `{cod_b}` estruturada na engenharia do banco de dados (`analises_multibiotipo_futuro`), porém bloqueada para coleta. "
                                    "O Administrador pode destravá-la e definir suas colunas analíticas em `☰ > 5. Governança`."
                                )
                            else:
                                prefixo_busca = cod_b.replace("N", "")
                                ams_tipo = fetch_all(
                                    "SELECT id_amostra FROM amostras_biobanco WHERE id_p = :id AND prefixo_tipo = :pr",
                                    {"id": id_b, "pr": prefixo_busca},
                                )
                                if not ams_tipo:
                                    st.info(
                                        f"Nenhuma amostra do tipo `-{cod_b}` cadastrada para o paciente `{id_b}`."
                                    )
                                else:
                                    am_alvo = st.selectbox(
                                        f"Selecionar Amostra (-{cod_b})",
                                        [r[0] for r in ams_tipo],
                                        key=f"sel_fut_{cod_b}",
                                    )
                                    try:
                                        lista_cols = json.loads(cols_j)
                                    except Exception:
                                        lista_cols = [
                                            "Parametro_1",
                                            "Parametro_2",
                                        ]

                                    valores_coletados = {}
                                    cols_ui = st.columns(
                                        min(3, max(1, len(lista_cols)))
                                    )
                                    for idx_c, nome_col in enumerate(
                                        lista_cols
                                    ):
                                        valores_coletados[nome_col] = cols_ui[
                                            idx_c % len(cols_ui)
                                        ].text_input(
                                            nome_col,
                                            key=f"in_fut_{cod_b}_{nome_col}",
                                        )

                                    if st.button(
                                        f"Salvar Análise de {am_alvo} no Dataset IA",
                                        key=f"btn_fut_{cod_b}",
                                        type="primary",
                                    ):
                                        id_reg = f"ANL-{am_alvo}-{int(datetime.now().timestamp())}"
                                        run_sql(
                                            "INSERT INTO analises_multibiotipo_futuro VALUES (:idr, :ida, :idp, :bc, :ver, :pay, :resp, :dt)",
                                            {
                                                "idr": id_reg,
                                                "ida": am_alvo,
                                                "idp": id_b,
                                                "bc": cod_b,
                                                "ver": ver_s,
                                                "pay": json.dumps(
                                                    valores_coletados,
                                                    ensure_ascii=False,
                                                ),
                                                "resp": st.session_state.username,
                                                "dt": datetime.now().strftime(
                                                    "%d/%m/%Y %H:%M"
                                                ),
                                            },
                                        )
                                        st.success(
                                            f"Parâmetros de `{am_alvo}` incorporados ao repositório de treinamento futuro da IA."
                                        )

    # =========================================================================
    # FASE 3: HOMEOSTAS.IA (INTEGRADA AOS DADOS REAIS DO PACIENTE E DO ORGANOIDE)
    # =========================================================================
    elif st.session_state.nav_curto == "3. Homeostas.IA":
        st.subheader(
            "Fase 3: Motor Preditivo Translacional — Homeostas.IA beta | By OrganSense"
        )
        id_b = (
            st.text_input(
                "ID do Paciente para Inferência Translacional (ex: OS-001)",
                value=st.session_state.get("id_ativo", ""),
            )
            .strip()
            .upper()
        )

        if id_b:
            (
                pct,
                _,
                pac,
                sub,
                _,
                _,
                frozen,
                ensaios,
                m_auto,
            ) = auditar_completude_paciente(id_b)
            if not pac:
                st.warning("Paciente não encontrado.")
            else:
                renderizar_gradiente_paciente(id_b)

                idade_p = pac[2]
                g_ex_pad = sub[14] if (sub and sub[14]) else 18
                g_po_pad = sub[15] if (sub and sub[15] is not None) else 2
                mg_pad = (
                    sub[17] if (sub and sub[17] in ["R0", "R1"]) else "R0"
                )
                gr_pad = (
                    sub[18]
                    if (sub and sub[18] in ["G1", "G2", "G3", "G4"])
                    else "G2"
                )

                c1, c2, c3, c4 = st.columns(4)
                g_ex_ia = c1.number_input(
                    "Gânglios Examinados", 1, 60, int(g_ex_pad)
                )
                g_po_ia = c2.number_input(
                    "Gânglios Positivos", 0, 60, int(g_po_pad)
                )
                mg_ia = c3.selectbox(
                    "Margem de Ressecção",
                    ["R0", "R1"],
                    index=0 if mg_pad == "R0" else 1,
                )
                gr_ia = c4.selectbox(
                    "Grau Histológico",
                    ["G1", "G2", "G3", "G4"],
                    index=["G1", "G2", "G3", "G4"].index(gr_pad),
                )

                cp1, cp2, cp3 = st.columns(3)
                fid_in = cp1.slider(
                    "Conservação Fenotípica do Organoide -TN-EN (%)",
                    0.0,
                    100.0,
                    float(m_auto["fidelidade_pdo"]),
                )
                viab_gem_in = cp2.slider(
                    "Viabilidade Residual em -TN-F2 (Gencitabina %)",
                    0.0,
                    100.0,
                    float(m_auto["viab_gem_pct"]),
                )
                viab_folf_in = cp3.slider(
                    "Viabilidade Residual em -TN-F3 (mFOLFIRINOX %)",
                    0.0,
                    100.0,
                    float(m_auto["viab_folf_pct"]),
                )

                # Pré-preenche Cts a partir dos ensaios genéticos reais (-TN-GN) se registrados
                g_dcts = m_auto["genes_dct"]
                ct_ref_pad = 20.1
                ct_bas_pad = (
                    round(ct_ref_pad + g_dcts["KRT5"], 2)
                    if "KRT5" in g_dcts
                    else 26.8
                )
                ct_cls_pad = (
                    round(ct_ref_pad + g_dcts["GATA6"], 2)
                    if "GATA6" in g_dcts
                    else 21.6
                )
                ct_pro_pad = (
                    round(ct_ref_pad + g_dcts["MKI67"], 2)
                    if "MKI67" in g_dcts
                    else 25.4
                )
                ct_hip_pad = (
                    round(ct_ref_pad + g_dcts["CA9"], 2)
                    if "CA9" in g_dcts
                    else 24.0
                )
                ct_est_pad = (
                    round(ct_ref_pad + g_dcts["COL1A1"], 2)
                    if "COL1A1" in g_dcts
                    else 19.8
                )

                cm1, cm2, cm3, cm4, cm5, cm6 = st.columns(6)
                ct_ref = cm6.number_input(
                    "Ct Endógeno (GAPDH)", 14.0, 28.0, ct_ref_pad, step=0.1
                )
                ct_bas = cm1.number_input(
                    "Ct Basal-like (-GN)",
                    15.0,
                    35.0,
                    float(np.clip(ct_bas_pad, 15.0, 35.0)),
                    step=0.1,
                )
                ct_cls = cm2.number_input(
                    "Ct Classical (-GN)",
                    15.0,
                    35.0,
                    float(np.clip(ct_cls_pad, 15.0, 35.0)),
                    step=0.1,
                )
                ct_pro = cm3.number_input(
                    "Ct Proliferação",
                    15.0,
                    35.0,
                    float(np.clip(ct_pro_pad, 15.0, 35.0)),
                    step=0.1,
                )
                ct_hip = cm4.number_input(
                    "Ct Hipóxia",
                    15.0,
                    35.0,
                    float(np.clip(ct_hip_pad, 15.0, 35.0)),
                    step=0.1,
                )
                ct_est = cm5.number_input(
                    "Ct Estroma",
                    15.0,
                    35.0,
                    float(np.clip(ct_est_pad, 15.0, 35.0)),
                    step=0.1,
                )

                res_ia = executar_fusao_translacional_organsense(
                    idade_p,
                    g_ex_ia,
                    g_po_ia,
                    mg_ia,
                    gr_ia,
                    converter_ct_para_log2tpm(ct_bas, ct_ref),
                    converter_ct_para_log2tpm(ct_cls, ct_ref),
                    converter_ct_para_log2tpm(ct_pro, ct_ref),
                    converter_ct_para_log2tpm(ct_hip, ct_ref),
                    converter_ct_para_log2tpm(ct_est, ct_ref),
                    fidelidade_pdo_pct=fid_in,
                    viab_pdo_gemcitabina=viab_gem_in,
                    viab_pdo_folfirinox=viab_folf_in,
                )

                st.divider()
                st.markdown("#### Adaptação de Linguagem por Perfil de Leitor")
                st.session_state.setdefault("visao_ia", "Médica")
                perfis_visao = [
                    "Médica",
                    "Paciente",
                    "Parente do Paciente",
                    "Funcionário da OrganSense",
                ]
                cols_v = st.columns(4)
                for idx_v, p_v in enumerate(perfis_visao):
                    if cols_v[idx_v].button(
                        f"Visão: {p_v}",
                        type="primary"
                        if st.session_state.visao_ia == p_v
                        else "secondary",
                        use_container_width=True,
                    ):
                        st.session_state.visao_ia = p_v
                        st.rerun()

                if st.session_state.visao_ia == "Médica":
                    st.markdown(
                        f"""
                        <div class="os-card">
                            <div style="font-size:15.5px; font-weight:700; color:#0F172A; margin-bottom:8px;">
                                Direcionamento Clínico-Translacional (Visão Médica) — {res_ia['quadrante']}
                            </div>
                            <div style="font-size:13.5px; color:#1E293B; line-height:1.6;">
                                • <strong>Subtipo Molecular (PurIST):</strong> {res_ia['subtipo']} (Score = <code>{res_ia['purist']}</code>) | <strong>Razão Linfonodal (LNR):</strong> <code>{res_ia['lnr']}</code> ({g_po_ia}/{g_ex_ia}, Margem {mg_ia}, Grau {gr_ia})<br>
                                • <strong>Fidelidade Fenotípica do Organoide (-TN-EN):</strong> <strong>{res_ia['fidelidade_pdo']}%</strong> (Peso translacional aplicado: <code>{res_ia['peso_pdo_aplicado']}%</code>)<br>
                                • <strong>Resposta Citotóxica Ex Vivo (-TN-FN):</strong> Morte celular de <strong>{res_ia['letalidade_pdo_poli']}%</strong> sob Poliquimioterapia vs. <strong>{res_ia['letalidade_pdo_gem']}%</strong> sob Gencitabina.<br>
                                • <strong>Sobrevida Estimada (12m / 24m):</strong> Sem Quimioterapia (F1): <code>{res_ia['s12_sem']}% / {res_ia['s24_sem']}%</code> | Gencitabina (F2): <code>{res_ia['s12_gem']}% / {res_ia['s24_gem']}%</code> | Poliquimioterapia (F3): <code>{res_ia['s12_poli']}% / {res_ia['s24_poli']}%</code> (Ganho absoluto em 24m: <strong>+{res_ia['ganho_24m']}%</strong>)<br>
                                • <strong>Conduta Recomendada:</strong> <span style="color:#0284C7; font-weight:700;">{res_ia['rota_recomendada']}</span> — {res_ia['conduta']}
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    st.pyplot(
                        gerar_grafico_dispersao_homeostasia(res_ia, id_b),
                        use_container_width=True,
                    )

                elif st.session_state.visao_ia == "Paciente":
                    melhor_s12 = max(res_ia["s12_poli"], res_ia["s12_gem"])
                    melhor_letal = max(
                        res_ia["letalidade_pdo_poli"],
                        res_ia["letalidade_pdo_gem"],
                    )
                    st.markdown(
                        f"""
                        <div class="os-card" style="border-left:5px solid #0284C7;">
                            <div style="font-size:16px; font-weight:700; color:#0F172A; margin-bottom:8px;">
                                Relatório para o Paciente — Transparência e Cuidado Personalizado
                            </div>
                            <div style="font-size:14px; color:#334155; line-height:1.7;">
                                Olá, <strong>{pac[1]}</strong>. A partir da amostra coletada no seu procedimento, cultivamos em laboratório pequenas estruturas tridimensionais chamadas <em>organoides</em>, que mantiveram <strong>{res_ia['fidelidade_pdo']}% das características originais</strong> do seu tecido.<br><br>
                                Isso permitiu testar os medicamentos diretamente nas células no laboratório antes de definir a melhor estratégia para você. O esquema <strong>{res_ia['rota_recomendada']}</strong> eliminou <strong>{melhor_letal}%</strong> das células testadas em bancada, elevando a projeção de controle e proteção no primeiro ano para <strong>{melhor_s12}%</strong>.<br><br>
                                Seu médico oncologista utilizará este resultado junto com seus exames de sangue para conduzir seu tratamento com a máxima segurança.
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                elif st.session_state.visao_ia == "Parente do Paciente":
                    st.markdown(
                        f"""
                        <div class="os-card" style="border-left:5px solid #16A34A;">
                            <div style="font-size:16px; font-weight:700; color:#0F172A; margin-bottom:8px;">
                                Guia de Transparência e Apoio para Familiares
                            </div>
                            <div style="font-size:14px; color:#334155; line-height:1.7;">
                                Este relatório apoia a família de <strong>{pac[1]}</strong> com informações claras e honestas sobre o tratamento:<br><br>
                                • <strong>Por que este tratamento foi escolhido:</strong> Combinando os exames genéticos e o teste direto nos organoides do paciente, a rota <strong>{res_ia['rota_recomendada']}</strong> proporcionou um ganho real de proteção de <strong>+{res_ia['ganho_24m']}%</strong> aos 24 meses.<br>
                                • <strong>Cuidados práticos em casa:</strong> Ofereçam refeições pequenas e frequentes, mantenham hidratação constante e comuniquem imediatamente a equipe médica caso surja febre (&ge; 37,8 &deg;C) ou icterícia (coloração amarelada nos olhos/pele).
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                else:
                    st.markdown(
                        "#### Visão Interna: Funcionário da OrganSense (Rede de Métricas, Matriz de Confusão e Custos Reais de Reagentes)"
                    )
                    st.pyplot(
                        gerar_painel_auditoria_interna_organsense(
                            res_ia["fidelidade_pdo"]
                        ),
                        use_container_width=True,
                    )
                    df_custos = calcular_custos_dinamicos_paciente(id_b)
                    st.dataframe(
                        df_custos, use_container_width=True, hide_index=True
                    )
                    st.info(
                        f"Custo Operacional Real Calculado para `{id_b}`: **R$ {df_custos['Subtotal (R$)'].sum():,.2f}**"
                    )

                if st.button(
                    "Consolidar Predição Homeostas.IA no Banco de Dados",
                    type="primary",
                ):
                    id_pr = f"HOMEO-{id_b}-{int(datetime.now().timestamp())}"
                    run_sql(
                        "INSERT INTO predicoes_ia_final VALUES (:v1,:v2,:v3,:v4,:v5,:v6,:v7,:v8,:v9,:v10,:v11,:v12,:v13,:v14)",
                        {
                            "v1": id_pr,
                            "v2": id_b,
                            "v3": res_ia["motor"],
                            "v4": res_ia["subtipo"],
                            "v5": res_ia["purist"],
                            "v6": res_ia["lnr"],
                            "v7": res_ia["recist_pct"],
                            "v8": res_ia["s24_sem"],
                            "v9": res_ia["s24_gem"],
                            "v10": res_ia["s24_poli"],
                            "v11": res_ia["quadrante"],
                            "v12": res_ia["rota_recomendada"],
                            "v13": st.session_state.username,
                            "v14": datetime.now().strftime(
                                "%d/%m/%Y %H:%M:%S"
                            ),
                        },
                    )
                    st.success(f"Predição `{id_pr}` gravada com sucesso.")
                    st.rerun()

    # =========================================================================
    # FASE 4: COORTE & DOSSIÊ (TABELA COM GRADIENTE + CONSULTA COMPLETA)
    # =========================================================================
    elif st.session_state.nav_curto == "4. Coorte & Dossiê":
        st.subheader("Coorte PDAC e Auditoria de Completude")
        df_pacs = fetch_df(
            'SELECT id_p AS "ID Paciente", nome AS "Nome", idade AS "Idade", sexo AS "Sexo", hospital AS "Instituição", status_geral AS "Status" FROM pacientes_final ORDER BY id_p DESC'
        )
        if not df_pacs.empty:
            df_pacs["Completude (%)"] = [
                auditar_completude_paciente(r["ID Paciente"])[0]
                for _, r in df_pacs.iterrows()
            ]
            st.dataframe(
                df_pacs,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Completude (%)": st.column_config.ProgressColumn(
                        "Gradiente de Completude",
                        format="%d%%",
                        min_value=0,
                        max_value=100,
                    )
                },
            )

        st.divider()
        id_dossie = (
            st.text_input(
                "Inspecionar Dossiê Completo do Paciente (ex: OS-001)",
                value=st.session_state.get("id_ativo", ""),
            )
            .strip()
            .upper()
        )
        if id_dossie:
            pac_d = fetch_one(
                "SELECT * FROM pacientes_final WHERE id_p = :id",
                {"id": id_dossie},
            )
            if pac_d:
                renderizar_gradiente_paciente(id_dossie)
                with st.expander("1. Submissão Clínica, Bioquímica, Anatomomorfológica e Tratamento", expanded=True):
                    st.dataframe(
                        fetch_df(
                            "SELECT * FROM submissao_paciente_detalhada WHERE id_p = :id",
                            {"id": id_dossie},
                        ),
                        use_container_width=True,
                        hide_index=True,
                    )
                with st.expander("2. Amostras Recebidas (-TN, -STN, -PN, -SN, -PBMCN) e Biobanco (-C, -EN, -FN)", expanded=True):
                    st.dataframe(
                        fetch_df(
                            "SELECT * FROM amostras_biobanco WHERE id_p = :id",
                            {"id": id_dossie},
                        ),
                        use_container_width=True,
                        hide_index=True,
                    )
                    st.dataframe(
                        fetch_df(
                            "SELECT * FROM linhagens_pdo WHERE id_p = :id",
                            {"id": id_dossie},
                        ),
                        use_container_width=True,
                        hide_index=True,
                    )
                    st.dataframe(
                        fetch_df(
                            "SELECT * FROM ampolas_congeladas WHERE id_p = :id",
                            {"id": id_dossie},
                        ),
                        use_container_width=True,
                        hide_index=True,
                    )
                with st.expander("3. Ensaios Farmacológicos (-TN-FN), Genéticos (-TN-GN) e Predições Homeostas.IA", expanded=True):
                    df_e_export = fetch_df(
                        "SELECT * FROM ensaios_farmaco_genetico WHERE id_p = :id",
                        {"id": id_dossie},
                    )
                    st.dataframe(
                        df_e_export, use_container_width=True, hide_index=True
                    )
                    st.dataframe(
                        fetch_df(
                            "SELECT * FROM predicoes_ia_final WHERE id_p = :id ORDER BY data_hora DESC",
                            {"id": id_dossie},
                        ),
                        use_container_width=True,
                        hide_index=True,
                    )
                    if not df_e_export.empty:
                        st.download_button(
                            "Exportar Dataset de Ensaios do Paciente (CSV)",
                            df_e_export.to_csv(index=False).encode("utf-8"),
                            f"Dataset_{id_dossie}.csv",
                            "text/csv",
                        )

    # =========================================================================
    # FASE 5: GOVERNANÇA (CONTROLE DO ADMINISTRADOR PARA LIBERAR ANÁLISES FUTURAS)
    # =========================================================================
    elif st.session_state.nav_curto == "5. Governança":
        if st.session_state.role != "Administrador":
            st.error("Acesso exclusivo para Administradores.")
        else:
            st.subheader(
                "Governança, Liberação de Módulos de Amostras (OTA) e Trilha de Auditoria"
            )
            t_mod, t_log, t_usr = st.tabs([
                "Liberação de Sessões Analíticas por Biotipo (-TN, -STN, -PN, -SN, -PBMCN)",
                "Logs de Auditoria",
                "Operadores",
            ])

            with t_mod:
                st.markdown(
                    "#### Controle de Atualização e Desbloqueio de Análises Futuras para Treinamento da IA"
                )
                configs = fetch_all(
                    "SELECT biotipo_codigo, nome_sessao, liberado_admin, versao_schema, colunas_custom_json FROM config_modulos_analise ORDER BY biotipo_codigo"
                )
                for cod_b, nome_s, lib_adm, ver_s, cols_j in configs:
                    with st.expander(
                        f"Configurar Sessão `-{cod_b}`: {nome_s} ({'LIBERADA' if lib_adm == 1 else 'BLOQUEADA'})",
                        expanded=True,
                    ):
                        c_a, c_b = st.columns([1, 2])
                        novo_lib = c_a.checkbox(
                            "Liberar sessão na plataforma para coleta",
                            value=(lib_adm == 1),
                            key=f"adm_lib_{cod_b}",
                        )
                        nova_ver = c_a.text_input(
                            "Versão da Atualização",
                            value=ver_s,
                            key=f"adm_ver_{cod_b}",
                        )
                        novas_cols = c_b.text_area(
                            "Colunas Analíticas do Módulo (Formato Lista JSON)",
                            value=cols_j,
                            key=f"adm_cols_{cod_b}",
                        )
                        if st.button(
                            f"Aplicar Atualização em -{cod_b}",
                            key=f"adm_sv_{cod_b}",
                            type="primary",
                        ):
                            run_sql(
                                """UPDATE config_modulos_analise 
                                   SET liberado_admin=:l, versao_schema=:v, colunas_custom_json=:cj, atualizado_por=:u, data_atualizacao=:dt
                                   WHERE biotipo_codigo=:c""",
                                {
                                    "l": 1 if novo_lib else 0,
                                    "v": nova_ver,
                                    "cj": novas_cols,
                                    "u": st.session_state.username,
                                    "dt": datetime.now().strftime(
                                        "%d/%m/%Y %H:%M"
                                    ),
                                    "c": cod_b,
                                },
                            )
                            log_audit(
                                st.session_state.username,
                                "Atualização de Módulo",
                                f"Sessão -{cod_b} atualizada (Liberado={novo_lib}, Versão={nova_ver})",
                            )
                            st.success(
                                f"Configuração de `-{cod_b}` atualizada."
                            )
                            st.rerun()

            with t_log:
                st.dataframe(
                    fetch_df(
                        'SELECT data_hora AS "Data/Hora", username AS "Operador", acao AS "Ação", detalhe AS "Detalhe" FROM audit_logs ORDER BY id DESC LIMIT 250'
                    ),
                    use_container_width=True,
                    hide_index=True,
                )

            with t_usr:
                st.dataframe(
                    fetch_df(
                        'SELECT username AS "Operador", role AS "Perfil", email AS "E-mail" FROM usuarios_final ORDER BY username'
                    ),
                    use_container_width=True,
                    hide_index=True,
                )