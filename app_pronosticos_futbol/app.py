import streamlit as st
import pandas as pd
import numpy as np
from scipy.stats import poisson
import requests
import os
from datetime import datetime
import time
from io import StringIO
import itertools
import json
import warnings
warnings.filterwarnings('ignore')

# ============================================================================
# CONFIGURACIÓN INICIAL
# ============================================================================

def detectar_movil():
    try:
        user_agent = st.query_params.get("user_agent", [""])
        mobile_keywords = ['mobile', 'android', 'iphone', 'ipad']
        return any(keyword in str(user_agent).lower() for keyword in mobile_keywords)
    except:
        return False

ES_MOVIL = detectar_movil()

st.set_page_config(
    page_title="⚽ Asistente de Apuestas JR6 - Fútbol Profesional",
    page_icon="⚽",
    layout="centered" if ES_MOVIL else "wide",
    initial_sidebar_state="collapsed" if ES_MOVIL else "expanded"
)

st.markdown("""
<style>
    .big-font { font-size:26px !important; font-weight: bold; }
    .green-big { color: #2ecc71; font-size:26px !important; font-weight: bold; }
    .red-big   { color: #e74c3c; font-size:26px !important; font-weight: bold; }
    .yellow-big{ color: #f1c40f; font-size:26px !important; font-weight: bold; }
    .info-box  { padding: 1rem; border-radius: 0.5rem; background-color: #f0f2f6; }
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
    .alerta-verde   { border-left-color: #2e7d32; background-color: #e8f5e9; color: #1b5e20; }
    .alerta-amarilla{ border-left-color: #ff8f00; background-color: #fff8e1; color: #e65100; }

    /* Combinada cards */
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
    .combo-riesgo-bajo  { color: #2ecc71; font-weight: bold; }
    .combo-riesgo-medio { color: #f1c40f; font-weight: bold; }
    .combo-riesgo-alto  { color: #e74c3c; font-weight: bold; }

    .ia-explicacion {
        background: linear-gradient(135deg, #0d1b2a, #1b263b);
        border: 1px solid #415a77; border-radius: 12px;
        padding: 20px; color: #e0e0e0; margin-top: 15px;
        line-height: 1.7;
    }
    .ia-badge {
        background: #e94560; color: white; border-radius: 20px;
        padding: 3px 12px; font-size: 12px; font-weight: bold;
        display: inline-block; margin-bottom: 10px;
    }

    @media (max-width: 768px) {
        .stButton button { min-height: 50px; font-size: 18px; }
        .stSelectbox div[data-baseweb="select"] { min-height: 50px; }
    }
</style>
""", unsafe_allow_html=True)


# ============================================================================
# PESOS TEMPORALES Y FORTALEZAS (DIXON-COLES SIMPLIFICADO)
# ============================================================================

def calcular_pesos_temporales(fechas, factor_decaimiento=0.003):
    if fechas.empty:
        return np.array([])
    fecha_max = fechas.max()
    dias_diff = (fecha_max - fechas).dt.days
    pesos = np.exp(-factor_decaimiento * dias_diff)
    return pesos / pesos.sum()


def calcular_fortalezas_liga(df_liga, min_partidos=5):
    if df_liga.empty or len(df_liga) < 10:
        return {}, {}, {}, {}, 1.5, 1.2

    media_goles_local = df_liga['FTHG'].mean()
    media_goles_visit = df_liga['FTAG'].mean()
    if media_goles_local == 0 or media_goles_visit == 0:
        return {}, {}, {}, {}, 1.5, 1.2

    equipos = set(df_liga['HomeTeam'].unique()) | set(df_liga['AwayTeam'].unique())
    attack_h, defence_h, attack_a, defence_a = {}, {}, {}, {}

    for eq in equipos:
        home_data = df_liga[df_liga['HomeTeam'] == eq]
        if len(home_data) >= min_partidos:
            attack_h[eq]  = home_data['FTHG'].mean() / media_goles_local
            defence_h[eq] = home_data['FTAG'].mean() / media_goles_visit
        away_data = df_liga[df_liga['AwayTeam'] == eq]
        if len(away_data) >= min_partidos:
            attack_a[eq]  = away_data['FTAG'].mean() / media_goles_visit
            defence_a[eq] = away_data['FTHG'].mean() / media_goles_local

    return attack_h, defence_h, attack_a, defence_a, media_goles_local, media_goles_visit


# ============================================================================
# MODELO DIXON-COLES CON PESOS TEMPORALES
# ============================================================================

class PronosticadorDixonColes:
    def __init__(self, df_total, df_local, df_visitante, local, visitante,
                 num_partidos=20, factor_decaimiento=0.003):
        self.df_total       = df_total
        self.local          = local
        self.visitante      = visitante
        self.num_partidos   = num_partidos
        self.factor_decaimiento = factor_decaimiento
        self.df_local       = df_local.tail(num_partidos * 2)
        self.df_visitante   = df_visitante.tail(num_partidos * 2)

        self._calcular_fortalezas_liga()
        self._calcular_medias_ponderadas()
        self._calcular_todo()

    def _calcular_fortalezas_liga(self):
        col_liga = 'Liga' if 'Liga' in self.df_total.columns else (
            'Div' if 'Div' in self.df_total.columns else None)

        self.attack_h, self.defence_h = {}, {}
        self.attack_a, self.defence_a = {}, {}
        self.media_liga_local = 1.5
        self.media_liga_visit = 1.2
        self.liga_detectada   = None

        if col_liga is None:
            return

        data_eq = self.df_total[self.df_total['HomeTeam'] == self.local]
        if not data_eq.empty:
            ligas_eq = data_eq[col_liga].value_counts()
            if not ligas_eq.empty:
                self.liga_detectada = ligas_eq.index[0]
                df_liga = self.df_total[self.df_total[col_liga] == self.liga_detectada].copy()
                att_h, def_h, att_a, def_a, med_l, med_v = calcular_fortalezas_liga(df_liga)
                self.attack_h, self.defence_h = att_h, def_h
                self.attack_a, self.defence_a = att_a, def_a
                self.media_liga_local, self.media_liga_visit = med_l, med_v

    def _calcular_media_ponderada_goles(self, df, equipo, condicion):
        if condicion == 'local':
            mask = df['HomeTeam'] == equipo
            sub  = df[mask].copy()
            goles = sub['FTHG']
        else:
            mask = df['AwayTeam'] == equipo
            sub  = df[mask].copy()
            goles = sub['FTAG']

        if goles.empty:
            return 0.0

        goles_clean = goles[goles <= 5]
        sub_clean   = sub[goles <= 5]

        if goles_clean.empty:
            return goles.mean()

        if 'Date' in sub_clean.columns and not sub_clean['Date'].isna().all():
            pesos = calcular_pesos_temporales(sub_clean['Date'], self.factor_decaimiento)
            if len(pesos) == len(goles_clean):
                return np.average(goles_clean.values, weights=pesos)

        return goles_clean.mean()

    def _calcular_medias_ponderadas(self):
        media_local_raw = self._calcular_media_ponderada_goles(self.df_local, self.local, 'local')
        media_visit_raw = self._calcular_media_ponderada_goles(self.df_visitante, self.visitante, 'visitante')

        if (self.attack_h and self.defence_a
                and self.local in self.attack_h
                and self.visitante in self.defence_a):
            self.media_local     = (self.media_liga_local *
                                    self.attack_h.get(self.local, 1.0) *
                                    self.defence_a.get(self.visitante, 1.0))
            self.media_visitante = (self.media_liga_visit *
                                    self.attack_a.get(self.visitante, 1.0) *
                                    self.defence_h.get(self.local, 1.0))
            self.modo_modelo = "Dixon-Coles"
        else:
            self.media_local     = media_local_raw if media_local_raw > 0 else 1.2
            self.media_visitante = media_visit_raw if media_visit_raw > 0 else 1.0
            self.modo_modelo = "Poisson Ponderado"

        self.media_local     = max(0.3, min(4.0, self.media_local))
        self.media_visitante = max(0.3, min(4.0, self.media_visitante))
        self.media_total     = self.media_local + self.media_visitante

    def _calcular_todo(self):
        self.prob_local_1    = (1 - poisson.pmf(0, self.media_local))     * 100
        self.prob_visitante_1= (1 - poisson.pmf(0, self.media_visitante)) * 100
        self.prob_ambos      = (self.prob_local_1/100 * self.prob_visitante_1/100) * 100
        self.prob_over_25    = (1 - poisson.cdf(2, self.media_total)) * 100
        self.prob_under_25   = poisson.cdf(2, self.media_total) * 100
        self.matriz, self.p_win, self.p_draw, self.p_lose = self._calcular_matriz()
        self.corners_total   = self._calcular_media_estadistica('HC', 'AC')
        self.tarjetas_total  = self._calcular_media_estadistica(['HY','HR'], ['AY','AR'])
        self.faltas_total    = self._calcular_media_estadistica('HF', 'AF')

    def _calcular_media_estadistica(self, col_local, col_visitante):
        total = 0
        for df, cols in [(self.df_local, col_local), (self.df_visitante, col_visitante)]:
            if isinstance(cols, list):
                for c in cols:
                    if c in df.columns:
                        total += df[c].mean() if not df[c].isna().all() else 0
            else:
                if cols in df.columns:
                    total += df[cols].mean() if not df[cols].isna().all() else 0
        return max(0, total)

    def _calcular_matriz(self):
        p_local    = [poisson.pmf(i, self.media_local)     for i in range(8)]
        p_visitante= [poisson.pmf(i, self.media_visitante) for i in range(8)]
        matriz  = np.outer(p_local, p_visitante)
        p_win   = np.sum(np.tril(matriz, -1))
        p_draw  = np.diag(matriz).sum()
        p_lose  = np.sum(np.triu(matriz, 1))
        return matriz, p_win*100, p_draw*100, p_lose*100

    def get_fiabilidad(self):
        muestras = len(self.df_local) + len(self.df_visitante)
        if muestras > 35: return "ALTA",  "#2ecc71", "✅ Muestra muy representativa"
        elif muestras > 20: return "MEDIA","#f1c40f", "⚠️ Muestra aceptable"
        else: return "BAJA", "#e74c3c", "❌ Pocos datos, usar con precaución"

    def get_marcador_sugerido(self):
        idx_max  = np.unravel_index(np.argmax(self.matriz), self.matriz.shape)
        prob_max = self.matriz[idx_max] * 100
        return idx_max[0], idx_max[1], prob_max


