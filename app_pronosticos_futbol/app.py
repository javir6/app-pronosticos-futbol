import streamlit as st
import pandas as pd
import numpy as np
from scipy.stats import poisson
import requests
import os
import hashlib
import time
import re
import itertools
import warnings
import json as _json
from io import StringIO
from datetime import datetime
from difflib import get_close_matches
warnings.filterwarnings('ignore')


# ============================================================================
# SISTEMA DE CONTRASEÑA Y ACCESO
# ============================================================================

PASSWORD_FILE  = "password.txt"
ADMIN_PASSWORD = "admin_jr6_secret"   # ← cámbiala


def _leer_password():
    # 1. Primero intenta Streamlit Secrets (Streamlit Cloud)
    try:
        return st.secrets["PASSWORD"]
    except Exception:
        pass
    # 2. Si no hay secrets, lee desde archivo local
    if not os.path.exists(PASSWORD_FILE):
        return "Angus2026"   # contraseña por defecto
    with open(PASSWORD_FILE, "r") as f:
        return f.read().strip()


def _hash(texto):
    return hashlib.sha256(texto.encode()).hexdigest()


def verificar_acceso():
    if st.session_state.get('autenticado'):
        password_actual = _leer_password()
        if st.session_state.get('password_hash') != _hash(password_actual):
            st.session_state.clear()
            st.rerun()
        return True

    st.markdown("""
    <style>
        [data-testid="stSidebar"] { display: none; }
        .block-container { max-width: 460px; margin: auto; padding-top: 80px; }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div style='text-align:center; margin-bottom:40px;'>
        <div style='font-size:72px;'>⚽</div>
        <h1 style='color:#e94560; margin:8px 0 4px 0;'>Asistente de Apuestas JR6</h1>
        <p style='color:#888; font-size:15px;'>Acceso restringido — Introduce la contraseña</p>
    </div>
    """, unsafe_allow_html=True)

    pwd_input = st.text_input("🔑 Contraseña", type="password",
                               placeholder="Escribe la contraseña...", key="login_pwd")
    entrar = st.button("🚀 Entrar", use_container_width=True, type="primary")

    if entrar:
        if not pwd_input.strip():
            st.error("❌ Escribe la contraseña.")
            return False
        password_correcta = _leer_password()
        if pwd_input.strip() == password_correcta:
            st.session_state['autenticado']   = True
            st.session_state['password_hash'] = _hash(password_correcta)
            st.session_state['login_ts']      = datetime.now().strftime('%d/%m/%Y %H:%M')
            st.success("✅ Acceso correcto. Cargando...")
            time.sleep(0.6)
            st.rerun()
        else:
            st.error("❌ Contraseña incorrecta.")

    st.markdown("<p style='text-align:center;color:#555;font-size:13px;margin-top:20px;'>"
                "¿No tienes acceso? Contacta con el administrador.</p>", unsafe_allow_html=True)
    return False


def mostrar_info_sesion_sidebar():
    ts = st.session_state.get('login_ts', '')
    with st.sidebar:
        st.markdown(
            f"<div style='background:#1a1a2e;border:1px solid #e94560;"
            f"border-radius:8px;padding:10px 14px;margin-bottom:8px;'>"
            f"<span style='color:#e94560;font-weight:bold;'>🔓 Sesión activa</span><br>"
            f"<span style='color:#888;font-size:11px;'>Desde {ts}</span></div>",
            unsafe_allow_html=True
        )
        if st.button("🚪 Cerrar sesión", use_container_width=True, key="logout_btn"):
            st.session_state.clear()
            st.rerun()


def mostrar_panel_cambio_password():
    with st.sidebar:
        with st.expander("🔧 Panel Administrador", expanded=False):
            admin_pwd = st.text_input("Contraseña de admin", type="password",
                                       key="admin_pwd_chk", placeholder="Solo para el administrador")
            if admin_pwd != ADMIN_PASSWORD:
                if admin_pwd: st.error("❌ Contraseña de admin incorrecta.")
                return
            st.success("✅ Acceso de administrador")
            st.divider()
            st.markdown("**🔑 Cambiar contraseña de acceso**")
            nueva_pwd = st.text_input("Nueva contraseña", key="nueva_pwd_in")
            confirmar = st.text_input("Confirmar", type="password", key="confirm_pwd_in")
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("💾 Guardar", use_container_width=True, key="save_pwd"):
                    if not nueva_pwd.strip():          st.error("❌ No puede estar vacía.")
                    elif nueva_pwd != confirmar:       st.error("❌ No coinciden.")
                    elif len(nueva_pwd) < 4:           st.error("❌ Mínimo 4 caracteres.")
                    else:
                        with open(PASSWORD_FILE, "w") as f: f.write(nueva_pwd.strip())
                        st.session_state['password_hash'] = _hash(nueva_pwd.strip())
                        st.success("✅ Contraseña cambiada.")
                        st.info("Los demás usuarios serán desconectados en su próxima acción.")
            with col_b:
                st.code(f"Actual: {_leer_password()}", language=None)


# ============================================================================
# CONFIGURACIÓN INICIAL
# ============================================================================

def detectar_movil():
    try:
        user_agent = st.query_params.get("user_agent", [""])
        return any(k in str(user_agent).lower() for k in ['mobile','android','iphone','ipad'])
    except: return False

ES_MOVIL = detectar_movil()

st.set_page_config(
    page_title="⚽ Asistente de Apuestas JR6 - Fútbol Profesional",
    page_icon="⚽",
    layout="centered" if ES_MOVIL else "wide",
    initial_sidebar_state="collapsed" if ES_MOVIL else "expanded"
)

st.markdown("""
<style>
    .big-font  { font-size:26px !important; font-weight: bold; }
    .green-big { color: #2ecc71; font-size:26px !important; font-weight: bold; }
    .red-big   { color: #e74c3c; font-size:26px !important; font-weight: bold; }
    .yellow-big{ color: #f1c40f; font-size:26px !important; font-weight: bold; }
    .stButton>button { width: 100%; }
    .value-alta {
        background: linear-gradient(90deg, #27ae60 0%, #2ecc71 100%);
        color: white; padding: 15px; border-radius: 10px; margin: 10px 0;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .value-media {
        background: linear-gradient(90deg, #f39c12 0%, #f1c40f 100%);
        color: white; padding: 15px; border-radius: 10px; margin: 10px 0;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .alerta-card {
        padding: 15px; border-radius: 10px; margin: 10px 0;
        font-weight: bold; border-left: 5px solid;
        background-color: #f8f9fa; box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    .alerta-verde    { border-left-color: #2e7d32; background-color: #e8f5e9; color: #1b5e20; }
    .alerta-amarilla { border-left-color: #ff8f00; background-color: #fff8e1; color: #e65100; }
    .alerta-azul     { border-left-color: #1565c0; background-color: #e3f2fd; color: #0d47a1; }
    .combo-winner {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
        color: #e0e0e0; padding: 20px; border-radius: 14px; margin: 10px 0;
        border: 2px solid #e94560; box-shadow: 0 8px 20px rgba(233,69,96,0.3);
    }
    .combo-partido {
        background: #0f0f1a; border-left: 4px solid #e94560;
        padding: 12px 16px; border-radius: 8px; margin: 8px 0; color: #e0e0e0;
    }
    .combo-stat {
        background: rgba(255,255,255,0.05); border-radius: 8px;
        padding: 10px; text-align: center; color: #e0e0e0;
    }
    .ia-explicacion {
        background: linear-gradient(135deg, #0d1b2a, #1b263b);
        border: 1px solid #415a77; border-radius: 12px;
        padding: 20px; color: #e0e0e0; margin-top: 15px; line-height: 1.7;
    }
    .ia-badge {
        background: #e94560; color: white; border-radius: 20px;
        padding: 3px 12px; font-size: 12px; font-weight: bold;
        display: inline-block; margin-bottom: 10px;
    }
    .q-table { width:100%; border-collapse:collapse; margin-top:10px; }
    .q-table th { background:#e94560; color:white; padding:8px 12px; text-align:left; font-size:13px; }
    .q-table td { padding:9px 12px; border-bottom:1px solid rgba(100,100,100,0.2); font-size:14px; }
    .q-table tr:hover td { background:rgba(255,255,255,0.03); }
    .badge-1 { background:#1e4d2b; color:#2ecc71; border-radius:5px; padding:2px 7px; font-weight:bold; margin:0 2px; }
    .badge-X { background:#4d3a00; color:#f1c40f; border-radius:5px; padding:2px 7px; font-weight:bold; margin:0 2px; }
    .badge-2 { background:#1a2e4d; color:#3498db; border-radius:5px; padding:2px 7px; font-weight:bold; margin:0 2px; }
    .t-simple { background:#1e3a5f; color:#90caf9; border-radius:10px; padding:2px 8px; font-size:11px; font-weight:bold; }
    .t-doble  { background:#3a1e5f; color:#ce93d8; border-radius:10px; padding:2px 8px; font-size:11px; font-weight:bold; }
    .t-triple { background:#5f3a1e; color:#ffcc80; border-radius:10px; padding:2px 8px; font-size:11px; font-weight:bold; }
    @media (max-width: 768px) {
        .stButton button { min-height: 50px; font-size: 18px; }
    }
</style>
""", unsafe_allow_html=True)


# ============================================================================
# PESOS TEMPORALES Y FORTALEZAS
# ============================================================================

def calcular_pesos_temporales(fechas, factor_decaimiento=0.003):
    if fechas.empty: return np.array([])
    fecha_max = fechas.max()
    dias_diff = (fecha_max - fechas).dt.days
    pesos     = np.exp(-factor_decaimiento * dias_diff)
    return pesos / pesos.sum()


def calcular_fortalezas_liga(df_liga, min_partidos=5):
    if df_liga.empty or len(df_liga) < 10: return {},{},{},{},1.5,1.2
    ml = df_liga['FTHG'].mean(); mv = df_liga['FTAG'].mean()
    if ml == 0 or mv == 0: return {},{},{},{},1.5,1.2
    equipos = set(df_liga['HomeTeam'].unique()) | set(df_liga['AwayTeam'].unique())
    ah,dh,aa,da = {},{},{},{}
    for eq in equipos:
        hd = df_liga[df_liga['HomeTeam']==eq]
        if len(hd)>=min_partidos: ah[eq]=hd['FTHG'].mean()/ml; dh[eq]=hd['FTAG'].mean()/mv
        ad = df_liga[df_liga['AwayTeam']==eq]
        if len(ad)>=min_partidos: aa[eq]=ad['FTAG'].mean()/mv; da[eq]=ad['FTHG'].mean()/ml
    return ah,dh,aa,da,ml,mv


# ============================================================================
# MODELO DIXON-COLES
# ============================================================================