# ============================================================================
# MÓDULO DE APUESTA COMBINADA CON IA
# ============================================================================

def analizar_partido_para_combinada(df_total, local, visitante, num_partidos=20, factor_decay=0.003):
    """Analiza un partido y devuelve sus métricas principales para la combinada."""
    d_local = df_total[(df_total['HomeTeam'] == local) | (df_total['AwayTeam'] == local)]
    d_visit = df_total[(df_total['HomeTeam'] == visitante) | (df_total['AwayTeam'] == visitante)]

    if d_local.empty or d_visit.empty:
        return None

    try:
        pron = PronosticadorDixonColes(df_total, d_local, d_visit, local, visitante,
                                       num_partidos, factor_decay)
        # Mejor opción del partido
        opciones = [
            {'mercado': f'Local ({local})', 'prob': pron.p_win,      'tipo': '1X2',    'cuota_est': max(1.3, 100/max(pron.p_win,1))},
            {'mercado': 'Empate',            'prob': pron.p_draw,     'tipo': '1X2',    'cuota_est': max(1.3, 100/max(pron.p_draw,1))},
            {'mercado': f'Visitante ({visitante})', 'prob': pron.p_lose, 'tipo': '1X2', 'cuota_est': max(1.3, 100/max(pron.p_lose,1))},
            {'mercado': 'Over 1.5',  'prob': (1 - poisson.cdf(1, pron.media_total))*100, 'tipo':'Goles', 'cuota_est': 1.55},
            {'mercado': 'Under 1.5', 'prob': poisson.cdf(1, pron.media_total)*100,        'tipo':'Goles', 'cuota_est': 2.40},
            {'mercado': 'Over 2.5',          'prob': pron.prob_over_25,'tipo': 'Goles', 'cuota_est': 2.0},
            {'mercado': 'Under 2.5',         'prob': pron.prob_under_25,'tipo':'Goles', 'cuota_est': 1.9},
            {'mercado': 'Ambos Marcan - SI', 'prob': pron.prob_ambos,  'tipo': 'BTTS',  'cuota_est': 1.95},
            {'mercado': 'Ambos Marcan - NO', 'prob': 100-pron.prob_ambos,'tipo':'BTTS', 'cuota_est': 1.85},
        ]
        mejor = max(opciones, key=lambda x: x['prob'])

        return {
            'local':       local,
            'visitante':   visitante,
            'p_win':       round(pron.p_win, 1),
            'p_draw':      round(pron.p_draw, 1),
            'p_lose':      round(pron.p_lose, 1),
            'prob_over25': round(pron.prob_over_25, 1),
            'prob_ambos':  round(pron.prob_ambos, 1),
            'media_local': round(pron.media_local, 2),
            'media_visit': round(pron.media_visitante, 2),
            'modo':        pron.modo_modelo,
            'mejor_opcion': mejor,
            'todas_opciones': sorted(opciones, key=lambda x: x['prob'], reverse=True)
        }
    except Exception as e:
        return None


def calcular_mejor_combinada(partidos_analizados, min_partidos=2, max_partidos=4,
                               prob_min_individual=0.52, prob_conjunta_min=0.12):
    """
    Busca la combinación óptima de entre min_partidos y max_partidos selecciones.
    Optimiza el EV = prob_conjunta * cuota_conjunta − 1
    """
    if not partidos_analizados:
        return None

    candidatos = []
    for p in partidos_analizados:
        for op in p['todas_opciones']:
            if op['prob'] / 100 >= prob_min_individual:
                candidatos.append({
                    'partido_label': f"{p['local']} vs {p['visitante']}",
                    'local':         p['local'],
                    'visitante':     p['visitante'],
                    'mercado':       op['mercado'],
                    'prob':          op['prob'] / 100,
                    'cuota_est':     op['cuota_est'],
                    'tipo':          op['tipo'],
                    'modo':          p['modo'],
                })

    # Asegurar 1 selección por partido
    partidos_ya_vistos = set()
    candidatos_filtrados = []
    for c in sorted(candidatos, key=lambda x: x['prob'], reverse=True):
        clave = c['partido_label']
        if clave not in partidos_ya_vistos:
            candidatos_filtrados.append(c)
            partidos_ya_vistos.add(clave)

    if len(candidatos_filtrados) < min_partidos:
        return None

    mejor_combo = None
    mejor_ev    = -999

    for n in range(min_partidos, min(max_partidos + 1, len(candidatos_filtrados) + 1)):
        for combo in itertools.combinations(candidatos_filtrados, n):
            prob_conjunta = 1.0
            cuota_conjunta= 1.0
            for sel in combo:
                prob_conjunta  *= sel['prob']
                cuota_conjunta *= sel['cuota_est']

            if prob_conjunta < prob_conjunta_min:
                continue

            ev = prob_conjunta * cuota_conjunta - 1

            if ev > mejor_ev:
                mejor_ev    = ev
                mejor_combo = {
                    'selecciones':    list(combo),
                    'prob_conjunta':  round(prob_conjunta * 100, 2),
                    'cuota_conjunta': round(cuota_conjunta, 2),
                    'ev_pct':         round(ev * 100, 2),
                    'n':              n,
                }

    return mejor_combo


def calcular_nivel_riesgo(prob_conjunta, n_partidos):
    if prob_conjunta >= 40:   return "BAJO",   "combo-riesgo-bajo",  "🟢"
    elif prob_conjunta >= 22: return "MEDIO",  "combo-riesgo-medio", "🟡"
    else:                     return "ALTO",   "combo-riesgo-alto",  "🔴"


def llamar_ia_combinada(partidos_analizados, mejor_combo, api_key_anthropic=""):
    """
    Llama a Claude vía API para generar una explicación experta de la combinada.
    Si no hay API key, devuelve análisis local de calidad.
    """
    resumen_partidos = []
    for p in partidos_analizados:
        resumen_partidos.append(
            f"- {p['local']} vs {p['visitante']}: "
            f"prob_local={p['p_win']}%, empate={p['p_draw']}%, visitante={p['p_lose']}%, "
            f"over2.5={p['prob_over25']}%, ambos_marcan={p['prob_ambos']}%"
        )

    resumen_combo = []
    for sel in mejor_combo['selecciones']:
        resumen_combo.append(
            f"- {sel['partido_label']}: {sel['mercado']} "
            f"(prob {sel['prob']*100:.1f}%, cuota est. {sel['cuota_est']:.2f})"
        )

    prompt = f"""Eres un analista experto en apuestas deportivas de fútbol con 15 años de experiencia.
Se han analizado los siguientes partidos con un modelo Dixon-Coles + Poisson ponderado:

PARTIDOS ANALIZADOS:
{chr(10).join(resumen_partidos)}

EL MODELO HA SELECCIONADO LA SIGUIENTE COMBINADA ÓPTIMA:
Número de partidos: {mejor_combo['n']}
Probabilidad conjunta: {mejor_combo['prob_conjunta']}%
Cuota combinada estimada: {mejor_combo['cuota_conjunta']}x
Valor esperado: {mejor_combo['ev_pct']}%
Selecciones:
{chr(10).join(resumen_combo)}

Por favor, genera un análisis experto breve (máx 200 palabras) que incluya:
1. Por qué estas selecciones son las más sólidas estadísticamente
2. El nivel de confianza real y advertencias de riesgo
3. Consejo sobre gestión de bankroll (% a apostar)
4. Una valoración honesta de las posibilidades reales

Responde en español, de forma directa y profesional. No uses markdown, solo texto plano."""

    if api_key_anthropic and api_key_anthropic.strip():
        try:
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": api_key_anthropic,
                    "anthropic-version": "2023-06-01"
                },
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 500,
                    "messages": [{"role": "user", "content": prompt}]
                },
                timeout=30
            )
            if response.status_code == 200:
                data = response.json()
                return data['content'][0]['text'], True
        except Exception:
            pass

    # Análisis local de calidad si no hay API key o falla
    n   = mejor_combo['n']
    pc  = mejor_combo['prob_conjunta']
    ev  = mejor_combo['ev_pct']
    cuota = mejor_combo['cuota_conjunta']
    sels  = mejor_combo['selecciones']

    nivel_riesgo = "bajo" if pc >= 40 else "moderado" if pc >= 22 else "elevado"
    bankroll_pct = 3 if pc >= 40 else 2 if pc >= 22 else 1

    lineas = [
        f"Combinada de {n} selecciones con probabilidad conjunta del {pc}% y cuota estimada {cuota}x.",
        "",
        "SELECCIONES JUSTIFICADAS:",
    ]
    for sel in sels:
        p_pct = sel['prob'] * 100
        confianza = "alta confianza" if p_pct >= 65 else "confianza media" if p_pct >= 55 else "confianza ajustada"
        lineas.append(f"• {sel['mercado']} en {sel['partido_label']}: {p_pct:.1f}% de probabilidad ({confianza}).")

    lineas += [
        "",
        f"VALORACIÓN: El valor esperado positivo del {ev}% indica que la combinada tiene edge "
        f"estadístico sobre el mercado. El nivel de riesgo es {nivel_riesgo}.",
        "",
        f"GESTIÓN DE BANKROLL: Se recomienda no superar el {bankroll_pct}% del bankroll total "
        f"en apuestas combinadas, independientemente de la confianza del modelo.",
        "",
        "ADVERTENCIA: Las probabilidades son estimaciones estadísticas. "
        "Factores externos (lesiones, motivación, meteorología) no están incluidos en el modelo."
    ]
    return "\n".join(lineas), False