class PronosticadorDixonColes:
    def __init__(self, df_total, df_local, df_visitante, local, visitante,
                 num_partidos=20, factor_decaimiento=0.003):
        self.df_total=df_total; self.local=local; self.visitante=visitante
        self.num_partidos=num_partidos; self.factor_decaimiento=factor_decaimiento
        self.df_local=df_local.tail(num_partidos*2)
        self.df_visitante=df_visitante.tail(num_partidos*2)
        self._calcular_fortalezas_liga()
        self._calcular_medias_ponderadas()
        self._calcular_todo()

    def _calcular_fortalezas_liga(self):
        col_liga='Liga' if 'Liga' in self.df_total.columns else ('Div' if 'Div' in self.df_total.columns else None)
        self.attack_h=self.defence_h=self.attack_a=self.defence_a={}
        self.media_liga_local=1.5; self.media_liga_visit=1.2; self.liga_detectada=None
        if col_liga is None: return
        data_eq=self.df_total[self.df_total['HomeTeam']==self.local]
        if not data_eq.empty:
            ligas_eq=data_eq[col_liga].value_counts()
            if not ligas_eq.empty:
                self.liga_detectada=ligas_eq.index[0]
                df_liga=self.df_total[self.df_total[col_liga]==self.liga_detectada].copy()
                ah,dh,aa,da,ml,mv=calcular_fortalezas_liga(df_liga)
                self.attack_h,self.defence_h=ah,dh; self.attack_a,self.defence_a=aa,da
                self.media_liga_local,self.media_liga_visit=ml,mv

    def _calcular_media_ponderada_goles(self, df, equipo, condicion):
        if condicion=='local': sub=df[df['HomeTeam']==equipo].copy(); goles=sub['FTHG']
        else:                  sub=df[df['AwayTeam']==equipo].copy();  goles=sub['FTAG']
        if goles.empty: return 0.0
        gc=goles[goles<=5]; sc=sub[goles<=5]
        if gc.empty: return goles.mean()
        if 'Date' in sc.columns and not sc['Date'].isna().all():
            pw=calcular_pesos_temporales(sc['Date'],self.factor_decaimiento)
            if len(pw)==len(gc): return np.average(gc.values,weights=pw)
        return gc.mean()

    def _calcular_medias_ponderadas(self):
        ml_raw=self._calcular_media_ponderada_goles(self.df_local,    self.local,    'local')
        mv_raw=self._calcular_media_ponderada_goles(self.df_visitante,self.visitante,'visitante')
        if (self.attack_h and self.defence_a
                and self.local in self.attack_h and self.visitante in self.defence_a):
            self.media_local    =(self.media_liga_local*self.attack_h.get(self.local,1.0)*self.defence_a.get(self.visitante,1.0))
            self.media_visitante=(self.media_liga_visit*self.attack_a.get(self.visitante,1.0)*self.defence_h.get(self.local,1.0))
            self.modo_modelo="Dixon-Coles"
        else:
            self.media_local    =ml_raw if ml_raw>0 else 1.2
            self.media_visitante=mv_raw if mv_raw>0 else 1.0
            self.modo_modelo="Poisson Ponderado"
        self.media_local    =max(0.3,min(4.0,self.media_local))
        self.media_visitante=max(0.3,min(4.0,self.media_visitante))
        self.media_total    =self.media_local+self.media_visitante

    def _calcular_todo(self):
        self.prob_local_1    =(1-poisson.pmf(0,self.media_local))*100
        self.prob_visitante_1=(1-poisson.pmf(0,self.media_visitante))*100
        self.prob_ambos      =(self.prob_local_1/100*self.prob_visitante_1/100)*100
        self.prob_over_25    =(1-poisson.cdf(2,self.media_total))*100
        self.prob_under_25   =poisson.cdf(2,self.media_total)*100
        self.matriz,self.p_win,self.p_draw,self.p_lose=self._calcular_matriz()
        self.corners_total  =self._calcular_media_estadistica('HC','AC')
        self.tarjetas_total =self._calcular_media_estadistica(['HY','HR'],['AY','AR'])
        self.faltas_total   =self._calcular_media_estadistica('HF','AF')

    def _calcular_media_estadistica(self, col_local, col_visitante):
        total=0
        for df,cols in [(self.df_local,col_local),(self.df_visitante,col_visitante)]:
            if isinstance(cols,list):
                for c in cols:
                    if c in df.columns: total+=df[c].mean() if not df[c].isna().all() else 0
            else:
                if cols in df.columns: total+=df[cols].mean() if not df[cols].isna().all() else 0
        return max(0,total)

    def _calcular_matriz(self):
        pl=[poisson.pmf(i,self.media_local)     for i in range(8)]
        pv=[poisson.pmf(i,self.media_visitante) for i in range(8)]
        m=np.outer(pl,pv)
        return m,np.sum(np.tril(m,-1))*100,np.diag(m).sum()*100,np.sum(np.triu(m,1))*100

    def get_fiabilidad(self):
        n=len(self.df_local)+len(self.df_visitante)
        if n>35:   return "ALTA", "#2ecc71","✅ Muestra muy representativa"
        elif n>20: return "MEDIA","#f1c40f","⚠️ Muestra aceptable"
        else:      return "BAJA", "#e74c3c","❌ Pocos datos, usar con precaución"

    def get_marcador_sugerido(self):
        idx=np.unravel_index(np.argmax(self.matriz),self.matriz.shape)
        return idx[0],idx[1],self.matriz[idx]*100


# ============================================================================
# CACHÉ DE PRONÓSTICOS
# ============================================================================

MAX_CACHE = 20

def _cache_key(local,visitante,num,decay):
    return f"{local}|{visitante}|{num}|{decay:.4f}"

def get_pronostico_cacheado(local,visitante,num,decay):
    return st.session_state.get('cache_pronosticos',{}).get(_cache_key(local,visitante,num,decay),None)

def guardar_pronostico_cache(local,visitante,num,decay,datos):
    if 'cache_pronosticos' not in st.session_state: st.session_state['cache_pronosticos']={}
    if 'cache_orden'       not in st.session_state: st.session_state['cache_orden']=[]
    key=_cache_key(local,visitante,num,decay)
    if key in st.session_state['cache_orden']: st.session_state['cache_orden'].remove(key)
    st.session_state['cache_pronosticos'][key]=datos
    st.session_state['cache_orden'].append(key)
    while len(st.session_state['cache_orden'])>MAX_CACHE:
        old=st.session_state['cache_orden'].pop(0)
        st.session_state['cache_pronosticos'].pop(old,None)

def mostrar_panel_cache_sidebar():
    n=len(st.session_state.get('cache_pronosticos',{}))
    if n>0:
        st.caption(f"🗂️ Pronósticos en caché: {n}/{MAX_CACHE}")
        if st.button("🗑️ Limpiar caché",use_container_width=True,key="clear_cache"):
            st.session_state['cache_pronosticos']={}; st.session_state['cache_orden']=[]
            st.rerun()


# ============================================================================
# ALERTA DIVERGENCIA TEMPORADAS
# ============================================================================

def analizar_divergencia_temporadas(df_equipo, equipo, num_partidos):
    if 'Temporada' not in df_equipo.columns: return None
    df_rec=df_equipo.tail(num_partidos*2); total=len(df_rec)
    if total==0: return None
    n_actual  =(df_rec['Temporada']=='2526').sum()
    n_anterior=(df_rec['Temporada']=='2425').sum()
    pct=n_anterior/total*100
    return {'total':total,'n_actual':int(n_actual),'n_anterior':int(n_anterior),
            'pct_anterior':round(pct,1),'alerta':pct>60}

def check_alerta_divergencia(df_total, local, visitante, num_partidos):
    alertas=[]
    for equipo in [local,visitante]:
        df_eq=df_total[(df_total['HomeTeam']==equipo)|(df_total['AwayTeam']==equipo)]
        r=analizar_divergencia_temporadas(df_eq,equipo,num_partidos)
        if r and r['alerta']:
            alertas.append({'equipo':equipo,'pct_anterior':r['pct_anterior'],
                            'n_actual':r['n_actual'],'n_anterior':r['n_anterior']})
    return alertas


# ============================================================================
# MÓDULO COMBINADA IA  (incluye córners)
# ============================================================================

def _prob_corners(corners_total):
    """Probabilidades de córners usando Poisson con la media calculada."""
    if corners_total <= 0:
        return {}
    return {
        'Córners Over 7.5':  round((1-poisson.cdf(7,  corners_total))*100, 1),
        'Córners Under 7.5': round(poisson.cdf(7,  corners_total)*100, 1),
        'Córners Over 8.5':  round((1-poisson.cdf(8,  corners_total))*100, 1),
        'Córners Under 8.5': round(poisson.cdf(8,  corners_total)*100, 1),
        'Córners Over 9.5':  round((1-poisson.cdf(9,  corners_total))*100, 1),
        'Córners Under 9.5': round(poisson.cdf(9,  corners_total)*100, 1),
        'Córners Over 10.5': round((1-poisson.cdf(10, corners_total))*100, 1),
        'Córners Under 10.5':round(poisson.cdf(10, corners_total)*100, 1),
    }


def analizar_partido_para_combinada(df_total, local, visitante, num_partidos=20, factor_decay=0.003):
    dl=df_total[(df_total['HomeTeam']==local)     | (df_total['AwayTeam']==local)]
    dv=df_total[(df_total['HomeTeam']==visitante) | (df_total['AwayTeam']==visitante)]
    if dl.empty or dv.empty: return None
    try:
        p=PronosticadorDixonColes(df_total,dl,dv,local,visitante,num_partidos,factor_decay)

        # Opciones de goles y resultado
        opciones=[
            {'mercado':f'Local ({local})',        'prob':p.p_win,       'tipo':'1X2',   'cuota_est':max(1.3,100/max(p.p_win,1))},
            {'mercado':'Empate',                   'prob':p.p_draw,      'tipo':'1X2',   'cuota_est':max(1.3,100/max(p.p_draw,1))},
            {'mercado':f'Visitante ({visitante})', 'prob':p.p_lose,      'tipo':'1X2',   'cuota_est':max(1.3,100/max(p.p_lose,1))},
            {'mercado':'1X',                       'prob':p.p_win+p.p_draw, 'tipo':'D.Oport.','cuota_est':max(1.1,100/max(p.p_win+p.p_draw,1))},
            {'mercado':'X2',                       'prob':p.p_draw+p.p_lose,'tipo':'D.Oport.','cuota_est':max(1.1,100/max(p.p_draw+p.p_lose,1))},
            {'mercado':'12',                       'prob':p.p_win+p.p_lose, 'tipo':'D.Oport.','cuota_est':max(1.1,100/max(p.p_win+p.p_lose,1))},
            {'mercado':'Over 1.5',  'prob':(1-poisson.cdf(1,p.media_total))*100,'tipo':'Goles','cuota_est':1.55},
            {'mercado':'Under 1.5', 'prob':poisson.cdf(1,p.media_total)*100,     'tipo':'Goles','cuota_est':2.40},
            {'mercado':'Over 2.5',  'prob':p.prob_over_25,  'tipo':'Goles','cuota_est':2.0},
            {'mercado':'Under 2.5', 'prob':p.prob_under_25, 'tipo':'Goles','cuota_est':1.9},
            {'mercado':'Ambos Marcan - SI','prob':p.prob_ambos,      'tipo':'BTTS','cuota_est':1.95},
            {'mercado':'Ambos Marcan - NO','prob':100-p.prob_ambos,  'tipo':'BTTS','cuota_est':1.85},
        ]

        # Añadir córners si hay datos
        if p.corners_total > 0:
            probs_c=_prob_corners(p.corners_total)
            # Seleccionamos la línea más cercana a la media para que sea la más relevante
            lineas_over =['Córners Over 7.5','Córners Over 8.5','Córners Over 9.5','Córners Over 10.5']
            lineas_under=['Córners Under 7.5','Córners Under 8.5','Córners Under 9.5','Córners Under 10.5']
            for mercado_c in lineas_over+lineas_under:
                prob_c=probs_c.get(mercado_c,0)
                if prob_c>0:
                    linea=float(mercado_c.split()[-1])
                    # Cuota estimada basada en la probabilidad
                    cuota_c=max(1.2, min(3.5, round(100/max(prob_c,1),2)))
                    opciones.append({'mercado':mercado_c,'prob':prob_c,'tipo':'Córners','cuota_est':cuota_c})

        mejor=max(opciones,key=lambda x:x['prob'])
        return {
            'local':local,'visitante':visitante,
            'p_win':round(p.p_win,1),'p_draw':round(p.p_draw,1),'p_lose':round(p.p_lose,1),
            'prob_over25':round(p.prob_over_25,1),'prob_ambos':round(p.prob_ambos,1),
            'corners_total':round(p.corners_total,1),
            'media_local':round(p.media_local,2),'media_visit':round(p.media_visitante,2),
            'modo':p.modo_modelo,'mejor_opcion':mejor,
            'todas_opciones':sorted(opciones,key=lambda x:x['prob'],reverse=True),
        }
    except Exception: return None