def mostrar_tab_combinada(df_total, num_partidos, factor_decay, api_key_anthropic):
    st.subheader("🤖 Generador de Apuesta Combinada con IA")
    st.markdown(
        "Introduce entre **2 y 10 enfrentamientos** de diferentes ligas. "
        "La IA analizará cada partido con el modelo Dixon-Coles y seleccionará la **combinada óptima** "
        "maximizando el valor esperado con el menor riesgo posible."
    )

    equipos = sorted(set(df_total['HomeTeam'].unique()) | set(df_total['AwayTeam'].unique()))

    # --- Configuración de la combinada ---
    with st.expander("⚙️ Parámetros de la combinada", expanded=False):
        col_cfg1, col_cfg2, col_cfg3 = st.columns(3)
        with col_cfg1:
            min_sel = st.slider("Mín. selecciones", 2, 4, 2)
            max_sel = st.slider("Máx. selecciones", 2, 6, 4)
        with col_cfg2:
            prob_ind_min = st.slider("Prob. mínima individual (%)", 45, 70, 52) / 100
            prob_conj_min= st.slider("Prob. mínima conjunta (%)", 5, 35, 12) / 100
        with col_cfg3:
            st.info(
                "**Prob. individual**: descarta selecciones con menos probabilidad que este umbral.\n\n"
                "**Prob. conjunta**: descarta combinadas con probabilidad total inferior."
            )

    # --- Selector dinámico de partidos ---
    st.markdown("### 📋 Partidos a analizar")

    if 'num_partidos_combo' not in st.session_state:
        st.session_state.num_partidos_combo = 3

    col_add, col_rem, _ = st.columns([1, 1, 4])
    with col_add:
        if st.button("➕ Añadir partido", use_container_width=True):
            if st.session_state.num_partidos_combo < 10:
                st.session_state.num_partidos_combo += 1
    with col_rem:
        if st.button("➖ Quitar partido", use_container_width=True):
            if st.session_state.num_partidos_combo > 2:
                st.session_state.num_partidos_combo -= 1

    partidos_seleccionados = []
    for i in range(st.session_state.num_partidos_combo):
        c1, c2, c3 = st.columns([1, 3, 3])
        with c1:
            st.markdown(f"<br><b>#{i+1}</b>", unsafe_allow_html=True)
        with c2:
            local_i = st.selectbox(
                f"🏠 Local #{i+1}", equipos,
                index=min(i * 2, len(equipos) - 1),
                key=f"combo_local_{i}"
            )
        with c3:
            visitante_i = st.selectbox(
                f"🚀 Visitante #{i+1}", equipos,
                index=min(i * 2 + 1, len(equipos) - 1),
                key=f"combo_visit_{i}"
            )
        if local_i != visitante_i:
            partidos_seleccionados.append((local_i, visitante_i))

    st.divider()

    # --- Botón de análisis ---
    if st.button("🚀 ANALIZAR Y GENERAR COMBINADA ÓPTIMA", use_container_width=True, type="primary"):
        if len(partidos_seleccionados) < 2:
            st.error("❌ Necesitas al menos 2 partidos distintos para generar una combinada.")
            return

        partidos_unicos = list(dict.fromkeys(partidos_seleccionados))

        with st.spinner("🔍 Analizando partidos con Dixon-Coles..."):
            progress = st.progress(0)
            resultados = []
            for idx, (loc, vis) in enumerate(partidos_unicos):
                progress.progress((idx + 1) / len(partidos_unicos))
                r = analizar_partido_para_combinada(df_total, loc, vis, num_partidos, factor_decay)
                if r:
                    resultados.append(r)
                else:
                    st.warning(f"⚠️ Sin datos suficientes para {loc} vs {vis}")
            progress.empty()

        if len(resultados) < 2:
            st.error("❌ No hay suficientes datos para analizar los partidos seleccionados.")
            return

        with st.spinner("🧮 Calculando combinación óptima..."):
            mejor_combo = calcular_mejor_combinada(
                resultados, min_sel, max_sel, prob_ind_min, prob_conj_min
            )

        if not mejor_combo:
            st.warning(
                "⚠️ No se encontró una combinada que cumpla los criterios de calidad. "
                "Prueba a reducir el umbral de probabilidad mínima o añade más partidos."
            )
            # Mostrar igualmente el análisis individual
        else:
            # --- MOSTRAR RESULTADO PRINCIPAL ---
            nivel, clase_css, emoji = calcular_nivel_riesgo(
                mejor_combo['prob_conjunta'], mejor_combo['n']
            )

            st.markdown("### 🏆 COMBINADA ÓPTIMA SELECCIONADA")

            with st.container():
                st.markdown(f"""
                <div class="combo-winner">
                    <div style="font-size:13px; opacity:0.7; margin-bottom:8px;">
                        MEJOR COMBINADA · {mejor_combo['n']} SELECCIONES
                    </div>
                    <div style="display:flex; gap:10px; flex-wrap:wrap; margin-bottom:15px;">
                        <div class="combo-stat">
                            <div style="font-size:28px; font-weight:900; color:#e94560;">
                                {mejor_combo['prob_conjunta']}%
                            </div>
                            <div style="font-size:11px; opacity:0.7;">Prob. Conjunta</div>
                        </div>
                        <div class="combo-stat">
                            <div style="font-size:28px; font-weight:900; color:#4fc3f7;">
                                {mejor_combo['cuota_conjunta']}x
                            </div>
                            <div style="font-size:11px; opacity:0.7;">Cuota Estimada</div>
                        </div>
                        <div class="combo-stat">
                            <div style="font-size:28px; font-weight:900;
                                color:{'#2ecc71' if mejor_combo['ev_pct'] > 0 else '#e74c3c'};">
                                {'+' if mejor_combo['ev_pct'] > 0 else ''}{mejor_combo['ev_pct']}%
                            </div>
                            <div style="font-size:11px; opacity:0.7;">Valor Esperado</div>
                        </div>
                        <div class="combo-stat">
                            <div style="font-size:28px;">{emoji}</div>
                            <div style="font-size:11px; opacity:0.7;">Riesgo {nivel}</div>
                        </div>
                    </div>
                """, unsafe_allow_html=True)

                for sel in mejor_combo['selecciones']:
                    p_pct = sel['prob'] * 100
                    color_prob = "#2ecc71" if p_pct >= 65 else "#f1c40f" if p_pct >= 52 else "#e74c3c"
                    st.markdown(f"""
                    <div class="combo-partido">
                        <span style="font-size:13px; opacity:0.6;">{sel['partido_label']}</span><br>
                        <span style="font-size:17px; font-weight:700;">✅ {sel['mercado']}</span>
                        <span style="margin-left:15px; color:{color_prob}; font-weight:bold;">
                            {p_pct:.1f}%
                        </span>
                        <span style="margin-left:10px; opacity:0.6; font-size:13px;">
                            cuota ~{sel['cuota_est']:.2f}
                        </span>
                        <span style="margin-left:10px; opacity:0.5; font-size:11px;">
                            [{sel['tipo']} · {sel['modo']}]
                        </span>
                    </div>
                    """, unsafe_allow_html=True)

                st.markdown("</div>", unsafe_allow_html=True)

            # --- ANÁLISIS IA ---
            st.markdown("### 🤖 Análisis del Experto IA")
            ia_label = "⚡ Claude AI" if (api_key_anthropic and api_key_anthropic.strip()) else "📊 Análisis Local"

            with st.spinner(f"Generando análisis ({ia_label})..."):
                explicacion, es_claude = llamar_ia_combinada(resultados, mejor_combo, api_key_anthropic)

            st.markdown(f"""
            <div class="ia-explicacion">
                <span class="ia-badge">{'🤖 Claude AI' if es_claude else '📊 Análisis estadístico'}</span>
                <p style="margin:0; white-space: pre-line;">{explicacion}</p>
            </div>
            """, unsafe_allow_html=True)

        # --- TABLA RESUMEN DE TODOS LOS PARTIDOS ---
        st.divider()
        st.markdown("### 📊 Resumen de todos los partidos analizados")

        filas = []
        for p in resultados:
            mejor_op = p['mejor_opcion']
            filas.append({
                'Partido': f"{p['local']} vs {p['visitante']}",
                'Local %': p['p_win'],
                'Empate %': p['p_draw'],
                'Visit. %': p['p_lose'],
                'Over 2.5 %': p['prob_over25'],
                'BTTS %': p['prob_ambos'],
                'Mejor opción': mejor_op['mercado'],
                'Prob. mejor': f"{mejor_op['prob']:.1f}%",
                'Modelo': p['modo'],
            })

        df_resumen = pd.DataFrame(filas)
        st.dataframe(
            df_resumen.style.background_gradient(
                subset=['Local %', 'Empate %', 'Visit. %', 'Over 2.5 %', 'BTTS %'],
                cmap='RdYlGn', vmin=20, vmax=80
            ),
            use_container_width=True
        )

        # Exportar
        csv_combo = df_resumen.to_csv(index=False)
        st.download_button(
            "📥 Exportar análisis CSV", data=csv_combo,
            file_name=f"combinada_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv"
        )

        st.session_state['ultimo_combo_resultado'] = {
            'mejor_combo': mejor_combo,
            'resultados':  resultados
        }


# ============================================================================
# BACKTESTING
# ============================================================================

@st.cache_data(ttl=3600)
def ejecutar_backtesting(_df_total, num_partidos_test=200, umbral_prob=0.55):
    if _df_total.empty or len(_df_total) < 100:
        return None

    df_sorted = _df_total.dropna(subset=['FTHG', 'FTAG', 'Date']).sort_values('Date')
    df_test   = df_sorted.tail(num_partidos_test)
    resultados= []

    progress_bar = st.progress(0)
    total = len(df_test)

    for i, (idx, partido) in enumerate(df_test.iterrows()):
        progress_bar.progress((i + 1) / total)
        local     = partido['HomeTeam']
        visitante = partido['AwayTeam']
        fecha     = partido['Date']

        df_anterior = df_sorted[df_sorted['Date'] < fecha]
        if len(df_anterior) < 50:
            continue

        d_local = df_anterior[(df_anterior['HomeTeam'] == local) | (df_anterior['AwayTeam'] == local)]
        d_visit = df_anterior[(df_anterior['HomeTeam'] == visitante) | (df_anterior['AwayTeam'] == visitante)]
        if len(d_local) < 5 or len(d_visit) < 5:
            continue

        try:
            pron = PronosticadorDixonColes(df_anterior, d_local, d_visit, local, visitante, 20)

            resultado_real = ('local' if partido['FTHG'] > partido['FTAG']
                              else 'visitante' if partido['FTHG'] < partido['FTAG']
                              else 'empate')

            probs    = {'local': pron.p_win/100, 'empate': pron.p_draw/100, 'visitante': pron.p_lose/100}
            pred_mod = max(probs, key=probs.get)
            prob_max = max(probs.values())

            resultados.append({
                'fecha': fecha, 'local': local, 'visitante': visitante,
                'pred': pred_mod, 'prob': prob_max,
                'real': resultado_real,
                'correcto': pred_mod == resultado_real,
                'over_real': (partido['FTHG'] + partido['FTAG']) > 2.5,
                'prob_over': pron.prob_over_25 / 100,
                'ambos_real': partido['FTHG'] > 0 and partido['FTAG'] > 0,
                'prob_ambos': pron.prob_ambos / 100,
            })
        except:
            continue

    progress_bar.empty()
    if not resultados:
        return None

    df_res = pd.DataFrame(resultados)
    df_seg = df_res[df_res['prob'] >= umbral_prob]

    bins = [0.4, 0.5, 0.6, 0.7, 0.8, 1.0]
    calibracion = []
    for i in range(len(bins) - 1):
        mask = (df_res['prob'] >= bins[i]) & (df_res['prob'] < bins[i+1])
        sub  = df_res[mask]
        if len(sub) >= 5:
            calibracion.append({
                'Rango':           f"{int(bins[i]*100)}-{int(bins[i+1]*100)}%",
                'N Partidos':      len(sub),
                'Prob Media Pred.':round(sub['prob'].mean()*100, 1),
                'Tasa Real':       round(sub['correcto'].mean()*100, 1),
                'Diferencia':      round((sub['correcto'].mean() - sub['prob'].mean())*100, 1)
            })

    over_mask  = df_res['prob_over']  >= 0.6
    ambos_mask = df_res['prob_ambos'] >= 0.6

    roi = df_seg['correcto'].apply(lambda x: 0.9 if x else -1).mean() * 100 if not df_seg.empty else 0

    return {
        'total_partidos':   len(df_res),
        'accuracy_total':   round(df_res['correcto'].mean()*100, 1),
        'accuracy_seguro':  round(df_seg['correcto'].mean()*100, 1) if not df_seg.empty else 0,
        'partidos_seguros': len(df_seg),
        'calibracion':      pd.DataFrame(calibracion),
        'accuracy_over':    round(df_res[over_mask]['over_real'].mean()*100, 1) if over_mask.sum() > 0 else 0,
        'accuracy_ambos':   round(df_res[ambos_mask]['ambos_real'].mean()*100, 1) if ambos_mask.sum() > 0 else 0,
        'roi_simulado':     round(roi, 1),
        'df_res':           df_res,
    }


def mostrar_tab_backtesting(df_total):
    st.subheader("🔬 Backtesting y Validación del Modelo")
    st.info("Predice cada partido usando SOLO datos anteriores, simulando condiciones reales.")

    col_bt1, col_bt2, col_bt3 = st.columns(3)
    with col_bt1: n_test  = st.slider("Partidos de test", 50, 500, 200, 50)
    with col_bt2: umbral  = st.slider("Umbral de confianza", 0.50, 0.75, 0.55, 0.05)
    with col_bt3: ejecutar= st.button("▶️ Ejecutar Backtesting", use_container_width=True)

    if ejecutar:
        with st.spinner("Ejecutando backtesting..."):
            resultado = ejecutar_backtesting(df_total, n_test, umbral)
            if resultado:
                st.session_state['backtest_cache'] = resultado
                st.success("✅ Backtesting completado")
            else:
                st.error("❌ No hay suficientes datos")

    if 'backtest_cache' in st.session_state:
        r = st.session_state['backtest_cache']
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        col_m1.metric("📊 Partidos analizados",    r['total_partidos'])
        col_m2.metric("🎯 Accuracy global",         f"{r['accuracy_total']}%")
        col_m3.metric(f"✅ Accuracy (≥{int(umbral*100)}%)", f"{r['accuracy_seguro']}%")
        col_m4.metric("💰 ROI simulado",            f"{r['roi_simulado']}%")

        col_ov, col_am, col_seg = st.columns(3)
        col_ov.metric("⚽ Accuracy Over 2.5",    f"{r['accuracy_over']}%")
        col_am.metric("🥅 Accuracy Ambos Marcan",f"{r['accuracy_ambos']}%")
        col_seg.metric("🔒 Con alta confianza",   r['partidos_seguros'])

        if not r['calibracion'].empty:
            st.subheader("📈 Calibración del Modelo")
            st.dataframe(r['calibracion'], use_container_width=True)

        if r['accuracy_seguro'] > 55:
            st.success(f"✅ Accuracy {r['accuracy_seguro']}% con alta confianza. El modelo tiene edge estadístico.")
        elif r['accuracy_seguro'] > 45:
            st.warning(f"⚠️ Accuracy {r['accuracy_seguro']}%. Mejora ligera sobre el azar.")
        else:
            st.error(f"❌ Accuracy {r['accuracy_seguro']}%. No supera claramente el azar.")
        return r
    return None


# ============================================================================
# CUOTAS EN TIEMPO REAL
# ============================================================================