def calcular_mejor_combinada(partidos, min_p=2, max_p=4, prob_ind=0.52, prob_conj=0.12):
    if not partidos: return None
    candidatos=[]
    for p in partidos:
        for op in p['todas_opciones']:
            if op['prob']/100>=prob_ind:
                candidatos.append({
                    'partido_label':f"{p['local']} vs {p['visitante']}",
                    'local':p['local'],'visitante':p['visitante'],
                    'mercado':op['mercado'],'prob':op['prob']/100,
                    'cuota_est':op['cuota_est'],'tipo':op['tipo'],'modo':p['modo'],
                })
    vistos,filtrados=set(),[]
    for c in sorted(candidatos,key=lambda x:x['prob'],reverse=True):
        if c['partido_label'] not in vistos:
            filtrados.append(c); vistos.add(c['partido_label'])
    if len(filtrados)<min_p: return None
    mejor,mejor_ev=None,-999
    for n in range(min_p,min(max_p+1,len(filtrados)+1)):
        for combo in itertools.combinations(filtrados,n):
            pc=1.0; qc=1.0
            for s in combo: pc*=s['prob']; qc*=s['cuota_est']
            if pc<prob_conj: continue
            ev=pc*qc-1
            if ev>mejor_ev:
                mejor_ev=ev
                mejor={'selecciones':list(combo),'prob_conjunta':round(pc*100,2),
                       'cuota_conjunta':round(qc,2),'ev_pct':round(ev*100,2),'n':n}
    return mejor


def llamar_ia_combinada(partidos, mejor_combo, api_key=""):
    rs=[f"- {p['local']} vs {p['visitante']}: L={p['p_win']}% E={p['p_draw']}% V={p['p_lose']}% "
        f"O25={p['prob_over25']}% BTTS={p['prob_ambos']}% Corners={p['corners_total']}" for p in partidos]
    rc=[f"- {s['partido_label']}: {s['mercado']} ({s['prob']*100:.1f}%, ~{s['cuota_est']:.2f}) [{s['tipo']}]"
        for s in mejor_combo['selecciones']]
    prompt=(f"Eres un analista experto en apuestas deportivas.\n\nPARTIDOS:\n{chr(10).join(rs)}\n\n"
            f"COMBINADA ÓPTIMA ({mejor_combo['n']} sel., prob={mejor_combo['prob_conjunta']}%, "
            f"cuota={mejor_combo['cuota_conjunta']}x, EV={mejor_combo['ev_pct']}%):\n{chr(10).join(rc)}\n\n"
            f"Análisis experto breve (máx 200 palabras): justificación estadística, nivel de confianza, "
            f"gestión de bankroll y valoración honesta. En español, sin markdown.")
    if api_key and api_key.strip():
        try:
            r=requests.post("https://api.anthropic.com/v1/messages",
                headers={"Content-Type":"application/json","x-api-key":api_key,"anthropic-version":"2023-06-01"},
                json={"model":"claude-sonnet-4-20250514","max_tokens":500,
                      "messages":[{"role":"user","content":prompt}]},timeout=30)
            if r.status_code==200: return r.json()['content'][0]['text'],True
        except Exception: pass
    pc=mejor_combo['prob_conjunta']; ev=mejor_combo['ev_pct']; cuota=mejor_combo['cuota_conjunta']
    niv="bajo" if pc>=40 else "moderado" if pc>=22 else "elevado"
    bk=3 if pc>=40 else 2 if pc>=22 else 1
    lns=[f"Combinada de {mejor_combo['n']} selecciones. Prob. conjunta: {pc}%, cuota estimada: {cuota}x.",""]
    for s in mejor_combo['selecciones']:
        pp=s['prob']*100
        cf="alta confianza" if pp>=65 else "confianza media" if pp>=55 else "confianza ajustada"
        lns.append(f"- {s['mercado']} en {s['partido_label']}: {pp:.1f}% ({cf}) [{s['tipo']}].")
    lns+=["",f"EV positivo del {ev}%. Riesgo {niv}.",f"Bankroll recomendado: max {bk}%.",
          "","Advertencia: factores externos (lesiones, motivacion) no incluidos en el modelo."]
    return "\n".join(lns),False


def mostrar_tab_combinada(df_total, num_partidos, factor_decay, api_key_anthropic):
    st.subheader("🤖 Generador de Apuesta Combinada con IA")
    st.markdown("Introduce entre **2 y 10 enfrentamientos**. La IA seleccionará la **combinada óptima** "
                "considerando resultado, goles y **córners**.")
    equipos=sorted(set(df_total['HomeTeam'].unique())|set(df_total['AwayTeam'].unique()))

    with st.expander("⚙️ Parámetros",expanded=False):
        c1,c2,c3=st.columns(3)
        with c1:
            min_sel=st.slider("Mín. selecciones",2,4,2)
            max_sel=st.slider("Máx. selecciones",2,6,4)
        with c2:
            prob_ind =st.slider("Prob. mínima individual (%)",45,70,52)/100
            prob_conj=st.slider("Prob. mínima conjunta (%)",5,35,12)/100
        with c3:
            incluir_corners=st.checkbox("Incluir córners en la combinada", value=True,
                help="Usa la distribución Poisson de córners para añadir mercados de córners")
            st.info("**Prob. individual**: descarta selecciones bajo este umbral.\n\n"
                    "**Prob. conjunta**: descarta combinadas con probabilidad total inferior.")

    st.markdown("### 📋 Partidos a analizar")
    if 'num_combo' not in st.session_state: st.session_state.num_combo=3
    ca,cr,_=st.columns([1,1,4])
    with ca:
        if st.button("➕ Añadir",use_container_width=True,key="c_add"):
            if st.session_state.num_combo<10: st.session_state.num_combo+=1
    with cr:
        if st.button("➖ Quitar",use_container_width=True,key="c_rem"):
            if st.session_state.num_combo>2: st.session_state.num_combo-=1

    seleccionados=[]
    for i in range(st.session_state.num_combo):
        c1,c2,c3=st.columns([1,3,3])
        with c1: st.markdown(f"<br><b>#{i+1}</b>",unsafe_allow_html=True)
        with c2: loc=st.selectbox(f"🏠 Local #{i+1}",   equipos,index=min(i*2,  len(equipos)-1),key=f"cl_{i}")
        with c3: vis=st.selectbox(f"🚀 Visitante #{i+1}",equipos,index=min(i*2+1,len(equipos)-1),key=f"cv_{i}")
        if loc!=vis: seleccionados.append((loc,vis))

    st.divider()
    if st.button("🚀 ANALIZAR Y GENERAR COMBINADA ÓPTIMA",use_container_width=True,type="primary"):
        if len(seleccionados)<2:
            st.error("❌ Necesitas al menos 2 partidos distintos."); return
        unicos=list(dict.fromkeys(seleccionados))
        with st.spinner("🔍 Analizando con Dixon-Coles + Córners..."):
            pb=st.progress(0); res=[]
            for i,(l,v) in enumerate(unicos):
                pb.progress((i+1)/len(unicos))
                r=analizar_partido_para_combinada(df_total,l,v,num_partidos,factor_decay)
                if r:
                    # Si el usuario no quiere córners, filtrar esas opciones
                    if not incluir_corners:
                        r['todas_opciones']=[op for op in r['todas_opciones'] if op['tipo']!='Córners']
                    res.append(r)
                else: st.warning(f"⚠️ Sin datos: {l} vs {v}")
            pb.empty()
        if len(res)<2:
            st.error("❌ Datos insuficientes."); return
        with st.spinner("🧮 Calculando combinación óptima..."):
            mc=calcular_mejor_combinada(res,min_sel,max_sel,prob_ind,prob_conj)
        if not mc:
            st.warning("⚠️ No se encontró combinada que cumpla los criterios. Reduce umbrales o añade más partidos.")
        else:
            nivel  ="BAJO" if mc['prob_conjunta']>=40 else "MEDIO" if mc['prob_conjunta']>=22 else "ALTO"
            emoji_r="🟢" if nivel=="BAJO" else "🟡" if nivel=="MEDIO" else "🔴"
            st.markdown("### 🏆 COMBINADA ÓPTIMA")
            st.markdown(f"""
            <div class="combo-winner">
                <div style="font-size:13px;opacity:0.7;margin-bottom:8px;">MEJOR COMBINADA · {mc['n']} SELECCIONES</div>
                <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:15px;">
                    <div class="combo-stat"><div style="font-size:28px;font-weight:900;color:#e94560;">{mc['prob_conjunta']}%</div><div style="font-size:11px;opacity:0.7;">Prob. Conjunta</div></div>
                    <div class="combo-stat"><div style="font-size:28px;font-weight:900;color:#4fc3f7;">{mc['cuota_conjunta']}x</div><div style="font-size:11px;opacity:0.7;">Cuota Estimada</div></div>
                    <div class="combo-stat"><div style="font-size:28px;font-weight:900;color:{'#2ecc71' if mc['ev_pct']>0 else '#e74c3c'};">{'+' if mc['ev_pct']>0 else ''}{mc['ev_pct']}%</div><div style="font-size:11px;opacity:0.7;">Valor Esperado</div></div>
                    <div class="combo-stat"><div style="font-size:28px;">{emoji_r}</div><div style="font-size:11px;opacity:0.7;">Riesgo {nivel}</div></div>
                </div>
            """,unsafe_allow_html=True)
            for s in mc['selecciones']:
                pp=s['prob']*100
                cp="#2ecc71" if pp>=65 else "#f1c40f" if pp>=52 else "#e74c3c"
                tipo_icon="🎯" if s['tipo']=='Córners' else "⚽" if s['tipo']=='Goles' else "🔄" if 'Oport' in s['tipo'] else "📊"
                st.markdown(f"""<div class="combo-partido">
                    <span style="font-size:13px;opacity:0.6;">{s['partido_label']}</span><br>
                    <span style="font-size:17px;font-weight:700;">{tipo_icon} {s['mercado']}</span>
                    <span style="margin-left:15px;color:{cp};font-weight:bold;">{pp:.1f}%</span>
                    <span style="margin-left:10px;opacity:0.6;font-size:13px;">~{s['cuota_est']:.2f}</span>
                    <span style="margin-left:10px;opacity:0.5;font-size:11px;">[{s['tipo']} · {s['modo']}]</span>
                </div>""",unsafe_allow_html=True)
            st.markdown("</div>",unsafe_allow_html=True)
            st.markdown("### 🤖 Análisis Experto IA")
            lbl="⚡ Claude AI" if (api_key_anthropic and api_key_anthropic.strip()) else "📊 Análisis local"
            with st.spinner(f"Generando análisis ({lbl})..."):
                expl,es_claude=llamar_ia_combinada(res,mc,api_key_anthropic)
            st.markdown(f"""<div class="ia-explicacion">
                <span class="ia-badge">{'🤖 Claude AI' if es_claude else '📊 Análisis estadístico'}</span>
                <p style="margin:0;white-space:pre-line;">{expl}</p>
            </div>""",unsafe_allow_html=True)
        st.divider()
        st.markdown("### 📊 Resumen de partidos analizados")
        filas=[{'Partido':f"{p['local']} vs {p['visitante']}",
                'Local %':p['p_win'],'Empate %':p['p_draw'],'Visit. %':p['p_lose'],
                'Over 2.5 %':p['prob_over25'],'BTTS %':p['prob_ambos'],
                'Córners (media)':p['corners_total'],
                'Mejor':p['mejor_opcion']['mercado'],
                'Prob.':f"{p['mejor_opcion']['prob']:.1f}%",'Modelo':p['modo']} for p in res]
        st.dataframe(pd.DataFrame(filas),use_container_width=True)
        st.download_button("📥 Exportar CSV",pd.DataFrame(filas).to_csv(index=False),
                           file_name=f"combinada_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",mime="text/csv")


# ============================================================================
# MÓDULO QUINIELA
# ============================================================================

SELAE_EQUIPOS_MAP = {
    'real madrid':'Real Madrid','barcelona':'Barcelona','fc barcelona':'Barcelona',
    'atletico':'Ath Madrid','atletico de madrid':'Ath Madrid','atletico madrid':'Ath Madrid',
    'athletic':'Ath Bilbao','athletic club':'Ath Bilbao','valencia':'Valencia',
    'sevilla':'Sevilla','betis':'Betis','real betis':'Betis','villarreal':'Villarreal',
    'celta':'Celta','celta de vigo':'Celta','rayo':'Rayo Vallecano','rayo vallecano':'Rayo Vallecano',
    'getafe':'Getafe','osasuna':'Osasuna','sociedad':'Sociedad','real sociedad':'Sociedad',
    'girona':'Girona','mallorca':'Mallorca','real mallorca':'Mallorca','alaves':'Alaves',
    'espanyol':'Espanol','las palmas':'Las Palmas','valladolid':'Valladolid','leganes':'Leganes',
    'zaragoza':'Zaragoza','sporting':'Sp Gijon','oviedo':'Oviedo','real oviedo':'Oviedo',
    'huesca':'Huesca','levante':'Levante','elche':'Elche','granada':'Granada',
    'tenerife':'Tenerife','albacete':'Albacete','almeria':'Almeria','eibar':'Eibar',
    'burgos':'Burgos','cordoba':'Cordoba','racing':'Racing Santander','mirandes':'Mirandes',
    'castellon':'Castellon','ferrol':'Racing Ferrol','cartagena':'Cartagena','eldense':'Eldense',
}