@st.cache_data(ttl=300)
def obtener_cuotas_tiempo_real(local, visitante, api_key, liga_cod=None):
    if not api_key or api_key.strip() == "":
        return None

    liga_map = {
        'SP1': 'soccer_spain_la_liga', 'SP2': 'soccer_spain_segunda_division',
        'E0':  'soccer_epl',           'E1':  'soccer_efl_champ',
        'I1':  'soccer_italy_serie_a', 'D1':  'soccer_germany_bundesliga',
        'F1':  'soccer_france_ligue_one','P1': 'soccer_portugal_primeira_liga',
        'N1':  'soccer_netherlands_eredivisie','B1':'soccer_belgium_first_div'
    }
    sport  = liga_map.get(liga_cod, 'soccer_epl')
    url    = f"https://api.the-odds-api.com/v4/sports/{sport}/odds/"
    params = {'apiKey': api_key, 'regions': 'eu', 'markets': 'h2h', 'oddsFormat': 'decimal'}

    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code != 200:
            return None

        cuotas = {}
        for evento in response.json():
            home = evento.get('home_team', '').lower()
            away = evento.get('away_team', '').lower()
            if (local.lower()[:6] in home or home[:6] in local.lower()) and \
               (visitante.lower()[:6] in away or away[:6] in visitante.lower()):
                for bookmaker in evento.get('bookmakers', []):
                    for market in bookmaker.get('markets', []):
                        if market['key'] == 'h2h':
                            for outcome in market.get('outcomes', []):
                                name  = outcome['name'].lower()
                                price = outcome['price']
                                if evento['home_team'].lower() in name:
                                    if 'local' not in cuotas or price > cuotas['local']['cuota']:
                                        cuotas['local'] = {'cuota': price, 'casa': bookmaker['title'],
                                                           'prob_implícita': round(1/price*100,1), 'tipo':'real'}
                                elif evento['away_team'].lower() in name:
                                    if 'visitante' not in cuotas or price > cuotas['visitante']['cuota']:
                                        cuotas['visitante'] = {'cuota': price, 'casa': bookmaker['title'],
                                                               'prob_implícita': round(1/price*100,1), 'tipo':'real'}
                                elif 'draw' in name:
                                    if 'empate' not in cuotas or price > cuotas['empate']['cuota']:
                                        cuotas['empate'] = {'cuota': price, 'casa': bookmaker['title'],
                                                            'prob_implícita': round(1/price*100,1), 'tipo':'real'}
                return cuotas if len(cuotas) >= 2 else None
        return None
    except:
        return None


# ============================================================================
# CARGA DE DATOS
# ============================================================================

@st.cache_data(ttl=3600)
def cargar_datos():
    try:
        if not os.path.exists("datos_historicos.csv"):
            return pd.DataFrame()
        df = pd.read_csv("datos_historicos.csv")
        df['Date']     = pd.to_datetime(df['Date'], dayfirst=True, errors='coerce')
        df['HomeTeam'] = df['HomeTeam'].str.strip()
        df['AwayTeam'] = df['AwayTeam'].str.strip()
        df = df.dropna(subset=['FTHG', 'FTAG'])
        return df
    except Exception as e:
        st.error(f"Error cargando datos: {e}")
        return pd.DataFrame()


def actualizar_csv(progreso_bar, status_text):
    temporadas = ['2526', '2425']
    ligas = [
        "SP1","SP2","E0","E1","E2","I1","I2","D1","D2","F1","F2",
        "P1","N1","B1","T1","G1","SC0","SC1","SC2","SC3","A1",
        "C1","DK1","SE1","SE2","NO1","NO2","FI1","PO1","CZ1","RU1",
        "UA1","HR1","SR1","BG1","RO1","HU1","SK1","SI1"
    ]
    total   = len(temporadas) * len(ligas)
    contador= 0
    lista_dfs, errores = [], []

    for t in temporadas:
        for cod in ligas:
            contador += 1
            progreso_bar.progress(contador / total)
            status_text.text(f"📥 {t}/{cod} ({int(contador/total*100)}%)")
            url = f"https://www.football-data.co.uk/mmz4281/{t}/{cod}.csv"
            try:
                r = requests.get(url, timeout=10, headers={'User-Agent':'Mozilla/5.0'})
                if r.status_code == 200 and len(r.text) > 100:
                    df_t = pd.read_csv(StringIO(r.text))
                    df_t['Temporada'] = t
                    df_t['Liga']      = cod
                    cols = ['Date','HomeTeam','AwayTeam','FTHG','FTAG','FTR','Div','Temporada','Liga',
                            'HC','AC','HF','AF','HY','AY','HR','AR',
                            'B365H','B365D','B365A','PSH','PSD','PSA',
                            'WHH','WHD','WHA','VCH','VCD','VCA',
                            'MaxH','MaxD','MaxA','AvgH','AvgD','AvgA']
                    ex = [c for c in cols if c in df_t.columns]
                    if ex:
                        lista_dfs.append(df_t[ex])
                else:
                    errores.append(f"{t}/{cod}")
            except Exception as e:
                errores.append(f"{t}/{cod}: {str(e)[:30]}")

    if lista_dfs:
        if os.path.exists("datos_historicos.csv"):
            fecha = datetime.now().strftime("%Y%m%d_%H%M%S")
            os.makedirs("backups", exist_ok=True)
            try:
                os.rename("datos_historicos.csv", f"backups/backup_{fecha}.csv")
            except:
                pass
        df_final = pd.concat(lista_dfs, ignore_index=True)
        df_final.to_csv("datos_historicos.csv", index=False)
        return True, len(df_final), errores
    return False, 0, errores


def obtener_historial_h2h(df, local, visitante, limite=8):
    mask = ((df['HomeTeam'] == local) & (df['AwayTeam'] == visitante)) | \
           ((df['HomeTeam'] == visitante) & (df['AwayTeam'] == local))
    return df[mask].sort_values('Date', ascending=False).head(limite)


# ============================================================================
# FUNCIONES DE ANÁLISIS
# ============================================================================

def calcular_probabilidades_todos_mercados(pronostico):
    return {
        '1x2': {'local': pronostico.p_win, 'empate': pronostico.p_draw, 'visitante': pronostico.p_lose},
        'doble_oportunidad': {
            '1X': pronostico.p_win + pronostico.p_draw,
            '12': pronostico.p_win + pronostico.p_lose,
            'X2': pronostico.p_draw + pronostico.p_lose,
        },
        'over_under': {
            'Over 0.5':  (1 - poisson.pmf(0, pronostico.media_total)) * 100,
            'Under 0.5': poisson.pmf(0, pronostico.media_total) * 100,
            'Over 1.5':  (1 - poisson.cdf(1, pronostico.media_total)) * 100,
            'Under 1.5': poisson.cdf(1, pronostico.media_total) * 100,
            'Over 2.5':  pronostico.prob_over_25,
            'Under 2.5': pronostico.prob_under_25,
            'Over 3.5':  (1 - poisson.cdf(3, pronostico.media_total)) * 100,
            'Under 3.5': poisson.cdf(3, pronostico.media_total) * 100,
        },
        'ambos_marcan': {'Si': pronostico.prob_ambos, 'No': 100 - pronostico.prob_ambos},
    }


def encontrar_mejores_cuotas(df_partido):
    if df_partido.empty:
        return None
    row = df_partido.iloc[0]
    mapping = {
        'local':     ['B365H','PSH','WHH','VCH','MaxH'],
        'empate':    ['B365D','PSD','WHD','VCD','MaxD'],
        'visitante': ['B365A','PSA','WHA','VCA','MaxA'],
    }
    cuotas = {}
    for mercado, cols in mapping.items():
        mejor_cuota, mejor_casa = 0, None
        for col in cols:
            if col in row and pd.notna(row[col]):
                val = float(row[col])
                if val > mejor_cuota:
                    mejor_cuota, mejor_casa = val, col
        if mejor_cuota > 0:
            cuotas[mercado] = {'cuota': mejor_cuota, 'casa': mejor_casa,
                               'prob_implícita': round(1/mejor_cuota*100,1), 'tipo':'histórico'}
    return cuotas if cuotas else None


def calcular_valor_esperado(prob_real, cuota):
    if cuota <= 0 or prob_real <= 0:
        return -100
    return (prob_real / 100 * cuota - 1) * 100


def recomendar_apuesta_segura(pronostico, cuotas_disponibles):
    items = [
        (f'Local: {pronostico.local}',          pronostico.p_win,          'local',     2.0),
        ('Empate',                               pronostico.p_draw,         'empate',    3.2),
        (f'Visitante: {pronostico.visitante}',   pronostico.p_lose,         'visitante', 3.0),
        ('Over 2.5',                             pronostico.prob_over_25,   None,        2.0),
        ('Under 2.5',                            pronostico.prob_under_25,  None,        1.9),
        ('Ambos marcan - SI',                    pronostico.prob_ambos,     None,        1.95),
        ('Ambos marcan - NO',                    100-pronostico.prob_ambos, None,        1.85),
    ]
    todas = []
    for nombre, prob, clave, cuota_def in items:
        cuota = (cuotas_disponibles.get(clave, {}).get('cuota', cuota_def)
                 if (cuotas_disponibles and clave) else cuota_def)
        seg   = 'ALTA' if prob > 65 else 'MEDIA' if prob > 50 else 'BAJA'
        tipo  = '1X2' if clave in ['local','empate','visitante'] else 'Mercado'
        todas.append({'nombre': nombre, 'tipo': tipo, 'probabilidad': prob,
                      'cuota': cuota, 'seguridad': seg})
    return sorted(todas, key=lambda x: x['probabilidad'], reverse=True)


def calcular_rating_confianza(pronostico, backtest_result=None):
    rating   = 0
    muestras = len(pronostico.df_local) + len(pronostico.df_visitante)
    rating  += 25 if muestras > 35 else (15 if muestras > 20 else 5)
    max_prob = max(pronostico.p_win, pronostico.p_draw, pronostico.p_lose)
    rating  += 25 if max_prob > 60 else (15 if max_prob > 50 else 5)
    diff_ou  = abs(pronostico.prob_over_25 - pronostico.prob_under_25)
    rating  += 15 if diff_ou > 30 else (10 if diff_ou > 15 else 3)
    diff_am  = abs(pronostico.prob_ambos - 50)
    rating  += 15 if diff_am > 25 else (10 if diff_am > 10 else 3)
    if hasattr(pronostico, 'modo_modelo') and pronostico.modo_modelo == "Dixon-Coles":
        rating += 10
    if backtest_result and backtest_result.get('accuracy_seguro', 0) > 55:
        rating += 10
    return min(rating, 100)


def analizar_value_bets(pronostico, cuotas_disponibles):
    if not cuotas_disponibles:
        return None
    res = {}
    mapping = {'local': pronostico.p_win, 'empate': pronostico.p_draw, 'visitante': pronostico.p_lose}
    for mercado, prob_real in mapping.items():
        if mercado in cuotas_disponibles:
            info  = cuotas_disponibles[mercado]
            value = prob_real - info['prob_implícita']
            res[mercado] = {'value': value, 'es_value': value > 5,
                            'cuota': info['cuota'], 'casa': info.get('casa',''),
                            'prob_impl': info['prob_implícita'], 'prob_real': prob_real,
                            'valor_esperado': calcular_valor_esperado(prob_real, info['cuota']),
                            'tipo_cuota': info.get('tipo','histórico')}
    valores_pos = [(k, v['value']) for k, v in res.items() if v['value'] > 3]
    if valores_pos:
        mejor_k = max(valores_pos, key=lambda x: x[1])
        res['mejor_value'] = {'mercado': mejor_k[0], 'value': mejor_k[1],
                              'cuota': res[mejor_k[0]]['cuota'],
                              'tipo':  res[mejor_k[0]]['tipo_cuota']}
    else:
        res['mejor_value'] = None
    return res


def check_alertas(pronostico, cuotas_disponibles, value_analysis, backtest_result=None):
    alertas = []
    if value_analysis and value_analysis.get('mejor_value'):
        v    = value_analysis['mejor_value']
        tipo = "⚡ Tiempo real" if v.get('tipo') == 'real' else "📊 Histórica"
        lbl  = "🔴 VALUE BET FUERTE" if v['value'] > 10 else "💰 VALUE BET DETECTADO"
        alertas.append({'tipo': lbl, 'mensaje': f"{v['mercado']} +{v['value']:.1f}% ({tipo})", 'clase':'alerta-verde'})
    max_prob = max(pronostico.p_win, pronostico.p_draw, pronostico.p_lose)
    if max_prob > 70:
        alertas.append({'tipo':'🎯 FAVORITO CLARO',         'mensaje':f"{max_prob:.1f}%", 'clase':'alerta-amarilla'})
    if pronostico.prob_over_25 > 75:
        alertas.append({'tipo':'⚽ MUCHOS GOLES ESPERADOS', 'mensaje':f"Over 2.5 al {pronostico.prob_over_25:.1f}%", 'clase':'alerta-amarilla'})
    if pronostico.prob_ambos > 75:
        alertas.append({'tipo':'🥅 AMBOS MARCAN PROBABLE',  'mensaje':f"{pronostico.prob_ambos:.1f}%", 'clase':'alerta-amarilla'})
    if backtest_result and backtest_result.get('accuracy_seguro', 0) > 60:
        alertas.append({'tipo':'✅ MODELO VALIDADO',         'mensaje':f"Accuracy histórico: {backtest_result['accuracy_seguro']:.1f}%", 'clase':'alerta-verde'})
    return alertas


def analizar_tendencias_equipo(df, equipo):
    partidos = df[(df['HomeTeam'] == equipo) | (df['AwayTeam'] == equipo)].tail(10)
    if partidos.empty:
        return None
    res = []
    for _, p in partidos.iterrows():
        if p['HomeTeam'] == equipo:
            r = 'G' if p['FTHG'] > p['FTAG'] else ('P' if p['FTHG'] < p['FTAG'] else 'E')
        else:
            r = 'G' if p['FTAG'] > p['FTHG'] else ('P' if p['FTAG'] < p['FTHG'] else 'E')
        res.append(r)
    return {'forma': ''.join(res),
            'rachas': {'victorias': res.count('G'), 'empates': res.count('E'), 'derrotas': res.count('P')},
            'puntos_10': res.count('G')*3 + res.count('E')}


def analizar_ligas(df_total):
    col_liga = 'Liga' if 'Liga' in df_total.columns else ('Div' if 'Div' in df_total.columns else None)
    if col_liga is None:
        return pd.DataFrame()
    ligas_dict = {
        'SP1':'La Liga','SP2':'La Liga 2','E0':'Premier','E1':'Championship',
        'I1':'Serie A','D1':'Bundesliga','F1':'Ligue 1','P1':'Liga Portugal',
        'N1':'Eredivisie','B1':'Pro League Bélgica','T1':'Süper Lig',
        'G1':'Super League Grecia','SC0':'Premiership Escocia','A1':'Bundesliga Austria'
    }
    stats = []
    for cod, nombre in ligas_dict.items():
        df_liga = df_total[df_total[col_liga] == cod]
        if len(df_liga) > 10:
            stats.append({'Liga': nombre, 'Partidos': len(df_liga),
                          'Media Goles': round((df_liga['FTHG'].mean()+df_liga['FTAG'].mean())/2, 2),
                          'Over 2.5 %': round((df_liga['FTHG']+df_liga['FTAG'] > 2.5).mean()*100, 1)})
    return pd.DataFrame(stats).sort_values('Over 2.5 %', ascending=False)


def calcular_prob_mitades(df, equipo):
    local_data = df[df['HomeTeam'] == equipo]
    away_data  = df[df['AwayTeam']  == equipo]
    total      = len(local_data) + len(away_data)
    if total == 0:
        return None, None
    if 'H1G' in df.columns and 'A1G' in df.columns:
        g1 = (local_data['H1G'].fillna(0) > 0).sum() + (away_data['A1G'].fillna(0) > 0).sum()
        g2 = (local_data.get('H2G', pd.Series(dtype=float)).fillna(0) > 0).sum() + \
             (away_data.get('A2G',  pd.Series(dtype=float)).fillna(0) > 0).sum()
        return g1/total*100, g2/total*100
    else:
        media = ((local_data['FTHG'].mean() if not local_data.empty else 0) +
                 (away_data['FTAG'].mean()  if not away_data.empty  else 0)) / 2
        return ((1 - poisson.pmf(0, media*0.45))*100,
                (1 - poisson.pmf(0, media*0.55))*100)


# ============================================================================
# INTERFAZ PRINCIPAL
# ============================================================================