def _normalizar(txt):
    trans=str.maketrans('áéíóúàèìòùäëïöüâêîôûñ','aeiouaeiouaeiouaeioun')
    return txt.lower().strip().translate(trans)

def _fuzzy_match_equipo(nombre_raw, equipos_bd, cutoff=0.55):
    nombre_n=_normalizar(nombre_raw)
    if nombre_n in SELAE_EQUIPOS_MAP:
        mapped=SELAE_EQUIPOS_MAP[nombre_n]
        if mapped in equipos_bd: return mapped,'exact'
    for key,val in SELAE_EQUIPOS_MAP.items():
        if key in nombre_n or nombre_n in key:
            if val in equipos_bd: return val,'partial'
    m=get_close_matches(nombre_raw,equipos_bd,n=1,cutoff=cutoff)
    if m: return m[0],'fuzzy'
    el={_normalizar(e):e for e in equipos_bd}
    ml=get_close_matches(nombre_n,list(el.keys()),n=1,cutoff=cutoff)
    if ml: return el[ml[0]],'fuzzy-low'
    return None,'not_found'

def _extraer_partidos_json_selae(data):
    pares=[]
    nodes=[data] if isinstance(data,dict) else (data if isinstance(data,list) else [])
    for node in nodes:
        if not isinstance(node,dict): continue
        for key in ['partidos','matches','encuentros','jornada','eventos','results','data']:
            sub=node.get(key,[])
            if isinstance(sub,list):
                for item in sub:
                    if isinstance(item,dict):
                        loc=(item.get('local') or item.get('equipoLocal') or item.get('home') or item.get('homeTeam') or '')
                        vis=(item.get('visitante') or item.get('equipoVisitante') or item.get('away') or item.get('awayTeam') or '')
                        if loc and vis: pares.append((loc.strip(),vis.strip()))
    return pares if len(pares)>=5 else None

def obtener_jornada_quiniela_oficial(equipos_bd):
    hdrs={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
          'Accept':'text/html,application/xhtml+xml,application/json,*/*;q=0.8','Accept-Language':'es-ES,es;q=0.9'}
    pares_raw=[]
    try:
        r=requests.get('https://www.loteriasyapuestas.es/servicios/qultimos?game_id=LAQU&num=1',headers=hdrs,timeout=12)
        if r.status_code==200:
            p=_extraer_partidos_json_selae(r.json())
            if p: pares_raw=p
    except Exception: pass
    if not pares_raw:
        try:
            r=requests.get('https://www.loteriasyapuestas.es/es/la-quiniela',headers=hdrs,timeout=15)
            if r.status_code==200:
                html=r.text
                for patron in [r'window\.__INITIAL_STATE__\s*=\s*({.+?});\s*</script>',r'"partidos"\s*:\s*(\[.+?\])']:
                    m=re.search(patron,html,re.DOTALL)
                    if m:
                        try:
                            blob=_json.loads(m.group(1))
                            p=_extraer_partidos_json_selae(blob if isinstance(blob,dict) else {'partidos':blob})
                            if p: pares_raw=p; break
                        except: continue
        except Exception: pass
    if not pares_raw: return None
    resultado=[]; no_encontrados=[]
    for par in pares_raw:
        if not (isinstance(par,(list,tuple)) and len(par)==2): continue
        loc_raw,vis_raw=str(par[0]).strip(),str(par[1]).strip()
        loc_bd,cl=_fuzzy_match_equipo(loc_raw,equipos_bd)
        vis_bd,cv=_fuzzy_match_equipo(vis_raw,equipos_bd)
        resultado.append({'local_raw':loc_raw,'visit_raw':vis_raw,'local_bd':loc_bd,'visit_bd':vis_bd,
                          'mapeado':loc_bd is not None and vis_bd is not None,'confianza':f"{cl}/{cv}"})
        if loc_bd is None: no_encontrados.append(loc_raw)
        if vis_bd is None: no_encontrados.append(vis_raw)
    return resultado,no_encontrados

def analizar_partido_quiniela(df_total, local, visitante, num_partidos=20, factor_decay=0.003):
    dl=df_total[(df_total['HomeTeam']==local)     | (df_total['AwayTeam']==local)]
    dv=df_total[(df_total['HomeTeam']==visitante) | (df_total['AwayTeam']==visitante)]
    if dl.empty or dv.empty: return None
    try:
        p=PronosticadorDixonColes(df_total,dl,dv,local,visitante,num_partidos,factor_decay)
        gl,gv,pm=p.get_marcador_sugerido()
        return {'local':local,'visitante':visitante,'p1':round(p.p_win,1),'pX':round(p.p_draw,1),
                'p2':round(p.p_lose,1),'modo':p.modo_modelo,
                'marcador_sugerido':f"{int(gl)}-{int(gv)}",'prob_marcador':round(pm,1)}
    except Exception: return None

def calcular_incertidumbre(r):
    probs=sorted([r['p1'],r['pX'],r['p2']],reverse=True)
    return 1-(probs[0]-probs[1])/100

def calcular_seleccion_optima(r, tipo):
    probs={'1':r['p1'],'X':r['pX'],'2':r['p2']}
    ord_=sorted(probs.items(),key=lambda x:x[1],reverse=True)
    if tipo=='triple': return '1X2',['1','X','2']
    elif tipo=='doble':
        top2=sorted([ord_[0][0],ord_[1][0]],key=lambda s:['1','X','2'].index(s))
        return ''.join(top2),top2
    else: return ord_[0][0],[ord_[0][0]]

def calcular_quiniela(resultados, n_dobles, n_triples):
    n=len(resultados); nt_val=min(n_triples,n); nd_val=min(n_dobles,max(0,n-nt_val))
    orden=sorted(range(n),key=lambda i:calcular_incertidumbre(resultados[i]),reverse=True)
    tipos=['simple']*n
    for i in range(nt_val):
        if i<len(orden): tipos[orden[i]]='triple'
    dc=0
    for i in range(nt_val,len(orden)):
        if dc>=nd_val: break
        if tipos[orden[i]]=='simple': tipos[orden[i]]='doble'; dc+=1
    quiniela=[]; prob_total=1.0; coste_mult=1
    for i,res in enumerate(resultados):
        tipo=tipos[i]; signo,opciones=calcular_seleccion_optima(res,tipo)
        pa=sum(res['p1'] if o=='1' else res['pX'] if o=='X' else res['p2'] for o in opciones)/100
        prob_total*=pa
        if tipo=='doble': coste_mult*=2
        elif tipo=='triple': coste_mult*=3
        quiniela.append({'num':i+1,'local':res['local'],'visitante':res['visitante'],
                         'p1':res['p1'],'pX':res['pX'],'p2':res['p2'],'tipo':tipo,'signo':signo,
                         'opciones':opciones,'prob_aciertopartido':round(pa*100,1),'modo':res.get('modo','?'),
                         'marcador_sugerido':res.get('marcador_sugerido','?-?'),'prob_marcador':res.get('prob_marcador',0.0)})
    return {'quiniela':quiniela,'prob_total':round(prob_total*100,4),'coste_total':round(0.75*coste_mult,2),
            'coste_multiplicador':coste_mult,'n_dobles':dc,'n_triples':nt_val,'n_simples':n-dc-nt_val}

def mostrar_tab_quiniela(df_total, num_partidos, factor_decay):
    st.subheader("🎯 Generador de Quiniela Automático")
    st.markdown("Selecciona hasta **15 partidos**. El **partido #15** muestra el **marcador exacto más probable**.")
    equipos=sorted(set(df_total['HomeTeam'].unique())|set(df_total['AwayTeam'].unique()))

    with st.expander("🌐 Cargar jornada oficial SELAE",expanded=False):
        col_btn,col_info=st.columns([2,4])
        with col_btn:
            cargar_btn=st.button("🔄 Cargar jornada SELAE",use_container_width=True,key="selae_load")
        with col_info:
            st.caption("⚠️ Depende de la disponibilidad del sitio de SELAE.")
        if cargar_btn:
            with st.spinner("Conectando con SELAE..."):
                resultado_selae=obtener_jornada_quiniela_oficial(equipos)
            if resultado_selae is None:
                st.error("❌ No se pudo obtener la jornada. Selecciona manualmente.")
            else:
                pm,_=resultado_selae
                ok=[p for p in pm if p['mapeado']]; mal=[p for p in pm if not p['mapeado']]
                st.success(f"✅ {len(pm)} partidos — mapeados: {len(ok)}/{len(pm)}")
                if mal: st.warning("⚠️ No encontrados: "+", ".join(f"{p['local_raw']} vs {p['visit_raw']}" for p in mal))
                st.session_state['selae_partidos']=pm
        if 'selae_partidos' in st.session_state:
            df_map=pd.DataFrame([{'SELAE Local':p['local_raw'],'BD Local':p['local_bd'] or '❌',
                                   'SELAE Visitante':p['visit_raw'],'BD Visitante':p['visit_bd'] or '❌',
                                   'Estado':'✅' if p['mapeado'] else '⚠️'} for p in st.session_state['selae_partidos']])
            st.dataframe(df_map,use_container_width=True,height=320)

    st.markdown("**⚡ Presets rápidos:**")
    PRESETS=[("Sencilla",0,0),("4 Triples",0,4),("7 Dobles",7,0),("3D + 3T",3,3),("6D + 2T",6,2),("8 Triples",0,8),("11 Dobles",11,0)]
    costes_reducidos={(0,4):6.75,(7,0):12.00,(3,3):18.00,(6,2):48.00,(0,8):60.75,(11,0):99.00}
    def reset_quiniela_tipo():
        if 'quiniela_tipo' in st.session_state: del st.session_state['quiniela_tipo']
    cols_pre1=st.columns(len(PRESETS))
    for col,(label,d,t) in zip(cols_pre1,PRESETS):
        coste_norm=0.75*(2**d)*(3**t)
        if col.button(f"{label}\n({coste_norm:.2f}€)",use_container_width=True,
                      key=f"preset_norm_{label.replace(' ','_').replace('+','p')}"):
            st.session_state['qd']=d; st.session_state['qt']=t
            st.session_state['quiniela_tipo']='normal'; st.rerun()
    cols_pre2=st.columns(len(PRESETS))
    for col,(label,d,t) in zip(cols_pre2,PRESETS):
        red_cost=costes_reducidos.get((d,t)); coste_txt=f"{red_cost:.2f}€" if red_cost else "—"
        if col.button(f"{label}\n({coste_txt})",use_container_width=True,
                      key=f"preset_red_{label.replace(' ','_').replace('+','p')}"):
            st.session_state['qd']=d; st.session_state['qt']=t
            st.session_state['quiniela_tipo']='reducida'; st.rerun()

    st.markdown("### ⚙️ Configuración")
    c1,c2,c3=st.columns(3)
    with c1: n_partidos_q=st.slider("Número de partidos",5,15,15)
    with c2:
        n_dobles =st.slider("Dobles  (×2 coste)",0,12,4,on_change=reset_quiniela_tipo)
        n_triples=st.slider("Triples (×3 coste)",0, 8,0,on_change=reset_quiniela_tipo)
    with c3:
        nt_v=min(n_triples,n_partidos_q); nd_v=min(n_dobles,max(0,n_partidos_q-nt_v))
        coste_normal=0.75*(2**nd_v)*(3**nt_v)
        st.metric("💶 Coste quiniela normal",  f"{coste_normal:.2f}€")
        reducido=costes_reducidos.get((nd_v,nt_v))
        st.metric("💶 Coste quiniela reducida",f"{reducido:.2f}€" if reducido else "No disponible")
        st.caption(f"Simples: {n_partidos_q-nd_v-nt_v} · Dobles: {nd_v} · Triples: {nt_v}")
        if coste_normal>100: st.warning(f"⚠️ Coste muy elevado ({coste_normal:.2f}€)")
    if 'qd' in st.session_state: n_dobles=st.session_state['qd']; n_triples=st.session_state['qt']

    st.divider()
    st.markdown("### 📋 Partidos de la quiniela")
    selae_data=st.session_state.get('selae_partidos',[])
    partidos_q=[]
    for i in range(n_partidos_q):
        pre_local,pre_visit=None,None
        if i<len(selae_data) and selae_data[i]['mapeado']:
            pre_local=selae_data[i]['local_bd']; pre_visit=selae_data[i]['visit_bd']
        num_color="#f1c40f" if i==14 else "#e94560"; extra_label=" ⭐" if i==14 else ""
        cn,cl,cv=st.columns([0.5,3,3])
        with cn: st.markdown(f"<br><b style='color:{num_color};font-size:16px;'>{i+1}{extra_label}</b>",unsafe_allow_html=True)
        idx_l=(equipos.index(pre_local) if pre_local and pre_local in equipos else min(i*2,len(equipos)-1))
        idx_v=(equipos.index(pre_visit) if pre_visit and pre_visit in equipos else min(i*2+1,len(equipos)-1))
        with cl: lq=st.selectbox(f"Local #{i+1}",   equipos,index=idx_l,key=f"ql_{i}")
        with cv: vq=st.selectbox(f"Visitante #{i+1}",equipos,index=idx_v,key=f"qv_{i}")
        if lq!=vq: partidos_q.append((lq,vq))
    st.caption("⭐ El partido #15 muestra el marcador exacto más probable.")
    st.divider()

    if st.button("🎯 GENERAR QUINIELA ÓPTIMA",use_container_width=True,type="primary"):
        if len(partidos_q)<3:
            st.error("❌ Necesitas al menos 3 partidos distintos."); return
        with st.spinner("🔍 Analizando partidos con Dixon-Coles..."):
            pb=st.progress(0); res_q=[]
            for i,(l,v) in enumerate(partidos_q):
                pb.progress((i+1)/len(partidos_q))
                r=analizar_partido_quiniela(df_total,l,v,num_partidos,factor_decay)
                res_q.append(r if r else {'local':l,'visitante':v,'p1':40.0,'pX':28.0,'p2':32.0,
                                           'modo':'Sin datos','marcador_sugerido':'1-1','prob_marcador':10.0})
            pb.empty()
        rq=calcular_quiniela(res_q,n_dobles,n_triples)
        if st.session_state.get('quiniela_tipo')=='reducida':
            combo=(nd_v,nt_v); rc=costes_reducidos.get(combo)
            if rc is not None: rq['coste_total']=rc; rq['coste_multiplicador']=round(rc/0.75)
        st.session_state['ultima_quiniela']=rq
        st.session_state.pop('qd',None); st.session_state.pop('qt',None)
        if 'quiniela_tipo' in st.session_state: del st.session_state['quiniela_tipo']

    if 'ultima_quiniela' not in st.session_state: return
    rq=st.session_state['ultima_quiniela']
    st.markdown("### 🏆 TU QUINIELA ÓPTIMA")
    cm1,cm2,cm3,cm4=st.columns(4)
    cm1.metric("💶 Coste",      f"{rq['coste_total']:.2f}€")
    cm2.metric("🎯 Prob. pleno",f"{rq['prob_total']}%")
    cm3.metric("📊 Columnas",   f"×{rq['coste_multiplicador']}")
    cm4.metric("🔁 Config.",    f"{rq['n_simples']}S · {rq['n_dobles']}D · {rq['n_triples']}T")

    fh=""
    for s in rq['quiniela']:
        bds="".join(f"<span class='badge-{o}'>{o}</span>" for o in ['1','X','2'] if o in s['opciones'])
        tipo_str=s['tipo']
        t_badge="<span class='t-"+tipo_str+"'>"+tipo_str.upper()+"</span>"
        mp=max(s['p1'],s['pX'],s['p2'])
        c1_="#2ecc71" if s['p1']==mp else "#888"
        cX_="#2ecc71" if s['pX']==mp else "#888"
        c2_="#2ecc71" if s['p2']==mp else "#888"
        num_color="#f1c40f" if s['num']==15 else "#e94560"
        if s['num']==15:
            marc=s.get('marcador_sugerido','?-?'); pm_=s.get('prob_marcador',0.0)
            extra_td=("<td style='color:#f1c40f;font-size:13px;font-weight:bold;'>⭐ "+marc+
                      " <span style='font-size:11px;opacity:0.7;'>("+str(pm_)+"%)</span></td>")
        else: extra_td="<td></td>"
        fh+=("<tr><td><b style='color:"+num_color+";'>"+str(s['num'])+"</b></td>"
             "<td style='font-size:13px;'>"+s['local'][:14]+" vs "+s['visitante'][:14]+"</td>"
             "<td><span style='color:"+c1_+";'><b>1</b> "+str(s['p1'])+"%</span>&nbsp;&nbsp;"
             "<span style='color:"+cX_+";'><b>X</b> "+str(s['pX'])+"%</span>&nbsp;&nbsp;"
             "<span style='color:"+c2_+";'><b>2</b> "+str(s['p2'])+"%</span></td>"
             "<td>"+bds+"</td><td>"+t_badge+"</td>"
             "<td style='color:#888;font-size:12px;'>"+str(s['prob_aciertopartido'])+"%</td>"+extra_td+"</tr>")
    st.markdown("<table class='q-table'><thead><tr><th>#</th><th>Partido</th><th>Probabilidades</th>"
                "<th>Selección</th><th>Tipo</th><th>Prob. acierto</th><th>Marcador exacto (#15)</th>"
                "</tr></thead><tbody>"+fh+"</tbody></table>",unsafe_allow_html=True)
    st.divider()
    cr1,cr2=st.columns(2)
    with cr1:
        st.markdown("#### 📋 Selecciones para copiar")
        st.code(" - ".join(s['signo'] for s in rq['quiniela']),language=None)
        st.caption("☝️ Copia y pega para rellenar tu quiniela")
        sh="<div style='display:flex;flex-wrap:wrap;gap:6px;margin-top:8px;'>"
        for s in rq['quiniela']:
            bg="#3a1e5f" if s['tipo']=='doble' else "#5f3a1e" if s['tipo']=='triple' else "#1a1a2e"
            br="#ce93d8" if s['tipo']=='doble' else "#ffcc80" if s['tipo']=='triple' else "#415a77"
            if s['num']==15: bg="#3a3000"; br="#f1c40f"
            sh+=("<div style='background:"+bg+";border:2px solid "+br+";border-radius:6px;"
                 "padding:4px 10px;font-weight:bold;font-size:14px;color:white;min-width:40px;text-align:center;'>"
                 "<div style='font-size:10px;opacity:0.6;'>"+str(s['num'])+"</div>"+s['signo']+"</div>")
        sh+="</div>"
        st.markdown(sh,unsafe_allow_html=True)
        top6=sorted(rq['quiniela'],key=lambda x:max(x['p1'],x['pX'],x['p2']),reverse=True)[:6]
        reducida=" · ".join(f"**#{s['num']}** {s['signo']}" for s in sorted(top6,key=lambda x:x['num']))
        st.markdown(f"*Reducida sugerida (0.75€)*: {reducida}")
    with cr2:
        st.markdown("#### 💡 Interpretación")
        if rq['prob_total']>1:    st.success(f"✅ Prob. relativamente alta: {rq['prob_total']}%")
        elif rq['prob_total']>0.1: st.warning(f"⚠️ Prob. moderada: {rq['prob_total']}%")
        else:                      st.error(f"🎲 Prob. baja: {rq['prob_total']}%")
        st.markdown(f"Con **{rq['n_dobles']} dobles** y **{rq['n_triples']} triples** "
                    f"cubres **{rq['coste_multiplicador']} columnas** por **{rq['coste_total']}€**.")
    st.divider()
    ex1,ex2=st.columns(2)
    with ex1:
        df_exp=pd.DataFrame([{'Num':s['num'],'Local':s['local'],'Visitante':s['visitante'],
                               'Prob_1':s['p1'],'Prob_X':s['pX'],'Prob_2':s['p2'],
                               'Seleccion':s['signo'],'Tipo':s['tipo'],
                               'Prob_acierto_%':s['prob_aciertopartido'],
                               'Marcador_exacto':s.get('marcador_sugerido','') if s['num']==15 else '',
                               'Modelo':s['modo']} for s in rq['quiniela']])
        st.download_button("📥 Exportar quiniela CSV",df_exp.to_csv(index=False),
                           file_name=f"quiniela_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                           mime="text/csv",use_container_width=True)
    with ex2:
        if st.button("🔄 Nueva quiniela",use_container_width=True):
            del st.session_state['ultima_quiniela']; st.rerun()


# ============================================================================
# BACKTESTING
# ============================================================================

@st.cache_data(ttl=3600)
def ejecutar_backtesting(_df_total, num_test=200, umbral=0.55):
    if _df_total.empty or len(_df_total)<100: return None
    df_s=_df_total.dropna(subset=['FTHG','FTAG','Date']).sort_values('Date')
    df_t=df_s.tail(num_test); res=[]; pb=st.progress(0)
    for i,(idx,p) in enumerate(df_t.iterrows()):
        pb.progress((i+1)/len(df_t))
        l,v,f=p['HomeTeam'],p['AwayTeam'],p['Date']
        dfa=df_s[df_s['Date']<f]
        if len(dfa)<50: continue
        dl=dfa[(dfa['HomeTeam']==l)|(dfa['AwayTeam']==l)]
        dv=dfa[(dfa['HomeTeam']==v)|(dfa['AwayTeam']==v)]
        if len(dl)<5 or len(dv)<5: continue
        try:
            pron=PronosticadorDixonColes(dfa,dl,dv,l,v,20)
            rr='local' if p['FTHG']>p['FTAG'] else 'visitante' if p['FTHG']<p['FTAG'] else 'empate'
            prb={'local':pron.p_win/100,'empate':pron.p_draw/100,'visitante':pron.p_lose/100}
            pm=max(prb,key=prb.get)
            res.append({'prob':max(prb.values()),'correcto':pm==rr,
                        'over_real':(p['FTHG']+p['FTAG'])>2.5,'prob_over':pron.prob_over_25/100,
                        'ambos_real':p['FTHG']>0 and p['FTAG']>0,'prob_ambos':pron.prob_ambos/100})
        except: continue
    pb.empty()
    if not res: return None
    df_r=pd.DataFrame(res); df_s2=df_r[df_r['prob']>=umbral]
    bins=[0.4,0.5,0.6,0.7,0.8,1.0]; cal=[]
    for i in range(len(bins)-1):
        m=(df_r['prob']>=bins[i])&(df_r['prob']<bins[i+1]); s=df_r[m]
        if len(s)>=5:
            cal.append({'Rango':f"{int(bins[i]*100)}-{int(bins[i+1]*100)}%",'N Partidos':len(s),
                        'Prob Media Pred.':round(s['prob'].mean()*100,1),
                        'Tasa Real':round(s['correcto'].mean()*100,1),
                        'Diferencia':round((s['correcto'].mean()-s['prob'].mean())*100,1)})
    om=df_r['prob_over']>=0.6; am=df_r['prob_ambos']>=0.6
    roi=df_s2['correcto'].apply(lambda x:0.9 if x else -1).mean()*100 if not df_s2.empty else 0
    return {'total_partidos':len(df_r),'accuracy_total':round(df_r['correcto'].mean()*100,1),
            'accuracy_seguro':round(df_s2['correcto'].mean()*100,1) if not df_s2.empty else 0,
            'partidos_seguros':len(df_s2),'calibracion':pd.DataFrame(cal),
            'accuracy_over':round(df_r[om]['over_real'].mean()*100,1) if om.sum()>0 else 0,
            'accuracy_ambos':round(df_r[am]['ambos_real'].mean()*100,1) if am.sum()>0 else 0,
            'roi_simulado':round(roi,1)}

def mostrar_tab_backtesting(df_total):
    st.subheader("🔬 Backtesting y Validación del Modelo")
    st.info("Predice cada partido usando SOLO datos anteriores, simulando condiciones reales.")
    c1,c2,c3=st.columns(3)
    with c1: nt=st.slider("Partidos de test",50,500,200,50)
    with c2: umb=st.slider("Umbral confianza",0.50,0.75,0.55,0.05)
    with c3: run=st.button("▶️ Ejecutar",use_container_width=True)
    if run:
        with st.spinner("Ejecutando..."):
            r=ejecutar_backtesting(df_total,nt,umb)
            if r: st.session_state['backtest_cache']=r; st.success("✅ Completado")
            else: st.error("❌ Datos insuficientes")
    if 'backtest_cache' in st.session_state:
        r=st.session_state['backtest_cache']
        m1,m2,m3,m4=st.columns(4)
        m1.metric("📊 Partidos",r['total_partidos']); m2.metric("🎯 Accuracy",f"{r['accuracy_total']}%")
        m3.metric(f"✅ Acc.≥{int(umb*100)}%",f"{r['accuracy_seguro']}%"); m4.metric("💰 ROI",f"{r['roi_simulado']}%")
        o1,o2,o3=st.columns(3)
        o1.metric("⚽ Acc. Over 2.5",f"{r['accuracy_over']}%"); o2.metric("🥅 Acc. Ambos",f"{r['accuracy_ambos']}%"); o3.metric("🔒 Alta confianza",r['partidos_seguros'])
        if not r['calibracion'].empty: st.subheader("📈 Calibración"); st.dataframe(r['calibracion'],use_container_width=True)
        if r['accuracy_seguro']>55:   st.success(f"✅ Accuracy {r['accuracy_seguro']}% — edge estadístico.")
        elif r['accuracy_seguro']>45: st.warning(f"⚠️ Accuracy {r['accuracy_seguro']}% — mejora ligera.")
        else:                         st.error(f"❌ Accuracy {r['accuracy_seguro']}% — no supera el azar.")
        return r
    return None


# ============================================================================
# CUOTAS EN TIEMPO REAL
# ============================================================================

@st.cache_data(ttl=300)
def obtener_cuotas_tiempo_real(local, visitante, api_key, liga_cod=None):
    if not api_key or not api_key.strip(): return None
    liga_map={'SP1':'soccer_spain_la_liga','SP2':'soccer_spain_segunda_division','E0':'soccer_epl',
              'E1':'soccer_efl_champ','I1':'soccer_italy_serie_a','D1':'soccer_germany_bundesliga',
              'F1':'soccer_france_ligue_one','P1':'soccer_portugal_primeira_liga',
              'N1':'soccer_netherlands_eredivisie','B1':'soccer_belgium_first_div'}
    sport=liga_map.get(liga_cod,'soccer_epl')
    url=f"https://api.the-odds-api.com/v4/sports/{sport}/odds/"
    params={'apiKey':api_key,'regions':'eu','markets':'h2h','oddsFormat':'decimal'}
    try:
        response=requests.get(url,params=params,timeout=10)
        if response.status_code!=200: return None
        cuotas={}
        for ev in response.json():
            home=ev.get('home_team','').lower(); away=ev.get('away_team','').lower()
            if ((local.lower()[:6] in home or home[:6] in local.lower()) and
                    (visitante.lower()[:6] in away or away[:6] in visitante.lower())):
                for bm in ev.get('bookmakers',[]):
                    for mk in bm.get('markets',[]):
                        if mk['key']=='h2h':
                            for oc in mk.get('outcomes',[]):
                                nm=oc['name'].lower(); pr=oc['price']
                                if ev['home_team'].lower() in nm:
                                    if 'local' not in cuotas or pr>cuotas['local']['cuota']:
                                        cuotas['local']={'cuota':pr,'casa':bm['title'],'prob_implícita':round(1/pr*100,1),'tipo':'real'}
                                elif ev['away_team'].lower() in nm:
                                    if 'visitante' not in cuotas or pr>cuotas['visitante']['cuota']:
                                        cuotas['visitante']={'cuota':pr,'casa':bm['title'],'prob_implícita':round(1/pr*100,1),'tipo':'real'}
                                elif 'draw' in nm:
                                    if 'empate' not in cuotas or pr>cuotas['empate']['cuota']:
                                        cuotas['empate']={'cuota':pr,'casa':bm['title'],'prob_implícita':round(1/pr*100,1),'tipo':'real'}
                return cuotas if len(cuotas)>=2 else None
        return None
    except: return None


# ============================================================================
# CARGA Y ACTUALIZACIÓN DE DATOS
# ============================================================================

@st.cache_data(ttl=3600)
def cargar_datos():
    try:
        if not os.path.exists("datos_historicos.csv"): return pd.DataFrame()
        df=pd.read_csv("datos_historicos.csv")
        df['Date']=pd.to_datetime(df['Date'],dayfirst=True,errors='coerce')
        df['HomeTeam']=df['HomeTeam'].str.strip(); df['AwayTeam']=df['AwayTeam'].str.strip()
        return df.dropna(subset=['FTHG','FTAG'])
    except Exception as e:
        st.error(f"Error cargando datos: {e}"); return pd.DataFrame()

def actualizar_csv(pb, st_txt):
    temporadas=['2526','2425']
    ligas=["SP1","SP2","E0","E1","E2","I1","I2","D1","D2","F1","F2","P1","N1","B1","T1","G1",
           "SC0","SC1","SC2","SC3","A1","C1","DK1","SE1","SE2","NO1","NO2","FI1","PO1","CZ1",
           "RU1","UA1","HR1","SR1","BG1","RO1","HU1","SK1","SI1"]
    total=len(temporadas)*len(ligas); cnt=0; lista=[]; errs=[]
    for t in temporadas:
        for cod in ligas:
            cnt+=1; pb.progress(cnt/total); st_txt.text(f"📥 {t}/{cod} ({int(cnt/total*100)}%)")
            url=f"https://www.football-data.co.uk/mmz4281/{t}/{cod}.csv"
            try:
                r=requests.get(url,timeout=10,headers={'User-Agent':'Mozilla/5.0'})
                if r.status_code==200 and len(r.text)>100:
                    df_t=pd.read_csv(StringIO(r.text)); df_t['Temporada']=t; df_t['Liga']=cod
                    cols=['Date','HomeTeam','AwayTeam','FTHG','FTAG','FTR','Div','Temporada','Liga',
                          'HC','AC','HF','AF','HY','AY','HR','AR','B365H','B365D','B365A',
                          'PSH','PSD','PSA','WHH','WHD','WHA','VCH','VCD','VCA','MaxH','MaxD','MaxA','AvgH','AvgD','AvgA']
                    ex=[c for c in cols if c in df_t.columns]
                    if ex: lista.append(df_t[ex])
                else: errs.append(f"{t}/{cod}")
            except Exception as e: errs.append(f"{t}/{cod}: {str(e)[:30]}")
    if lista:
        if os.path.exists("datos_historicos.csv"):
            os.makedirs("backups",exist_ok=True)
            try: os.rename("datos_historicos.csv",f"backups/backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
            except: pass
        df_f=pd.concat(lista,ignore_index=True); df_f.to_csv("datos_historicos.csv",index=False)
        return True,len(df_f),errs
    return False,0,errs

def obtener_historial_h2h(df, local, visitante, limite=8):
    mask=((df['HomeTeam']==local)&(df['AwayTeam']==visitante))|((df['HomeTeam']==visitante)&(df['AwayTeam']==local))
    return df[mask].sort_values('Date',ascending=False).head(limite)


# ============================================================================
# FUNCIONES DE ANÁLISIS
# ============================================================================

def calcular_probabilidades_todos_mercados(p):
    return {
        '1x2':{'local':p.p_win,'empate':p.p_draw,'visitante':p.p_lose},
        'doble_oportunidad':{
            '1X': round(p.p_win+p.p_draw,1),
            'X2': round(p.p_draw+p.p_lose,1),
            '12': round(p.p_win+p.p_lose,1),
        },
        'over_under':{
            'Over 0.5': round((1-poisson.pmf(0,p.media_total))*100,1),
            'Under 0.5':round(poisson.pmf(0,p.media_total)*100,1),
            'Over 1.5': round((1-poisson.cdf(1,p.media_total))*100,1),
            'Under 1.5':round(poisson.cdf(1,p.media_total)*100,1),
            'Over 2.5': round(p.prob_over_25,1),
            'Under 2.5':round(p.prob_under_25,1),
            'Over 3.5': round((1-poisson.cdf(3,p.media_total))*100,1),
            'Under 3.5':round(poisson.cdf(3,p.media_total)*100,1),
        },
        'ambos_marcan':{'Si':p.prob_ambos,'No':100-p.prob_ambos},
    }

def encontrar_mejores_cuotas(df_p):
    if df_p.empty: return None
    row=df_p.iloc[0]
    mp={'local':['B365H','PSH','WHH','VCH','MaxH'],'empate':['B365D','PSD','WHD','VCD','MaxD'],
        'visitante':['B365A','PSA','WHA','VCA','MaxA']}
    cuotas={}
    for m,cols in mp.items():
        bq,bc=0,None
        for c in cols:
            if c in row and pd.notna(row[c]):
                v=float(row[c])
                if v>bq: bq,bc=v,c
        if bq>0: cuotas[m]={'cuota':bq,'casa':bc,'prob_implícita':round(1/bq*100,1),'tipo':'histórico'}
    return cuotas if cuotas else None

def calcular_valor_esperado(prob, cuota):
    return -100 if cuota<=0 or prob<=0 else (prob/100*cuota-1)*100

def recomendar_apuesta_segura(p, cuotas):
    items=[(f'Local: {p.local}',p.p_win,'local',2.0),('Empate',p.p_draw,'empate',3.2),
           (f'Visitante: {p.visitante}',p.p_lose,'visitante',3.0),
           ('Over 2.5',p.prob_over_25,None,2.0),('Under 2.5',p.prob_under_25,None,1.9),
           ('Ambos marcan - SI',p.prob_ambos,None,1.95),('Ambos marcan - NO',100-p.prob_ambos,None,1.85)]
    res=[]
    for nombre,prob,clave,cd in items:
        cuota=(cuotas.get(clave,{}).get('cuota',cd) if (cuotas and clave) else cd)
        seg='ALTA' if prob>65 else 'MEDIA' if prob>50 else 'BAJA'
        tipo='1X2' if clave in ['local','empate','visitante'] else 'Mercado'
        res.append({'nombre':nombre,'tipo':tipo,'probabilidad':prob,'cuota':cuota,'seguridad':seg})
    return sorted(res,key=lambda x:x['probabilidad'],reverse=True)

def calcular_rating_confianza(p, bt=None):
    r=0; n=len(p.df_local)+len(p.df_visitante)
    r+=25 if n>35 else (15 if n>20 else 5)
    mp=max(p.p_win,p.p_draw,p.p_lose)
    r+=25 if mp>60 else (15 if mp>50 else 5)
    r+=15 if abs(p.prob_over_25-p.prob_under_25)>30 else (10 if abs(p.prob_over_25-p.prob_under_25)>15 else 3)
    r+=15 if abs(p.prob_ambos-50)>25 else (10 if abs(p.prob_ambos-50)>10 else 3)
    if hasattr(p,'modo_modelo') and p.modo_modelo=="Dixon-Coles": r+=10
    if bt and bt.get('accuracy_seguro',0)>55: r+=10
    return min(r,100)

def analizar_value_bets(p, cuotas):
    if not cuotas: return None
    res={}
    for m,pr in {'local':p.p_win,'empate':p.p_draw,'visitante':p.p_lose}.items():
        if m in cuotas:
            info=cuotas[m]; val=pr-info['prob_implícita']
            res[m]={'value':val,'es_value':val>5,'cuota':info['cuota'],'casa':info.get('casa',''),
                    'prob_impl':info['prob_implícita'],'prob_real':pr,
                    'valor_esperado':calcular_valor_esperado(pr,info['cuota']),'tipo_cuota':info.get('tipo','histórico')}
    vp=[(k,v['value']) for k,v in res.items() if v['value']>3]
    if vp:
        mk=max(vp,key=lambda x:x[1])
        res['mejor_value']={'mercado':mk[0],'value':mk[1],'cuota':res[mk[0]]['cuota'],'tipo':res[mk[0]]['tipo_cuota']}
    else: res['mejor_value']=None
    return res

def check_alertas(p, cuotas, va, bt=None):
    al=[]
    if va and va.get('mejor_value'):
        v=va['mejor_value']; t="⚡ Tiempo real" if v.get('tipo')=='real' else "📊 Histórica"
        al.append({'tipo':"🔴 VALUE BET FUERTE" if v['value']>10 else "💰 VALUE BET DETECTADO",
                   'mensaje':f"{v['mercado']} +{v['value']:.1f}% ({t})",'clase':'alerta-verde'})
    mp=max(p.p_win,p.p_draw,p.p_lose)
    if mp>70:             al.append({'tipo':'🎯 FAVORITO CLARO','mensaje':f"{mp:.1f}%",'clase':'alerta-amarilla'})
    if p.prob_over_25>75: al.append({'tipo':'⚽ MUCHOS GOLES','mensaje':f"Over 2.5 al {p.prob_over_25:.1f}%",'clase':'alerta-amarilla'})
    if p.prob_ambos>75:   al.append({'tipo':'🥅 AMBOS MARCAN','mensaje':f"{p.prob_ambos:.1f}%",'clase':'alerta-amarilla'})
    if bt and bt.get('accuracy_seguro',0)>60:
        al.append({'tipo':'✅ MODELO VALIDADO','mensaje':f"Accuracy: {bt['accuracy_seguro']:.1f}%",'clase':'alerta-verde'})
    return al

def analizar_ligas(df):
    col='Liga' if 'Liga' in df.columns else ('Div' if 'Div' in df.columns else None)
    if col is None: return pd.DataFrame()
    ld={'SP1':'La Liga','SP2':'La Liga 2','E0':'Premier','E1':'Championship','I1':'Serie A',
        'D1':'Bundesliga','F1':'Ligue 1','P1':'Liga Portugal','N1':'Eredivisie',
        'B1':'Pro League Bélgica','T1':'Süper Lig','G1':'Super League Grecia',
        'SC0':'Premiership Escocia','A1':'Bundesliga Austria'}
    s=[]
    for cod,nombre in ld.items():
        dl=df[df[col]==cod]
        if len(dl)>10:
            s.append({'Liga':nombre,'Partidos':len(dl),
                      'Media Goles':round((dl['FTHG'].mean()+dl['FTAG'].mean())/2,2),
                      'Over 2.5 %':round((dl['FTHG']+dl['FTAG']>2.5).mean()*100,1)})
    return pd.DataFrame(s).sort_values('Over 2.5 %',ascending=False)

def calcular_prob_mitades(df, equipo):
    ld=df[df['HomeTeam']==equipo]; ad=df[df['AwayTeam']==equipo]; total=len(ld)+len(ad)
    if total==0: return None,None
    if 'H1G' in df.columns and 'A1G' in df.columns:
        g1=(ld['H1G'].fillna(0)>0).sum()+(ad['A1G'].fillna(0)>0).sum()
        g2=(ld.get('H2G',pd.Series(dtype=float)).fillna(0)>0).sum()+(ad.get('A2G',pd.Series(dtype=float)).fillna(0)>0).sum()
        return g1/total*100,g2/total*100
    else:
        m=((ld['FTHG'].mean() if not ld.empty else 0)+(ad['FTAG'].mean() if not ad.empty else 0))/2
        return (1-poisson.pmf(0,m*0.45))*100,(1-poisson.pmf(0,m*0.55))*100


# ============================================================================
# MAIN
# ============================================================================

def main():
    if not verificar_acceso():
        return

    if 'favoritos' not in st.session_state:
        st.session_state.favoritos=[]

    st.title("⚽ ASISTENTE DE APUESTAS JR6 - FÚTBOL PROFESIONAL")
    st.caption("Dixon-Coles · Pesos Temporales · Value Bets · Combinada IA · Quiniela · Backtesting")

    df_total=cargar_datos()

    if df_total.empty:
        st.warning("⚠️ No hay datos. Pulsa 'Actualizar Base de Datos' en la barra lateral.")
        with st.sidebar:
            mostrar_info_sesion_sidebar()
            if st.button("🔄 Actualizar Base de Datos",use_container_width=True):
                with st.spinner("Actualizando..."):
                    pb=st.progress(0); st_=st.empty()
                    ok,num,_=actualizar_csv(pb,st_)
                    if ok:
                        st.success(f"✅ {num} registros"); st.cache_data.clear(); time.sleep(1); st.rerun()
        return

    equipos=sorted(set(df_total['HomeTeam'].unique())|set(df_total['AwayTeam'].unique()))

    # ── SIDEBAR ──────────────────────────────────────────────────────────
    with st.sidebar:
        mostrar_info_sesion_sidebar()
        st.header("⚙️ CONFIGURACIÓN")
        num_partidos=st.slider("📊 Partidos a analizar",5,50,10,5)
        factor_decay=st.slider("⏳ Decaimiento temporal",0.001,0.010,0.003,0.001,
                                help="Mayor = más peso a partidos recientes")
        st.divider()
        st.subheader("🔑 APIs")
        api_key_odds     =st.text_input("The Odds API Key", value="",type="password",help="theoddsapi.com (500 req/mes gratis)")
        api_key_anthropic=st.text_input("Anthropic API Key",value="",type="password",help="Para análisis IA en combinadas")
        if api_key_odds:      st.success("⚡ Odds API configurada")
        if api_key_anthropic: st.success("🤖 Claude API configurada")
        st.divider()
        st.header("⭐ FAVORITOS")
        nuevo=st.selectbox("Añadir favorito",equipos,key='nuevo_fav')
        if st.button("➕ Añadir",use_container_width=True):
            if nuevo not in st.session_state.favoritos:
                st.session_state.favoritos.append(nuevo); st.success(f"✅ {nuevo} añadido")
        for fav in st.session_state.favoritos:
            c1,c2=st.columns([3,1]); c1.write(f"• {fav}")
            if c2.button("❌",key=f"del_{fav}"):
                st.session_state.favoritos.remove(fav); st.rerun()
        st.divider()
        st.header("📊 LIGAS")
        df_ligas=analizar_ligas(df_total)
        if not df_ligas.empty: st.dataframe(df_ligas,use_container_width=True,height=200)
        st.divider()
        mostrar_panel_cache_sidebar()
        mostrar_panel_cambio_password()
        st.divider()
        if st.button("🔄 Actualizar Base de Datos",use_container_width=True):
            with st.spinner("Actualizando..."):
                pb=st.progress(0); st_=st.empty()
                ok,num,_=actualizar_csv(pb,st_)
                if ok:
                    st.success(f"✅ {num} registros"); st.cache_data.clear(); time.sleep(1); st.rerun()
        st.caption(f"📱 {'Móvil' if ES_MOVIL else 'Escritorio'} · {datetime.now().strftime('%d/%m/%Y %H:%M')}")

    # ── TABS ──────────────────────────────────────────────────────────────
    tab_p,tab_c,tab_q,tab_b=st.tabs([
        "⚽ Pronóstico Individual","🤖 Combinada IA","🎯 Quiniela","🔬 Backtesting & Validación",
    ])

    with tab_b: backtest_res=mostrar_tab_backtesting(df_total)
    with tab_c: mostrar_tab_combinada(df_total,num_partidos,factor_decay,api_key_anthropic)
    with tab_q: mostrar_tab_quiniela(df_total,num_partidos,factor_decay)

    # ── PRONÓSTICO INDIVIDUAL ─────────────────────────────────────────────
    with tab_p:
        if st.session_state.favoritos and st.checkbox("⭐ Solo favoritos"):
            disp=st.session_state.favoritos
        else:
            disp=equipos

        c1,c2=st.columns(2)
        with c1: local    =st.selectbox("🏠 Local",    disp,index=0)
        with c2: visitante=st.selectbox("🚀 Visitante",disp,index=min(1,len(disp)-1))

        dl=df_total[(df_total['HomeTeam']==local)     | (df_total['AwayTeam']==local)]
        dv=df_total[(df_total['HomeTeam']==visitante) | (df_total['AwayTeam']==visitante)]
        if dl.empty or dv.empty:
            st.error("❌ Datos insuficientes"); return

        # Alerta divergencia temporadas
        alertas_div=check_alerta_divergencia(df_total,local,visitante,num_partidos)
        for ad in alertas_div:
            st.markdown(
                f"<div class='alerta-card alerta-azul'>"
                f"<span style='font-size:18px;'>⚠️ ALERTA TEMPORADA — {ad['equipo']}</span><br>"
                f"El <b>{ad['pct_anterior']:.0f}%</b> de los datos son de la temporada anterior "
                f"({ad['n_anterior']} partidos 24/25 vs {ad['n_actual']} partidos 25/26).</div>",
                unsafe_allow_html=True
            )

        # Caché de pronósticos
        datos_cacheados=get_pronostico_cacheado(local,visitante,num_partidos,factor_decay)
        if datos_cacheados:
            pron=datos_cacheados['pron_obj']; st.caption("🗂️ *Pronóstico cargado desde caché*")
        else:
            pron=PronosticadorDixonColes(df_total,dl,dv,local,visitante,num_partidos,factor_decay)
            guardar_pronostico_cache(local,visitante,num_partidos,factor_decay,{'pron_obj':pron})

        mc_="#2ecc71" if pron.modo_modelo=="Dixon-Coles" else "#f1c40f"
        st.markdown(f"<small>🤖 <b style='color:{mc_};'>{pron.modo_modelo}</b> | "
                    f"λL:<b>{pron.media_local:.2f}</b> | λV:<b>{pron.media_visitante:.2f}</b></small>",
                    unsafe_allow_html=True)

        cuotas_disp=None
        if api_key_odds:
            with st.spinner("⚡ Cuotas tiempo real..."):
                cuotas_disp=obtener_cuotas_tiempo_real(local,visitante,api_key_odds,getattr(pron,'liga_detectada',None))
            if cuotas_disp: st.success("⚡ Cuotas en tiempo real")
            else:           st.info("No encontrado en tiempo real, usando cuotas históricas")
        if not cuotas_disp:
            h2h_q=obtener_historial_h2h(df_total,local,visitante,1)
            cuotas_disp=encontrar_mejores_cuotas(h2h_q) if not h2h_q.empty else None

        mercados =calcular_probabilidades_todos_mercados(pron)
        aps      =recomendar_apuesta_segura(pron,cuotas_disp)
        bt_res   =st.session_state.get('backtest_cache',None)
        rating   =calcular_rating_confianza(pron,bt_res)
        va       =analizar_value_bets(pron,cuotas_disp)
        alertas  =check_alertas(pron,cuotas_disp,va,bt_res)
        p1l,p2l  =calcular_prob_mitades(df_total,local)
        p1v,p2v  =calcular_prob_mitades(df_total,visitante)

        if alertas:
            st.divider(); st.subheader("🚨 ALERTAS")
            for a in alertas:
                st.markdown(f"<div class='alerta-card {a.get('clase','alerta-amarilla')}'>"
                            f"<span style='font-size:20px;'>{a['tipo']}</span><br>{a['mensaje']}</div>",
                            unsafe_allow_html=True)

        st.divider()
        cols=st.columns(4)
        with cols[0]:
            st.subheader("🎯 Marcador")
            gl,gv,pm=pron.get_marcador_sugerido()
            st.markdown(f"<h1 style='color:#FF4B4B;text-align:center;'>{int(gl)} - {int(gv)}</h1>",unsafe_allow_html=True)
            st.caption(f"Prob: {pm:.1f}%")
        with cols[1]:
            st.subheader("📊 1X2")
            st.metric(f"1 {local[:10]}",   f"{pron.p_win:.1f}%")
            st.metric("X Empate",           f"{pron.p_draw:.1f}%")
            st.metric(f"2 {visitante[:10]}",f"{pron.p_lose:.1f}%")
        with cols[2]:
            st.subheader("⚽ Goles")
            co="green-big" if pron.prob_over_25>70 else "big-font"
            st.markdown(f"<p class='{co}'>Over 2.5: {pron.prob_over_25:.1f}%</p>",unsafe_allow_html=True)
            st.markdown(f"<p class='big-font'>Under 2.5: {pron.prob_under_25:.1f}%</p>",unsafe_allow_html=True)
        with cols[3]:
            st.subheader("🥅 Ambos")
            ca="green-big" if pron.prob_ambos>65 else "big-font"
            st.markdown(f"<p class='{ca}'>Sí: {pron.prob_ambos:.1f}%</p>",unsafe_allow_html=True)
            st.markdown(f"<p class='big-font'>No: {100-pron.prob_ambos:.1f}%</p>",unsafe_allow_html=True)

        r1,r2,r3=st.columns(3)
        with r1:
            st.metric("📊 Confianza",f"{rating}%")
            if rating>70:   st.success("ALTA")
            elif rating>50: st.warning("MEDIA")
            else:           st.error("BAJA")
        with r2:
            if cuotas_disp and 'local' in cuotas_disp:
                ic="⚡" if cuotas_disp['local'].get('tipo')=='real' else "📊"
                st.metric(f"{ic} Mejor Local",f"{cuotas_disp['local']['cuota']:.2f}"); st.caption(cuotas_disp['local']['casa'])
            else: st.metric("💰 Local","No disponible")
        with r3:
            if cuotas_disp and 'visitante' in cuotas_disp:
                ic="⚡" if cuotas_disp['visitante'].get('tipo')=='real' else "📊"
                st.metric(f"{ic} Mejor Visitante",f"{cuotas_disp['visitante']['cuota']:.2f}"); st.caption(cuotas_disp['visitante']['casa'])
            else: st.metric("💰 Visitante","No disponible")

        if va and va.get('mejor_value'):
            st.divider(); v=va['mejor_value']['value']
            t="⚡ Tiempo real" if va['mejor_value'].get('tipo')=='real' else "📊 Histórica"
            cls='value-alta' if v>10 else 'value-media'; lbl="🔥 VALUE FUERTE" if v>10 else "💰 VALUE DETECTADO"
            if v>5:
                st.markdown(f"<div class='{cls}'>{lbl} ({t})<br>"
                            f"Apuesta: <b>{va['mejor_value']['mercado']}</b><br>"
                            f"Cuota: {va['mejor_value']['cuota']:.2f} | Ventaja: +{v:.1f}%</div>",unsafe_allow_html=True)

        st.divider(); st.subheader("🎯 TOP 5 APUESTAS SUGERIDAS")
        for i,ap in enumerate(aps[:5]):
            cc="#2ecc71" if ap['seguridad']=='ALTA' else "#f1c40f" if ap['seguridad']=='MEDIA' else "#e74c3c"
            em="🟢" if ap['seguridad']=='ALTA' else "🟡" if ap['seguridad']=='MEDIA' else "🔴"
            ve=calcular_valor_esperado(ap['probabilidad'],ap['cuota'])
            a1,a2,a3,a4=st.columns([3,1,1,1])
            a1.markdown(f"**{i+1}. {ap['nombre']}**"); a1.caption(ap['tipo'])
            a2.markdown(f"<p style='color:{cc};font-weight:bold;font-size:20px;'>{ap['probabilidad']:.1f}%</p>",unsafe_allow_html=True)
            a3.markdown(f"<p style='font-size:20px;'>{em}</p>",unsafe_allow_html=True)
            if ve>5:    a4.markdown(f"<p style='color:#2ecc71;font-weight:bold;'>EV:+{ve:.1f}%</p>",unsafe_allow_html=True)
            elif ve<-5: a4.markdown(f"<p style='color:#e74c3c;'>EV:{ve:.1f}%</p>",unsafe_allow_html=True)
            else:       a4.markdown(f"EV:{ve:.1f}%")

        st.divider(); st.subheader("📈 Estadísticas Previstas")
        e1,e2,e3=st.columns(3)
        e1.metric("🎯 Corners", f"{pron.corners_total:.1f}")
        e2.metric("🟨 Tarjetas",f"{pron.tarjetas_total:.1f}")
        e3.metric("⚖️ Faltas",  f"{pron.faltas_total:.1f}")

        st.write("---"); st.subheader("🕐 Probabilidad por partes")
        pp1,pp2=st.columns(2)
        for cp,eq,p1,p2 in [(pp1,local,p1l,p2l),(pp2,visitante,p1v,p2v)]:
            with cp:
                st.markdown(f"**{eq}**")
                if p1 is not None: st.metric("1ª Parte",f"{p1:.1f}%"); st.metric("2ª Parte",f"{p2:.1f}%")
                else: st.info("Sin datos")

        # ── ANÁLISIS POR MERCADOS (con Doble Oportunidad) ─────────────────
        st.divider(); st.subheader("📊 ANÁLISIS POR MERCADOS")
        t1,t2,t3,t4=st.tabs(["1X2","Doble Oportunidad","Over/Under","Ambos Marcan"])

        with t1:
            x1,x2,x3=st.columns(3)
            for cx,lb,pr in [(x1,f"🏠 {local}",mercados['1x2']['local']),
                              (x2,"🤝 Empate",mercados['1x2']['empate']),
                              (x3,f"🚀 {visitante}",mercados['1x2']['visitante'])]:
                cx.markdown(f"**{lb}**"); cx.markdown(f"<p class='big-font'>{pr:.1f}%</p>",unsafe_allow_html=True)

        with t2:
            st.markdown("Probabilidad de que el resultado sea **cualquiera de los dos** marcadores seleccionados.")
            d1,d2,d3=st.columns(3)
            do=mercados['doble_oportunidad']
            # 1X
            with d1:
                prob_1X=do['1X']
                color_1X="green-big" if prob_1X>70 else "big-font"
                st.markdown(f"**🏠 1X** *(Local o Empate)*")
                st.markdown(f"<p class='{color_1X}'>{prob_1X}%</p>",unsafe_allow_html=True)
                st.caption(f"Local gana {pron.p_win:.1f}% + Empate {pron.p_draw:.1f}%")
            # X2
            with d2:
                prob_X2=do['X2']
                color_X2="green-big" if prob_X2>70 else "big-font"
                st.markdown(f"**🚀 X2** *(Empate o Visitante)*")
                st.markdown(f"<p class='{color_X2}'>{prob_X2}%</p>",unsafe_allow_html=True)
                st.caption(f"Empate {pron.p_draw:.1f}% + Visitante {pron.p_lose:.1f}%")
            # 12
            with d3:
                prob_12=do['12']
                color_12="green-big" if prob_12>70 else "big-font"
                st.markdown(f"**⚡ 12** *(Local o Visitante)*")
                st.markdown(f"<p class='{color_12}'>{prob_12}%</p>",unsafe_allow_html=True)
                st.caption(f"Local {pron.p_win:.1f}% + Visitante {pron.p_lose:.1f}%")

        with t3:
            ou=mercados['over_under']
            ois=sorted([(k,v) for k,v in ou.items() if k.startswith('Over')], key=lambda x:float(x[0].split()[1]))
            uis=sorted([(k,v) for k,v in ou.items() if k.startswith('Under')],key=lambda x:float(x[0].split()[1]))
            co_,cu_=st.columns(2)
            with co_:
                st.markdown("**Over**")
                for n_,p_ in ois:
                    col_="#2ecc71" if p_>65 else "#e74c3c" if p_<35 else "inherit"
                    st.markdown(f"<span style='color:{col_};'>{n_}: **{p_:.1f}%**</span>",unsafe_allow_html=True)
            with cu_:
                st.markdown("**Under**")
                for n_,p_ in uis:
                    col_="#2ecc71" if p_>65 else "#e74c3c" if p_<35 else "inherit"
                    st.markdown(f"<span style='color:{col_};'>{n_}: **{p_:.1f}%**</span>",unsafe_allow_html=True)

        with t4:
            b1,b2=st.columns(2)
            b1.markdown("**✅ SI**"); b1.markdown(f"<p class='big-font'>{mercados['ambos_marcan']['Si']:.1f}%</p>",unsafe_allow_html=True)
            b2.markdown("**❌ NO**"); b2.markdown(f"<p class='big-font'>{mercados['ambos_marcan']['No']:.1f}%</p>",unsafe_allow_html=True)

        st.divider(); st.subheader("🎯 Probabilidad de anotar (≥1 gol)")
        g1_,g2_,g3_=st.columns([2,2,1])
        with g1_:
            st.markdown(f"**{local}**")
            cls='green-big' if pron.prob_local_1>75 else 'big-font'
            st.markdown(f"<p class='{cls}'>{pron.prob_local_1:.1f}%</p>",unsafe_allow_html=True)
        with g2_:
            st.markdown(f"**{visitante}**")
            cls='green-big' if pron.prob_visitante_1>75 else 'big-font'
            st.markdown(f"<p class='{cls}'>{pron.prob_visitante_1:.1f}%</p>",unsafe_allow_html=True)
        with g3_:
            fi,cf,tip=pron.get_fiabilidad()
            st.markdown("**Fiabilidad**")
            st.markdown(f"<p style='color:{cf};font-weight:bold;'>{fi}</p>",unsafe_allow_html=True)
            st.caption(tip)

        st.divider(); st.subheader("🔙 Historial Directo")
        h2h=obtener_historial_h2h(df_total,local,visitante)
        if not h2h.empty:
            wl=((h2h['HomeTeam']==local)&(h2h['FTHG']>h2h['FTAG'])|(h2h['AwayTeam']==local)&(h2h['FTAG']>h2h['FTHG'])).sum()
            em=(h2h['FTHG']==h2h['FTAG']).sum(); wv=len(h2h)-wl-em
            hc1,hc2,hc3=st.columns(3)
            hc1.metric(f"✅ {local[:12]}",wl); hc2.metric("🤝 Empates",em); hc3.metric(f"✅ {visitante[:12]}",wv)
            for _,rw in h2h.iterrows():
                fe=rw['Date'].strftime('%d/%m/%Y') if pd.notna(rw['Date']) else '?'
                gl,gv=int(rw['FTHG']),int(rw['FTAG'])
                rs="🤝" if gl==gv else ("🏠" if (rw['HomeTeam']==local and gl>gv) or (rw['AwayTeam']==local and gv>gl) else "🚀")
                co=int(rw.get('HC',0)+rw.get('AC',0)); ta=int(rw.get('HY',0)+rw.get('AY',0)+rw.get('HR',0)+rw.get('AR',0))
                cu=""
                for cs in ['B365','PS','WH']:
                    if f'{cs}H' in rw and pd.notna(rw.get(f'{cs}H')):
                        cu=f" | {cs}: {rw[f'{cs}H']:.2f}"; break
                st.markdown(f"📅 {fe} {rs} | **{rw['HomeTeam']} {gl}-{gv} {rw['AwayTeam']}** | 🎯 {co} | 🟨 {ta}{cu}")
        else:
            st.info("Sin historial entre estos equipos")

        st.divider()
        ex1,ex2=st.columns(2)
        with ex1:
            data={'Fecha':datetime.now().strftime('%Y-%m-%d %H:%M'),'Local':local,'Visitante':visitante,
                  'Modelo':pron.modo_modelo,'lambda_Local':round(pron.media_local,3),
                  'lambda_Visitante':round(pron.media_visitante,3),'Prob_Local_%':round(pron.p_win,1),
                  'Prob_Empate_%':round(pron.p_draw,1),'Prob_Visitante_%':round(pron.p_lose,1),
                  'Over_2.5_%':round(pron.prob_over_25,1),'Ambos_Marcan_%':round(pron.prob_ambos,1),
                  'Rating':rating,'Backtest_Acc':bt_res.get('accuracy_seguro','N/A') if bt_res else 'N/A'}
            st.download_button("📥 Exportar CSV",pd.DataFrame([data]).to_csv(index=False),
                               file_name=f"pronostico_{local}_vs_{visitante}.csv",
                               mime="text/csv",use_container_width=True)
        with ex2:
            if st.button("🔄 Nuevo Pronóstico",use_container_width=True): st.rerun()


if __name__=="__main__":
    main()