def main():
    if 'favoritos' not in st.session_state:
        st.session_state.favoritos = []

    st.title("⚽ ASISTENTE DE APUESTAS JR6 - FÚTBOL PROFESIONAL")
    st.caption("Dixon-Coles · Pesos Temporales · Value Bets · Backtesting · Combinada IA")

    df_total = cargar_datos()

    if df_total.empty:
        st.warning("⚠️ No hay datos. Pulsa 'Actualizar Base de Datos' en la barra lateral.")
        with st.sidebar:
            if st.button("🔄 Actualizar Base de Datos", use_container_width=True):
                with st.spinner("Actualizando..."):
                    pbar = st.progress(0); status = st.empty()
                    ok, num, err = actualizar_csv(pbar, status)
                    if ok:
                        st.success(f"✅ {num} registros")
                        st.cache_data.clear(); time.sleep(1); st.rerun()
        return

    equipos = sorted(set(df_total['HomeTeam'].unique()) | set(df_total['AwayTeam'].unique()))

    # ===================== SIDEBAR =====================
    with st.sidebar:
        st.header("⚙️ CONFIGURACIÓN")

        num_partidos  = st.slider("📊 Partidos a analizar", 5, 50, 20, 5)
        factor_decay  = st.slider("⏳ Decaimiento temporal", 0.001, 0.010, 0.003, 0.001,
                                   help="Mayor = más peso a partidos recientes")

        st.divider()
        st.subheader("🔑 APIs")

        api_key_odds      = st.text_input("The Odds API Key (cuotas real)",
                                           value="", type="password",
                                           help="Gratis en theoddsapi.com (500 req/mes)")
        api_key_anthropic = st.text_input("Anthropic API Key (IA Combinada)",
                                           value="", type="password",
                                           help="Para análisis IA experto en combinadas. Sin key = análisis estadístico local.")
        if api_key_odds:
            st.success("⚡ Odds API configurada")
        if api_key_anthropic:
            st.success("🤖 Claude API configurada")

        st.divider()
        st.header("⭐ FAVORITOS")
        nuevo_fav = st.selectbox("Añadir favorito", equipos, key='nuevo_fav')
        if st.button("➕ Añadir", use_container_width=True):
            if nuevo_fav not in st.session_state.favoritos:
                st.session_state.favoritos.append(nuevo_fav)
                st.success(f"✅ {nuevo_fav} añadido")
        for fav in st.session_state.favoritos:
            c1, c2 = st.columns([3,1])
            c1.write(f"• {fav}")
            if c2.button("❌", key=f"del_{fav}"):
                st.session_state.favoritos.remove(fav); st.rerun()

        st.divider()
        st.header("📊 LIGAS")
        df_ligas = analizar_ligas(df_total)
        if not df_ligas.empty:
            st.dataframe(df_ligas, use_container_width=True, height=200)

        st.divider()
        if st.button("🔄 Actualizar Base de Datos", use_container_width=True):
            with st.spinner("Actualizando..."):
                pbar = st.progress(0); status = st.empty()
                ok, num, err = actualizar_csv(pbar, status)
                if ok:
                    st.success(f"✅ {num} registros")
                    st.cache_data.clear(); time.sleep(1); st.rerun()

        st.caption(f"📱 {'Móvil' if ES_MOVIL else 'Escritorio'} · {datetime.now().strftime('%d/%m/%Y %H:%M')}")

    # ===================== TABS =====================
    tab_pronostico, tab_combinada, tab_backtest = st.tabs([
        "⚽ Pronóstico Individual",
        "🤖 Combinada IA",
        "🔬 Backtesting & Validación"
    ])

    with tab_backtest:
        backtest_result = mostrar_tab_backtesting(df_total)

    with tab_combinada:
        mostrar_tab_combinada(df_total, num_partidos, factor_decay, api_key_anthropic)

    # ===================== PRONÓSTICO INDIVIDUAL =====================
    with tab_pronostico:
        if st.session_state.favoritos and st.checkbox("⭐ Solo favoritos"):
            disp = st.session_state.favoritos
        else:
            disp = equipos

        col1, col2 = st.columns(2)
        with col1:
            local = st.selectbox("🏠 Local", disp, index=0)
        with col2:
            idx = min(1, len(disp)-1) if len(disp) > 1 else 0
            visitante = st.selectbox("🚀 Visitante", disp, index=idx)

        d_local = df_total[(df_total['HomeTeam']==local) | (df_total['AwayTeam']==local)]
        d_visit = df_total[(df_total['HomeTeam']==visitante) | (df_total['AwayTeam']==visitante)]

        if d_local.empty or d_visit.empty:
            st.error("❌ Datos insuficientes para alguno de los equipos")
            return

        pronostico = PronosticadorDixonColes(
            df_total, d_local, d_visit, local, visitante, num_partidos, factor_decay
        )

        modo_color = "#2ecc71" if pronostico.modo_modelo == "Dixon-Coles" else "#f1c40f"
        st.markdown(
            f"<small>🤖 Modelo: <b style='color:{modo_color};'>{pronostico.modo_modelo}</b> | "
            f"λ local: <b>{pronostico.media_local:.2f}</b> | "
            f"λ visitante: <b>{pronostico.media_visitante:.2f}</b></small>",
            unsafe_allow_html=True
        )

        # Cuotas
        cuotas_disp   = None
        liga_detectada= getattr(pronostico, 'liga_detectada', None)

        if api_key_odds:
            with st.spinner("⚡ Buscando cuotas en tiempo real..."):
                cuotas_disp = obtener_cuotas_tiempo_real(local, visitante, api_key_odds, liga_detectada)
            if cuotas_disp:
                st.success("⚡ Cuotas en tiempo real obtenidas")
            else:
                st.info("Partido no encontrado en tiempo real, usando cuotas históricas")

        if not cuotas_disp:
            h2h_cuotas  = obtener_historial_h2h(df_total, local, visitante, 1)
            cuotas_disp = encontrar_mejores_cuotas(h2h_cuotas) if not h2h_cuotas.empty else None

        mercados       = calcular_probabilidades_todos_mercados(pronostico)
        apuestas_seg   = recomendar_apuesta_segura(pronostico, cuotas_disp)
        backtest_res   = st.session_state.get('backtest_cache', None)
        rating         = calcular_rating_confianza(pronostico, backtest_res)
        value_analysis = analizar_value_bets(pronostico, cuotas_disp)
        alertas        = check_alertas(pronostico, cuotas_disp, value_analysis, backtest_res)

        prob_local_1, prob_local_2 = calcular_prob_mitades(df_total, local)
        prob_visit_1, prob_visit_2 = calcular_prob_mitades(df_total, visitante)

        # Alertas
        if alertas:
            st.divider()
            st.subheader("🚨 ALERTAS")
            for a in alertas:
                st.markdown(
                    f"<div class='alerta-card {a.get('clase','alerta-amarilla')}'>"
                    f"<span style='font-size:20px;'>{a['tipo']}</span><br>{a['mensaje']}</div>",
                    unsafe_allow_html=True
                )

        # Resultados principales
        st.divider()
        cols = st.columns(4)
        with cols[0]:
            st.subheader("🎯 Marcador")
            gl, gv, pm = pronostico.get_marcador_sugerido()
            st.markdown(f"<h1 style='color:#FF4B4B;text-align:center;'>{gl} - {gv}</h1>", unsafe_allow_html=True)
            st.caption(f"Prob: {pm:.1f}%")
        with cols[1]:
            st.subheader("📊 1X2")
            st.metric(f"1 {local[:10]}", f"{pronostico.p_win:.1f}%")
            st.metric("X Empate",         f"{pronostico.p_draw:.1f}%")
            st.metric(f"2 {visitante[:10]}", f"{pronostico.p_lose:.1f}%")
        with cols[2]:
            st.subheader("⚽ Goles")
            co = "green-big" if pronostico.prob_over_25 > 70 else "big-font"
            st.markdown(f"<p class='{co}'>Over 2.5: {pronostico.prob_over_25:.1f}%</p>", unsafe_allow_html=True)
            st.markdown(f"<p class='big-font'>Under 2.5: {pronostico.prob_under_25:.1f}%</p>", unsafe_allow_html=True)
        with cols[3]:
            st.subheader("🥅 Ambos")
            ca = "green-big" if pronostico.prob_ambos > 65 else "big-font"
            st.markdown(f"<p class='{ca}'>Sí: {pronostico.prob_ambos:.1f}%</p>", unsafe_allow_html=True)
            st.markdown(f"<p class='big-font'>No: {100-pronostico.prob_ambos:.1f}%</p>", unsafe_allow_html=True)

        # Confianza y cuotas
        colr1, colr2, colr3 = st.columns(3)
        with colr1:
            st.metric("📊 Rating Confianza", f"{rating}%")
            if rating > 70:   st.success("ALTA CONFIANZA")
            elif rating > 50: st.warning("CONFIANZA MEDIA")
            else:             st.error("BAJA CONFIANZA")
        with colr2:
            if cuotas_disp and 'local' in cuotas_disp:
                icon = "⚡" if cuotas_disp['local'].get('tipo') == 'real' else "📊"
                st.metric(f"{icon} Mejor Local", f"{cuotas_disp['local']['cuota']:.2f}")
                st.caption(cuotas_disp['local']['casa'])
            else:
                st.metric("💰 Local", "No disponible")
        with colr3:
            if cuotas_disp and 'visitante' in cuotas_disp:
                icon = "⚡" if cuotas_disp['visitante'].get('tipo') == 'real' else "📊"
                st.metric(f"{icon} Mejor Visitante", f"{cuotas_disp['visitante']['cuota']:.2f}")
                st.caption(cuotas_disp['visitante']['casa'])
            else:
                st.metric("💰 Visitante", "No disponible")

        # Value bet
        if value_analysis and value_analysis.get('mejor_value'):
            st.divider()
            v    = value_analysis['mejor_value']['value']
            tipo = "⚡ Tiempo real" if value_analysis['mejor_value'].get('tipo') == 'real' else "📊 Histórica"
            if v > 10:
                st.markdown(
                    f"<div class='value-alta'>🔥 VALUE FUERTE ({tipo})<br>"
                    f"Apuesta: <b>{value_analysis['mejor_value']['mercado']}</b><br>"
                    f"Cuota: {value_analysis['mejor_value']['cuota']:.2f} | Ventaja: +{v:.1f}%</div>",
                    unsafe_allow_html=True
                )
            elif v > 5:
                st.markdown(
                    f"<div class='value-media'>💰 VALUE DETECTADO ({tipo})<br>"
                    f"Apuesta: <b>{value_analysis['mejor_value']['mercado']}</b><br>"
                    f"Cuota: {value_analysis['mejor_value']['cuota']:.2f} | Ventaja: +{v:.1f}%</div>",
                    unsafe_allow_html=True
                )

        # Top apuestas
        st.divider()
        st.subheader("🎯 TOP 5 APUESTAS SUGERIDAS")
        for i, ap in enumerate(apuestas_seg[:5]):
            col  = "#2ecc71" if ap['seguridad']=='ALTA' else "#f1c40f" if ap['seguridad']=='MEDIA' else "#e74c3c"
            emo  = "🟢" if ap['seguridad']=='ALTA' else "🟡" if ap['seguridad']=='MEDIA' else "🔴"
            ve   = calcular_valor_esperado(ap['probabilidad'], ap['cuota'])
            ca1,ca2,ca3,ca4 = st.columns([3,1,1,1])
            ca1.markdown(f"**{i+1}. {ap['nombre']}**"); ca1.caption(ap['tipo'])
            ca2.markdown(f"<p style='color:{col};font-weight:bold;font-size:20px;'>{ap['probabilidad']:.1f}%</p>",
                         unsafe_allow_html=True)
            ca3.markdown(f"<p style='font-size:20px;'>{emo}</p>", unsafe_allow_html=True)
            if ve > 5:   ca4.markdown(f"<p style='color:#2ecc71;font-weight:bold;'>EV:+{ve:.1f}%</p>", unsafe_allow_html=True)
            elif ve < -5:ca4.markdown(f"<p style='color:#e74c3c;'>EV:{ve:.1f}%</p>", unsafe_allow_html=True)
            else:        ca4.markdown(f"EV:{ve:.1f}%")

        # Estadísticas
        st.divider()
        st.subheader("📈 Estadísticas Previstas")
        col_e1, col_e2, col_e3 = st.columns(3)
        col_e1.metric("🎯 Corners",  f"{pronostico.corners_total:.1f}")
        col_e2.metric("🟨 Tarjetas", f"{pronostico.tarjetas_total:.1f}")
        col_e3.metric("⚖️ Faltas",   f"{pronostico.faltas_total:.1f}")

        st.write("---")
        st.subheader("🕐 Probabilidad de anotar por partes")
        col_p1, col_p2 = st.columns(2)
        for col_p, eq, p1, p2 in [(col_p1, local, prob_local_1, prob_local_2),
                                    (col_p2, visitante, prob_visit_1, prob_visit_2)]:
            with col_p:
                st.markdown(f"**{eq}**")
                if p1 is not None:
                    st.metric("1ª Parte", f"{p1:.1f}%")
                    st.metric("2ª Parte", f"{p2:.1f}%")
                else:
                    st.info("Sin datos")

        # Mercados
        st.divider()
        st.subheader("📊 ANÁLISIS POR MERCADOS")
        tab1, tab2, tab3 = st.tabs(["1X2", "Over/Under", "Ambos Marcan"])

        with tab1:
            colx1, colx2, colx3 = st.columns(3)
            for col_x, label, prob in [
                (colx1, f"🏠 {local}",    mercados['1x2']['local']),
                (colx2, "🤝 Empate",       mercados['1x2']['empate']),
                (colx3, f"🚀 {visitante}", mercados['1x2']['visitante'])
            ]:
                col_x.markdown(f"**{label}**")
                col_x.markdown(f"<p class='big-font'>{prob:.1f}%</p>", unsafe_allow_html=True)

        with tab2:
            ou         = mercados['over_under']
            over_items = sorted([(k,v) for k,v in ou.items() if k.startswith('Over')],
                                key=lambda x: float(x[0].split()[1]))
            under_items= sorted([(k,v) for k,v in ou.items() if k.startswith('Under')],
                                key=lambda x: float(x[0].split()[1]))
            col_o, col_u = st.columns(2)
            with col_o:
                st.markdown("**Over**")
                for nom, prob in over_items:
                    color = "#2ecc71" if prob > 65 else "#e74c3c" if prob < 35 else "inherit"
                    st.markdown(f"<span style='color:{color};'>{nom}: **{prob:.1f}%**</span>",
                                unsafe_allow_html=True)
            with col_u:
                st.markdown("**Under**")
                for nom, prob in under_items:
                    color = "#2ecc71" if prob > 65 else "#e74c3c" if prob < 35 else "inherit"
                    st.markdown(f"<span style='color:{color};'>{nom}: **{prob:.1f}%**</span>",
                                unsafe_allow_html=True)

        with tab3:
            cb1, cb2 = st.columns(2)
            cb1.markdown("**✅ SI**")
            cb1.markdown(f"<p class='big-font'>{mercados['ambos_marcan']['Si']:.1f}%</p>",
                         unsafe_allow_html=True)
            cb2.markdown("**❌ NO**")
            cb2.markdown(f"<p class='big-font'>{mercados['ambos_marcan']['No']:.1f}%</p>",
                         unsafe_allow_html=True)

        # Probabilidad de anotar
        st.divider()
        st.subheader("🎯 Probabilidad de anotar (≥1 gol)")
        cg1, cg2, cg3 = st.columns([2,2,1])
        with cg1:
            st.markdown(f"**{local}**")
            cls = 'green-big' if pronostico.prob_local_1 > 75 else 'big-font'
            st.markdown(f"<p class='{cls}'>{pronostico.prob_local_1:.1f}%</p>", unsafe_allow_html=True)
        with cg2:
            st.markdown(f"**{visitante}**")
            cls = 'green-big' if pronostico.prob_visitante_1 > 75 else 'big-font'
            st.markdown(f"<p class='{cls}'>{pronostico.prob_visitante_1:.1f}%</p>", unsafe_allow_html=True)
        with cg3:
            fiab, colf, tip = pronostico.get_fiabilidad()
            st.markdown("**Fiabilidad**")
            st.markdown(f"<p style='color:{colf};font-weight:bold;'>{fiab}</p>", unsafe_allow_html=True)
            st.caption(tip)

        # Historial H2H
        st.divider()
        st.subheader("🔙 Historial Directo")
        h2h = obtener_historial_h2h(df_total, local, visitante)
        if not h2h.empty:
            wins_l  = ((h2h['HomeTeam']==local)    & (h2h['FTHG']>h2h['FTAG']) |
                       (h2h['AwayTeam']==local)    & (h2h['FTAG']>h2h['FTHG'])).sum()
            empates = (h2h['FTHG'] == h2h['FTAG']).sum()
            wins_v  = len(h2h) - wins_l - empates

            c1, c2, c3 = st.columns(3)
            c1.metric(f"✅ {local[:12]}",     wins_l)
            c2.metric("🤝 Empates",            empates)
            c3.metric(f"✅ {visitante[:12]}", wins_v)

            for _, p in h2h.iterrows():
                fecha = p['Date'].strftime('%d/%m/%Y') if pd.notna(p['Date']) else '?'
                gl, gv = int(p['FTHG']), int(p['FTAG'])
                res = "🤝" if gl==gv else (
                    "🏠" if (p['HomeTeam']==local and gl>gv) or (p['AwayTeam']==local and gv>gl) else "🚀")
                corners  = int(p.get('HC',0)+p.get('AC',0))
                tarjetas = int(p.get('HY',0)+p.get('AY',0)+p.get('HR',0)+p.get('AR',0))
                cuo = ""
                for casa in ['B365','PS','WH']:
                    if f'{casa}H' in p and pd.notna(p.get(f'{casa}H')):
                        cuo = f" | {casa}: {p[f'{casa}H']:.2f}"; break
                st.markdown(
                    f"📅 {fecha} {res} | **{p['HomeTeam']} {gl}-{gv} {p['AwayTeam']}** "
                    f"| 🎯 {corners} | 🟨 {tarjetas}{cuo}"
                )
        else:
            st.info("Sin historial entre estos equipos")

        # Exportar
        st.divider()
        col_ex1, col_ex2 = st.columns(2)
        with col_ex1:
            data_exp = {
                'Fecha': datetime.now().strftime('%Y-%m-%d %H:%M'),
                'Local': local, 'Visitante': visitante,
                'Modelo': pronostico.modo_modelo,
                'λ_Local': round(pronostico.media_local, 3),
                'λ_Visitante': round(pronostico.media_visitante, 3),
                'Prob_Local_%': round(pronostico.p_win, 1),
                'Prob_Empate_%': round(pronostico.p_draw, 1),
                'Prob_Visitante_%': round(pronostico.p_lose, 1),
                'Over_2.5_%': round(pronostico.prob_over_25, 1),
                'Ambos_Marcan_%': round(pronostico.prob_ambos, 1),
                'Rating_Confianza': rating,
                'Backtest_Accuracy': backtest_res.get('accuracy_seguro','N/A') if backtest_res else 'N/A'
            }
            csv = pd.DataFrame([data_exp]).to_csv(index=False)
            st.download_button("📥 Exportar CSV", data=csv,
                               file_name=f"pronostico_{local}_vs_{visitante}.csv",
                               mime="text/csv", use_container_width=True)
        with col_ex2:
            if st.button("🔄 Nuevo Pronóstico", use_container_width=True):
                st.rerun()


if __name__ == "__main__":
    main()
