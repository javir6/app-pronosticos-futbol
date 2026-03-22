import streamlit as st
import pandas as pd
import numpy as np
from scipy.stats import poisson
import requests
import plotly.express as px
import plotly.graph_objects as go
import os
from datetime import datetime
import time
from io import StringIO

# ============================================================================
# CONFIGURACIÓN INICIAL Y DETECCIÓN MÓVIL
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
    page_title="⚽ Asistente de Apuestas IA - Fútbol Profesional",
    page_icon="⚽",
    layout="centered" if ES_MOVIL else "wide",
    initial_sidebar_state="collapsed" if ES_MOVIL else "expanded"
)

# Estilos personalizados (igual que antes)
st.markdown("""
<style>
    .big-font { font-size:26px !important; font-weight: bold; }
    .green-big { color: #2ecc71; font-size:26px !important; font-weight: bold; }
    .red-big { color: #e74c3c; font-size:26px !important; font-weight: bold; }
    .yellow-big { color: #f1c40f; font-size:26px !important; font-weight: bold; }
    .info-box { padding: 1rem; border-radius: 0.5rem; background-color: #f0f2f6; }
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
    .alerta-card { padding: 15px; border-radius: 10px; margin: 10px 0; font-weight: bold; }
    .alerta-verde { background-color: #e8f5e9; border-left: 5px solid #2e7d32; }
    .alerta-amarilla { background-color: #fff8e1; border-left: 5px solid #ff8f00; }
    
    .forma-container { display: flex; gap: 5px; margin: 10px 0; flex-wrap: wrap; }
    .forma-item { width: 35px; height: 35px; display: flex; align-items: center; 
                  justify-content: center; border-radius: 8px; color: white; 
                  font-weight: bold; font-size: 18px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
    .forma-G { background-color: #2ecc71; }
    .forma-E { background-color: #f1c40f; }
    .forma-P { background-color: #e74c3c; }
    
    @media (max-width: 768px) {
        .stButton button { min-height: 50px; font-size: 18px; }
        .stSelectbox div[data-baseweb="select"] { min-height: 50px; }
    }
</style>
""", unsafe_allow_html=True)

# ============================================================================
# CLASE PRINCIPAL PARA PRONÓSTICOS
# ============================================================================

class PronosticadorFutbol:
    def __init__(self, df_local, df_visitante, local, visitante, num_partidos=20):
        self.df_local = df_local.tail(num_partidos)
        self.df_visitante = df_visitante.tail(num_partidos)
        self.local = local
        self.visitante = visitante
        self.num_partidos = num_partidos
        self.calcular_todo()
    
    def calcular_todo(self):
        self.media_local = self._calcular_media_goles(self.df_local, self.local, 'local')
        self.media_visitante = self._calcular_media_goles(self.df_visitante, self.visitante, 'visitante')
        self.media_total = self.media_local + self.media_visitante
        
        self.prob_local_1 = (1 - poisson.pmf(0, self.media_local)) * 100
        self.prob_visitante_1 = (1 - poisson.pmf(0, self.media_visitante)) * 100
        self.prob_ambos = (self.prob_local_1/100 * self.prob_visitante_1/100) * 100
        self.prob_over_25 = (1 - poisson.cdf(2, self.media_total)) * 100
        self.prob_under_25 = poisson.cdf(2, self.media_total) * 100
        
        self.matriz, self.p_win, self.p_draw, self.p_lose = self._calcular_matriz()
        
        self.corners_total = self._calcular_media_estadistica('HC', 'AC')
        self.tarjetas_total = self._calcular_media_estadistica(['HY', 'HR'], ['AY', 'AR'])
        self.faltas_total = self._calcular_media_estadistica('HF', 'AF')
    
    def _calcular_media_goles(self, df, equipo, condicion):
        if condicion == 'local':
            mask = df['HomeTeam'] == equipo
            goles = df.loc[mask, 'FTHG']
        else:
            mask = df['AwayTeam'] == equipo
            goles = df.loc[mask, 'FTAG']
        if len(goles) < 3:
            return goles.mean() if not goles.empty else 0.0
        goles_sin_outliers = goles[goles <= 5]
        return goles_sin_outliers.mean() if not goles_sin_outliers.empty else goles.mean()
    
    def _calcular_media_estadistica(self, col_local, col_visitante):
        total = 0
        if isinstance(col_local, list):
            for col in col_local:
                if col in self.df_local.columns:
                    total += self.df_local[col].mean() if not self.df_local[col].isna().all() else 0
        else:
            if col_local in self.df_local.columns:
                total += self.df_local[col_local].mean() if not self.df_local[col_local].isna().all() else 0
        if isinstance(col_visitante, list):
            for col in col_visitante:
                if col in self.df_visitante.columns:
                    total += self.df_visitante[col].mean() if not self.df_visitante[col].isna().all() else 0
        else:
            if col_visitante in self.df_visitante.columns:
                total += self.df_visitante[col_visitante].mean() if not self.df_visitante[col_visitante].isna().all() else 0
        return max(0, total)
    
    def _calcular_matriz(self):
        p_local = [poisson.pmf(i, self.media_local) for i in range(8)]
        p_visitante = [poisson.pmf(i, self.media_visitante) for i in range(8)]
        matriz = np.outer(p_local, p_visitante)
        p_win = np.sum(np.tril(matriz, -1))
        p_draw = np.diag(matriz).sum()
        p_lose = np.sum(np.triu(matriz, 1))
        return matriz, p_win * 100, p_draw * 100, p_lose * 100
    
    def get_fiabilidad(self):
        muestras = len(self.df_local) + len(self.df_visitante)
        if muestras > 35:
            return "ALTA", "#2ecc71", "✅ Muestra muy representativa"
        elif muestras > 20:
            return "MEDIA", "#f1c40f", "⚠️ Muestra aceptable"
        else:
            return "BAJA", "#e74c3c", "❌ Pocos datos, usar con precaución"
    
    def get_marcador_sugerido(self):
        idx_max = np.unravel_index(np.argmax(self.matriz), self.matriz.shape)
        prob_max = self.matriz[idx_max] * 100
        return idx_max[0], idx_max[1], prob_max

# ============================================================================
# FUNCIONES DE CARGA Y PROCESAMIENTO DE DATOS
# ============================================================================

@st.cache_data(ttl=3600)
def cargar_datos():
    try:
        if not os.path.exists("datos_historicos.csv"):
            return pd.DataFrame()
        df = pd.read_csv("datos_historicos.csv")
        df['Date'] = pd.to_datetime(df['Date'], dayfirst=True, errors='coerce')
        df['HomeTeam'] = df['HomeTeam'].str.strip()
        df['AwayTeam'] = df['AwayTeam'].str.strip()
        df = df.dropna(subset=['FTHG', 'FTAG'])
        return df
    except Exception as e:
        st.error(f"Error cargando datos: {e}")
        return pd.DataFrame()

def actualizar_csv(progreso_bar, status_text):
    """Actualiza la base de datos con TODAS las ligas europeas disponibles"""
    temporadas = ['2526', '2425']
    
    ligas = [
        "SP1", "SP2", "E0", "E1", "E2", "I1", "I2", "D1", "D2", "F1", "F2",
        "P1", "N1", "B1", "T1", "G1", "SC0", "SC1", "SC2", "SC3", "A1",
        "C1", "DK1", "SE1", "SE2", "NO1", "NO2", "FI1", "PO1", "CZ1", "RU1",
        "UA1", "HR1", "SR1", "BG1", "RO1", "HU1", "SK1", "SI1"
    ]
    
    total_archivos = len(temporadas) * len(ligas)
    contador = 0
    lista_dfs = []
    errores = []
    exitosos = 0
    
    error_container = st.empty()
    
    for t in temporadas:
        for cod in ligas:
            contador += 1
            progreso = contador / total_archivos
            progreso_bar.progress(progreso)
            status_text.text(f"📥 Descargando: {t}/{cod} ({int(progreso*100)}%)")
            
            url = f"https://www.football-data.co.uk/mmz4281/{t}/{cod}.csv"
            try:
                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
                response = requests.get(url, timeout=10, headers=headers)
                
                if response.status_code == 200 and len(response.text) > 100:
                    df_temp = pd.read_csv(StringIO(response.text))
                    df_temp['Temporada'] = t
                    df_temp['Liga'] = cod
                    
                    # Añadimos columnas de goles por mitad
                    cols = ['Date', 'HomeTeam', 'AwayTeam', 'FTHG', 'FTAG', 'FTR', 'Div', 'Temporada', 'Liga',
                           'HC', 'AC', 'HF', 'AF', 'HY', 'AY', 'HR', 'AR',
                           'H1G', 'A1G', 'H2G', 'A2G',  # Goles por mitad
                           'B365H', 'B365D', 'B365A', 'PSC', 'PSH', 'PSD', 'PSA',
                           'WHH', 'WHD', 'WHA', 'VCH', 'VCD', 'VCA',
                           'MaxH', 'MaxD', 'MaxA', 'AvgH', 'AvgD', 'AvgA']
                    existentes = [c for c in cols if c in df_temp.columns]
                    if existentes:
                        lista_dfs.append(df_temp[existentes])
                        exitosos += 1
                else:
                    errores.append(f"{t}/{cod} - error")
            except Exception as e:
                errores.append(f"{t}/{cod} - {str(e)[:50]}")
                continue
    
    status_text.text("💾 Guardando datos...")
    
    if errores:
        with error_container.expander(f"⚠️ Errores ({len(errores)} archivos)"):
            for err in errores[:10]:
                st.text(f"• {err}")
    
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
# FUNCIONES DE ANÁLISIS AVANZADO
# ============================================================================

def calcular_probabilidades_todos_mercados(pronostico):
    mercados = {}
    mercados['1x2'] = {'local': pronostico.p_win, 'empate': pronostico.p_draw, 'visitante': pronostico.p_lose}
    mercados['doble_oportunidad'] = {'1X': pronostico.p_win + pronostico.p_draw,
                                      '12': pronostico.p_win + pronostico.p_lose,
                                      'X2': pronostico.p_draw + pronostico.p_lose}
    mercados['over_under'] = {
        'Over 0.5': (1 - poisson.pmf(0, pronostico.media_total)) * 100,
        'Under 0.5': poisson.pmf(0, pronostico.media_total) * 100,
        'Over 1.5': (1 - poisson.cdf(1, pronostico.media_total)) * 100,
        'Under 1.5': poisson.cdf(1, pronostico.media_total) * 100,
        'Over 2.5': pronostico.prob_over_25,
        'Under 2.5': pronostico.prob_under_25,
        'Over 3.5': (1 - poisson.cdf(3, pronostico.media_total)) * 100,
        'Under 3.5': poisson.cdf(3, pronostico.media_total) * 100
    }
    mercados['ambos_marcan'] = {'Si': pronostico.prob_ambos, 'No': 100 - pronostico.prob_ambos}
    mercados['goles_exactos'] = {f'Exactly {g}': poisson.pmf(g, pronostico.media_total) * 100 for g in range(7)}
    return mercados

def encontrar_mejores_cuotas(df_partido):
    if df_partido.empty:
        return None
    ultima_fila = df_partido.iloc[0]
    mapping = {
        'local': ['B365H', 'PSH', 'WHH', 'VCH', 'MaxH'],
        'empate': ['B365D', 'PSD', 'WHD', 'VCD', 'MaxD'],
        'visitante': ['B365A', 'PSA', 'WHA', 'VCA', 'MaxA']
    }
    cuotas = {}
    for mercado, columnas in mapping.items():
        mejor_cuota = 0
        mejor_casa = None
        for col in columnas:
            if col in ultima_fila and pd.notna(ultima_fila[col]):
                cuota_val = float(ultima_fila[col])
                if cuota_val > mejor_cuota:
                    mejor_cuota = cuota_val
                    mejor_casa = col
        if mejor_cuota > 0:
            cuotas[mercado] = {'cuota': mejor_cuota, 'casa': mejor_casa, 'prob_implícita': 1/mejor_cuota*100, 'tipo': 'real'}
    return cuotas if cuotas else None

def calcular_valor_esperado(prob_real, cuota):
    if cuota <= 0 or prob_real <= 0:
        return -100
    return (prob_real / 100 * cuota - 1) * 100

def recomendar_apuesta_segura(pronostico, cuotas_disponibles):
    todas = []
    # 1X2
    todas.append({'nombre': f'Local: {pronostico.local}', 'tipo': '1X2',
                  'probabilidad': pronostico.p_win,
                  'cuota': cuotas_disponibles.get('local', {}).get('cuota', 1.0) if cuotas_disponibles else 1.0,
                  'seguridad': 'ALTA' if pronostico.p_win > 60 else 'MEDIA' if pronostico.p_win > 45 else 'BAJA'})
    todas.append({'nombre': 'Empate', 'tipo': '1X2',
                  'probabilidad': pronostico.p_draw,
                  'cuota': cuotas_disponibles.get('empate', {}).get('cuota', 1.0) if cuotas_disponibles else 1.0,
                  'seguridad': 'ALTA' if pronostico.p_draw > 60 else 'MEDIA' if pronostico.p_draw > 45 else 'BAJA'})
    todas.append({'nombre': f'Visitante: {pronostico.visitante}', 'tipo': '1X2',
                  'probabilidad': pronostico.p_lose,
                  'cuota': cuotas_disponibles.get('visitante', {}).get('cuota', 1.0) if cuotas_disponibles else 1.0,
                  'seguridad': 'ALTA' if pronostico.p_lose > 60 else 'MEDIA' if pronostico.p_lose > 45 else 'BAJA'})
    # Over/Under
    todas.append({'nombre': 'Over 2.5', 'tipo': 'Totales', 'probabilidad': pronostico.prob_over_25, 'cuota': 2.0,
                  'seguridad': 'ALTA' if pronostico.prob_over_25 > 65 else 'MEDIA' if pronostico.prob_over_25 > 50 else 'BAJA'})
    todas.append({'nombre': 'Under 2.5', 'tipo': 'Totales', 'probabilidad': pronostico.prob_under_25, 'cuota': 1.9,
                  'seguridad': 'ALTA' if pronostico.prob_under_25 > 65 else 'MEDIA' if pronostico.prob_under_25 > 50 else 'BAJA'})
    # Ambos marcan
    todas.append({'nombre': 'Ambos marcan - SI', 'tipo': 'Ambos Marcan', 'probabilidad': pronostico.prob_ambos, 'cuota': 1.95,
                  'seguridad': 'ALTA' if pronostico.prob_ambos > 65 else 'MEDIA' if pronostico.prob_ambos > 50 else 'BAJA'})
    todas.append({'nombre': 'Ambos marcan - NO', 'tipo': 'Ambos Marcan', 'probabilidad': 100 - pronostico.prob_ambos, 'cuota': 1.85,
                  'seguridad': 'ALTA' if (100 - pronostico.prob_ambos) > 65 else 'MEDIA' if (100 - pronostico.prob_ambos) > 50 else 'BAJA'})
    todas.sort(key=lambda x: x['probabilidad'], reverse=True)
    return todas

def generar_combinadas_inteligentes(pronostico):
    combis = []
    if pronostico.p_win > 55 and pronostico.prob_over_25 > 55:
        prob = (pronostico.p_win/100)*(pronostico.prob_over_25/100)*100
        combis.append({'nombre': 'Local gana + Over 2.5', 'apuestas': [f'Gana {pronostico.local}', 'Over 2.5'],
                       'probabilidad': prob, 'cuota_estimada': 3.5, 'seguridad': 'ALTA' if prob > 35 else 'MEDIA'})
    if pronostico.p_draw > 30 and pronostico.prob_under_25 > 60:
        prob_1X = (pronostico.p_win + pronostico.p_draw)/100
        prob = prob_1X * (pronostico.prob_under_25/100) * 100
        combis.append({'nombre': 'Local o Empate + Under 2.5', 'apuestas': ['1X', 'Under 2.5'],
                       'probabilidad': prob, 'cuota_estimada': 2.8, 'seguridad': 'ALTA' if prob > 40 else 'MEDIA'})
    if pronostico.prob_ambos > 60 and pronostico.prob_over_25 > 60:
        prob = (pronostico.prob_ambos/100)*(pronostico.prob_over_25/100)*100
        combis.append({'nombre': 'Ambos marcan + Over 2.5', 'apuestas': ['Ambos marcan - SI', 'Over 2.5'],
                       'probabilidad': prob, 'cuota_estimada': 3.2, 'seguridad': 'ALTA' if prob > 40 else 'MEDIA'})
    if pronostico.p_draw > 35 and pronostico.prob_under_25 > 65:
        prob = (pronostico.p_draw/100)*(pronostico.prob_under_25/100)*100
        combis.append({'nombre': 'Empate + Under 2.5', 'apuestas': ['Empate', 'Under 2.5'],
                       'probabilidad': prob, 'cuota_estimada': 4.0, 'seguridad': 'MEDIA'})
    combis.sort(key=lambda x: x['probabilidad'], reverse=True)
    return combis

def calcular_rating_confianza(pronostico):
    rating = 0
    muestras = len(pronostico.df_local) + len(pronostico.df_visitante)
    rating += 30 if muestras > 35 else (20 if muestras > 20 else 10)
    max_prob = max(pronostico.p_win, pronostico.p_draw, pronostico.p_lose)
    rating += 30 if max_prob > 60 else (20 if max_prob > 50 else 10)
    diff_ou = abs(pronostico.prob_over_25 - pronostico.prob_under_25)
    rating += 20 if diff_ou > 30 else (15 if diff_ou > 15 else 5)
    diff_ambos = abs(pronostico.prob_ambos - 50)
    rating += 20 if diff_ambos > 25 else (15 if diff_ambos > 10 else 5)
    return min(rating, 100)

def analizar_value_bets(pronostico, cuotas_disponibles):
    if not cuotas_disponibles:
        return None
    res = {}
    for mercado in ['local', 'empate', 'visitante']:
        if mercado in cuotas_disponibles:
            prob_real = getattr(pronostico, 'p_win' if mercado == 'local' else 'p_draw' if mercado == 'empate' else 'p_lose')
            value = prob_real - cuotas_disponibles[mercado]['prob_implícita']
            res[mercado] = {'value': value, 'es_value': value > 5,
                            'cuota': cuotas_disponibles[mercado]['cuota'],
                            'casa': cuotas_disponibles[mercado]['casa'],
                            'prob_impl': cuotas_disponibles[mercado]['prob_implícita'],
                            'prob_real': prob_real}
    valores = [r['value'] for r in res.values() if r['value'] > 3]
    if valores:
        max_val = max(valores)
        for k, v in res.items():
            if v['value'] == max_val:
                res['mejor_value'] = {'mercado': k, 'value': max_val, 'cuota': v['cuota']}
                break
    else:
        res['mejor_value'] = None
    return res

def analizar_ligas(df_total):
    if 'Div' not in df_total.columns:
        return pd.DataFrame()
    ligas_dict = {
        'SP1': 'La Liga', 'SP2': 'La Liga 2', 'E0': 'Premier', 'E1': 'Championship',
        'I1': 'Serie A', 'D1': 'Bundesliga', 'F1': 'Ligue 1', 'P1': 'Liga Portugal',
        'N1': 'Eredivisie', 'B1': 'Pro League Bélgica', 'T1': 'Süper Lig',
        'G1': 'Super League Grecia', 'SC0': 'Premiership Escocia', 'A1': 'Bundesliga Austria',
        'C1': 'Super League Suiza', 'DK1': 'Superliga Dinamarca', 'SE1': 'Allsvenskan',
        'NO1': 'Eliteserien', 'FI1': 'Veikkausliiga', 'PO1': 'Ekstraklasa',
        'CZ1': 'Fortuna Liga', 'RU1': 'Premier Liga Rusa', 'UA1': 'Premier Liga Ucrania',
        'HR1': 'Prva HNL', 'SR1': 'Super Liga Serbia', 'BG1': 'Parva Liga',
        'RO1': 'Liga I', 'HU1': 'NB I', 'SK1': 'Fortuna Liga Eslovaquia', 'SI1': 'Prva Liga Eslovenia'
    }
    stats = []
    for cod, nombre in ligas_dict.items():
        df_liga = df_total[df_total['Div'] == cod]
        if len(df_liga) > 10:
            media_goles = (df_liga['FTHG'].mean() + df_liga['FTAG'].mean()) / 2
            stats.append({
                'Liga': nombre,
                'Partidos': len(df_liga),
                'Media Goles': round(media_goles, 2),
                'Over 2.5 %': round((df_liga['FTHG'] + df_liga['FTAG'] > 2.5).mean() * 100, 1)
            })
    return pd.DataFrame(stats).sort_values('Over 2.5 %', ascending=False)

def check_alertas(pronostico, cuotas_disponibles, value_analysis):
    alertas = []
    if value_analysis and value_analysis.get('mejor_value') and value_analysis['mejor_value']['value'] > 10:
        alertas.append({'tipo': '🔴 VALUE BET FUERTE',
                        'mensaje': f"{value_analysis['mejor_value']['mercado']} con +{value_analysis['mejor_value']['value']:.1f}%"})
    max_prob = max(pronostico.p_win, pronostico.p_draw, pronostico.p_lose)
    if max_prob > 70:
        alertas.append({'tipo': '🎯 FAVORITO CLARO', 'mensaje': f"{max_prob:.1f}% de probabilidad"})
    if pronostico.prob_over_25 > 75:
        alertas.append({'tipo': '⚽ MUCHOS GOLES', 'mensaje': f"Over 2.5 al {pronostico.prob_over_25:.1f}%"})
    if pronostico.prob_ambos > 75:
        alertas.append({'tipo': '🥅 AMBOS MARCAN SEGURO', 'mensaje': f"{pronostico.prob_ambos:.1f}% de probabilidad"})
    return alertas

def analizar_tendencias_equipo(df, equipo):
    partidos = df[(df['HomeTeam'] == equipo) | (df['AwayTeam'] == equipo)].tail(10)
    if partidos.empty:
        return None
    res = []
    for _, p in partidos.iterrows():
        if p['HomeTeam'] == equipo:
            if p['FTHG'] > p['FTAG']: res.append('G')
            elif p['FTHG'] < p['FTAG']: res.append('P')
            else: res.append('E')
        else:
            if p['FTAG'] > p['FTHG']: res.append('G')
            elif p['FTAG'] < p['FTHG']: res.append('P')
            else: res.append('E')
    return {'forma': ''.join(res),
            'rachas': {'victorias': res.count('G'), 'empates': res.count('E'), 'derrotas': res.count('P')}}

# ============================================================================
# NUEVA FUNCIÓN: PROBABILIDADES POR MITAD
# ============================================================================

def calcular_prob_mitades(df, equipo):
    """
    Calcula la probabilidad de que el equipo anote en la primera y segunda parte.
    Utiliza los datos de goles por mitad (H1G, A1G, H2G, A2G) si existen.
    Si no existen, estima con un reparto del 45% de los goles en primera parte.
    """
    # Datos donde el equipo juega como local
    local_data = df[df['HomeTeam'] == equipo]
    # Datos donde el equipo juega como visitante
    away_data = df[df['AwayTeam'] == equipo]
    
    # Inicializar contadores
    total_partidos = len(local_data) + len(away_data)
    if total_partidos == 0:
        # Sin datos, devolvemos estimación global
        return None, None
    
    # Verificar si existen las columnas de goles por mitad
    if 'H1G' in df.columns and 'A1G' in df.columns and 'H2G' in df.columns and 'A2G' in df.columns:
        # Contar partidos donde anotó en primera parte
        goles_1_local = local_data['H1G'].fillna(0).apply(lambda x: x > 0).sum()
        goles_1_away = away_data['A1G'].fillna(0).apply(lambda x: x > 0).sum()
        partidos_anotados_1 = goles_1_local + goles_1_away
        
        # Contar partidos donde anotó en segunda parte
        goles_2_local = local_data['H2G'].fillna(0).apply(lambda x: x > 0).sum()
        goles_2_away = away_data['A2G'].fillna(0).apply(lambda x: x > 0).sum()
        partidos_anotados_2 = goles_2_local + goles_2_away
        
        prob_1 = (partidos_anotados_1 / total_partidos) * 100
        prob_2 = (partidos_anotados_2 / total_partidos) * 100
    else:
        # Estimación basada en la media de goles totales y reparto 45% primera parte
        # Media de goles del equipo (local + visitante)
        goles_local = local_data['FTHG'].mean() if not local_data.empty else 0
        goles_away = away_data['FTAG'].mean() if not away_data.empty else 0
        media_goles = (goles_local + goles_away) / 2 if (len(local_data) + len(away_data)) > 0 else 0
        
        # Suponemos que el 45% de los goles se marcan en primera parte (datos históricos)
        media_1 = media_goles * 0.45
        media_2 = media_goles * 0.55
        
        prob_1 = (1 - poisson.pmf(0, media_1)) * 100
        prob_2 = (1 - poisson.pmf(0, media_2)) * 100
    
    return prob_1, prob_2

# ============================================================================
# INTERFAZ PRINCIPAL
# ============================================================================

def main():
    if 'favoritos' not in st.session_state:
        st.session_state.favoritos = []
    
    st.title("⚽ ASISTENTE DE APUESTAS IA - FÚTBOL PROFESIONAL")
    
    with st.expander("ℹ️ ¿Cómo funciona?", expanded=False):
        st.markdown("""
        ### 🎯 **Sistema Experto de Apuestas**
        - Modelo Poisson para probabilidades reales.
        - Comparación con cuotas de mercado para detectar **Value Bets**.
        - Alertas automáticas y rating de confianza.
        """)
    
    df_total = cargar_datos()
    if df_total.empty:
        st.warning("⚠️ No hay datos. Pulsa 'Actualizar Base de Datos' en la barra lateral.")
        with st.sidebar:
            if st.button("🔄 Actualizar Base de Datos", use_container_width=True):
                with st.spinner("Actualizando..."):
                    pbar = st.progress(0)
                    status = st.empty()
                    ok, num, err = actualizar_csv(pbar, status)
                    if ok:
                        st.success(f"✅ {num} registros")
                        st.cache_data.clear()
                        time.sleep(1)
                        st.rerun()
        return
    
    equipos = sorted(set(df_total['HomeTeam'].unique()) | set(df_total['AwayTeam'].unique()))
    
    with st.sidebar:
        st.header("⚙️ CONFIGURACIÓN")
        # Indicador de cuotas
        eq_cuotas = []
        for eq in equipos[:30]:
            hh = obtener_historial_h2h(df_total, eq, eq)
            if not hh.empty and any(c in hh.columns and not hh[c].isna().all() for c in ['B365H','PSH','WHH']):
                eq_cuotas.append(eq)
        st.info(f"📊 {len(eq_cuotas)} equipos con cuotas históricas")
        
        num_partidos = st.slider("📊 Partidos a analizar", 5, 50, 20, 5)
        st.divider()
        
        st.header("⭐ MIS FAVORITOS")
        nuevo_fav = st.selectbox("Añadir favorito", equipos, key='nuevo_fav')
        if st.button("➕ Añadir", use_container_width=True):
            if nuevo_fav not in st.session_state.favoritos:
                st.session_state.favoritos.append(nuevo_fav)
                st.success(f"✅ {nuevo_fav} añadido")
        for fav in st.session_state.favoritos:
            colf1, colf2 = st.columns([3,1])
            colf1.write(f"• {fav}")
            if colf2.button("❌", key=f"del_{fav}"):
                st.session_state.favoritos.remove(fav)
                st.rerun()
        st.divider()
        
        st.header("📊 ESTADÍSTICAS POR LIGA")
        df_ligas = analizar_ligas(df_total)
        if not df_ligas.empty:
            st.dataframe(df_ligas, use_container_width=True, height=200)
        st.divider()
        
        if st.button("🔄 Actualizar Base de Datos", use_container_width=True):
            with st.spinner("Actualizando..."):
                pbar = st.progress(0)
                status = st.empty()
                ok, num, err = actualizar_csv(pbar, status)
                if ok:
                    st.success(f"✅ {num} registros")
                    st.cache_data.clear()
                    time.sleep(1)
                    st.rerun()
        st.caption(f"📱 Modo: {'Móvil' if ES_MOVIL else 'Escritorio'}")
        st.caption(f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    
    # Selección de equipos
    if st.session_state.favoritos and st.checkbox("⭐ Solo favoritos"):
        disp = st.session_state.favoritos
    else:
        disp = equipos
    
    col1, col2 = st.columns(2)
    with col1:
        local = st.selectbox("🏠 Local", disp, index=0)
    with col2:
        idx = min(1, len(disp)-1) if len(disp)>1 else 0
        visitante = st.selectbox("🚀 Visitante", disp, index=idx)
    
    # Filtrar datos
    d_local = df_total[(df_total['HomeTeam']==local)|(df_total['AwayTeam']==local)]
    d_visit = df_total[(df_total['HomeTeam']==visitante)|(df_total['AwayTeam']==visitante)]
    if d_local.empty or d_visit.empty:
        st.error("Datos insuficientes")
        return
    
    pronostico = PronosticadorFutbol(d_local, d_visit, local, visitante, num_partidos)
    tend_local = analizar_tendencias_equipo(d_local, local)
    tend_visit = analizar_tendencias_equipo(d_visit, visitante)
    
    h2h_cuotas = obtener_historial_h2h(df_total, local, visitante, 1)
    cuotas_disp = encontrar_mejores_cuotas(h2h_cuotas) if not h2h_cuotas.empty else None
    
    mercados = calcular_probabilidades_todos_mercados(pronostico)
    apuestas_seguras = recomendar_apuesta_segura(pronostico, cuotas_disp)
    rating = calcular_rating_confianza(pronostico)
    value_analysis = analizar_value_bets(pronostico, cuotas_disp)
    alertas = check_alertas(pronostico, cuotas_disp, value_analysis)
    
    # Calcular probabilidades de anotar por mitades
    prob_local_1, prob_local_2 = calcular_prob_mitades(df_total, local)
    prob_visit_1, prob_visit_2 = calcular_prob_mitades(df_total, visitante)
    
    if alertas:
        st.divider()
        st.subheader("🚨 ALERTAS")
        for a in alertas:
            cls = "alerta-verde" if "VALUE" in a['tipo'] or "MUCHOS" in a['tipo'] else "alerta-amarilla"
            st.markdown(f"<div class='{cls} alerta-card'><span style='font-size:20px;'>{a['tipo']}</span><br>{a['mensaje']}</div>", unsafe_allow_html=True)
    
    st.divider()
    cols = st.columns(4)
    with cols[0]:
        st.subheader("🎯 Marcador")
        gl, gv, pm = pronostico.get_marcador_sugerido()
        st.markdown(f"<h1 style='color:#FF4B4B; text-align:center;'>{gl} - {gv}</h1>", unsafe_allow_html=True)
        st.caption(f"Prob: {pm:.1f}%")
    with cols[1]:
        st.subheader("📊 Resultado")
        st.metric("Local", f"{pronostico.p_win:.1f}%")
        st.metric("Empate", f"{pronostico.p_draw:.1f}%")
        st.metric("Visitante", f"{pronostico.p_lose:.1f}%")
    with cols[2]:
        st.subheader("⚽ Goles")
        co = "green-big" if pronostico.prob_over_25>70 else "big-font"
        st.markdown(f"<p class='{co}'>Over 2.5: {pronostico.prob_over_25:.1f}%</p>", unsafe_allow_html=True)
        st.markdown(f"<p class='big-font'>Under 2.5: {pronostico.prob_under_25:.1f}%</p>", unsafe_allow_html=True)
    with cols[3]:
        st.subheader("🥅 Ambos")
        ca = "green-big" if pronostico.prob_ambos>65 else "big-font"
        st.markdown(f"<p class='{ca}'>{pronostico.prob_ambos:.1f}%</p>", unsafe_allow_html=True)
    
    colr1, colr2, colr3 = st.columns(3)
    with colr1:
        st.metric("📊 Confianza", f"{rating}%")
        if rating>70: st.success("ALTA")
        elif rating>50: st.warning("MEDIA")
        else: st.error("BAJA")
    with colr2:
        if cuotas_disp and 'local' in cuotas_disp:
            st.metric("💰 Mejor Local", f"{cuotas_disp['local']['cuota']:.2f}")
            st.caption(cuotas_disp['local']['casa'])
        else:
            st.metric("💰 Mejor Local", "No disponible")
    with colr3:
        if cuotas_disp and 'visitante' in cuotas_disp:
            st.metric("💰 Mejor Visitante", f"{cuotas_disp['visitante']['cuota']:.2f}")
            st.caption(cuotas_disp['visitante']['casa'])
        else:
            st.metric("💰 Mejor Visitante", "No disponible")
    
    st.divider()
    st.subheader("📈 FORMA RECIENTE (últimos 10)")
    colt1, colt2 = st.columns(2)
    with colt1:
        st.markdown(f"**🏠 {local}**")
        if tend_local:
            html = "<div class='forma-container'>"
            for letra in tend_local['forma']:
                html += f"<div class='forma-item forma-{letra}'>{letra}</div>"
            html += "</div>"
            st.markdown(html, unsafe_allow_html=True)
            c1,c2,c3 = st.columns(3)
            c1.markdown(f"<p style='color:#2ecc71; font-weight:bold; font-size:20px;'>{tend_local['rachas']['victorias']}</p>", unsafe_allow_html=True); c1.caption("G")
            c2.markdown(f"<p style='color:#f1c40f; font-weight:bold; font-size:20px;'>{tend_local['rachas']['empates']}</p>", unsafe_allow_html=True); c2.caption("E")
            c3.markdown(f"<p style='color:#e74c3c; font-weight:bold; font-size:20px;'>{tend_local['rachas']['derrotas']}</p>", unsafe_allow_html=True); c3.caption("P")
        else:
            st.info("Sin datos")
    with colt2:
        st.markdown(f"**🚀 {visitante}**")
        if tend_visit:
            html = "<div class='forma-container'>"
            for letra in tend_visit['forma']:
                html += f"<div class='forma-item forma-{letra}'>{letra}</div>"
            html += "</div>"
            st.markdown(html, unsafe_allow_html=True)
            c1,c2,c3 = st.columns(3)
            c1.markdown(f"<p style='color:#2ecc71; font-weight:bold; font-size:20px;'>{tend_visit['rachas']['victorias']}</p>", unsafe_allow_html=True); c1.caption("G")
            c2.markdown(f"<p style='color:#f1c40f; font-weight:bold; font-size:20px;'>{tend_visit['rachas']['empates']}</p>", unsafe_allow_html=True); c2.caption("E")
            c3.markdown(f"<p style='color:#e74c3c; font-weight:bold; font-size:20px;'>{tend_visit['rachas']['derrotas']}</p>", unsafe_allow_html=True); c3.caption("P")
        else:
            st.info("Sin datos")
    
    if value_analysis and value_analysis.get('mejor_value'):
        st.divider()
        v = value_analysis['mejor_value']['value']
        if v > 10:
            st.markdown(f"<div class='value-alta'><span style='font-size:24px;'>🔥 VALUE FUERTE</span><br>Apuesta por <b>{value_analysis['mejor_value']['mercado']}</b><br>Cuota: {value_analysis['mejor_value']['cuota']:.2f} | Ventaja: +{v:.1f}%</div>", unsafe_allow_html=True)
        elif v > 5:
            st.markdown(f"<div class='value-media'><span style='font-size:24px;'>💰 VALUE DETECTADO</span><br>Apuesta por <b>{value_analysis['mejor_value']['mercado']}</b><br>Cuota: {value_analysis['mejor_value']['cuota']:.2f} | Ventaja: +{v:.1f}%</div>", unsafe_allow_html=True)
    
    st.divider()
    st.subheader("🎯 TOP 5 APUESTAS MÁS SEGURAS")
    for i, ap in enumerate(apuestas_seguras[:5]):
        col = "#2ecc71" if ap['seguridad']=='ALTA' else "#f1c40f" if ap['seguridad']=='MEDIA' else "#e74c3c"
        emo = "🟢" if ap['seguridad']=='ALTA' else "🟡" if ap['seguridad']=='MEDIA' else "🔴"
        ve = calcular_valor_esperado(ap['probabilidad'], ap['cuota'])
        ca1, ca2, ca3, ca4 = st.columns([3,1,1,1])
        ca1.markdown(f"**{i+1}. {ap['nombre']}**"); ca1.caption(ap['tipo'])
        ca2.markdown(f"<p style='color:{col}; font-weight:bold; font-size:20px;'>{ap['probabilidad']:.1f}%</p>", unsafe_allow_html=True)
        ca3.markdown(f"<p style='font-size:20px;'>{emo}</p>", unsafe_allow_html=True)
        if ve > 5: ca4.markdown(f"<p style='color:#2ecc71; font-weight:bold;'>+{ve:.1f}%</p>", unsafe_allow_html=True)
        elif ve < -5: ca4.markdown(f"<p style='color:#e74c3c;'>{ve:.1f}%</p>", unsafe_allow_html=True)
        else: ca4.markdown(f"{ve:.1f}%")
    
    # ========================================================================
    # NUEVA SECCIÓN: ESTADÍSTICAS PREVISTAS MEJORADA
    # ========================================================================
    st.divider()
    st.subheader("📈 Estadísticas Previstas")
    
    # Fila 1: Métricas clásicas (corners, tarjetas, faltas)
    col_e1, col_e2, col_e3 = st.columns(3)
    with col_e1:
        st.metric("🎯 Corners", f"{pronostico.corners_total:.1f}")
    with col_e2:
        st.metric("🟨 Tarjetas", f"{pronostico.tarjetas_total:.1f}")
    with col_e3:
        st.metric("⚖️ Faltas", f"{pronostico.faltas_total:.1f}")
    
    # Fila 2: Probabilidades de anotar por mitades
    st.write("---")
    st.subheader("🎯 Probabilidad de anotar por partes")
    col_p1, col_p2 = st.columns(2)
    with col_p1:
        st.markdown(f"**{local}**")
        if prob_local_1 is not None:
            st.metric("1ª Parte", f"{prob_local_1:.1f}%")
            st.metric("2ª Parte", f"{prob_local_2:.1f}%")
        else:
            st.info("Sin datos históricos suficientes")
    with col_p2:
        st.markdown(f"**{visitante}**")
        if prob_visit_1 is not None:
            st.metric("1ª Parte", f"{prob_visit_1:.1f}%")
            st.metric("2ª Parte", f"{prob_visit_2:.1f}%")
        else:
            st.info("Sin datos históricos suficientes")
    
    # ========================================================================
    # ANÁLISIS POR MERCADOS (sin handicap, over/under reorganizado)
    # ========================================================================
    st.divider()
    st.subheader("📊 ANÁLISIS POR MERCADOS")
    tab1, tab2, tab3 = st.tabs(["1X2", "Over/Under", "Ambos Marcan"])
    
    with tab1:
        colx1, colx2, colx3 = st.columns(3)
        colx1.markdown(f"**🏠 {local}**")
        colx1.markdown(f"<p class='big-font'>{mercados['1x2']['local']:.1f}%</p>", unsafe_allow_html=True)
        colx2.markdown("**🤝 Empate**")
        colx2.markdown(f"<p class='big-font'>{mercados['1x2']['empate']:.1f}%</p>", unsafe_allow_html=True)
        colx3.markdown(f"**🚀 {visitante}**")
        colx3.markdown(f"<p class='big-font'>{mercados['1x2']['visitante']:.1f}%</p>", unsafe_allow_html=True)
    
    with tab2:
        # Mostrar Over y Under en dos columnas
        ou_items = list(mercados['over_under'].items())
        # Separar Over y Under
        over_items = [(k, v) for k, v in ou_items if k.startswith('Over')]
        under_items = [(k, v) for k, v in ou_items if k.startswith('Under')]
        # Ordenar Over por número ascendente (0.5,1.5,2.5,3.5)
        over_items.sort(key=lambda x: float(x[0].split()[1]))
        under_items.sort(key=lambda x: float(x[0].split()[1]))
        
        col_over, col_under = st.columns(2)
        with col_over:
            st.markdown("**Over**")
            for nom, prob in over_items:
                st.markdown(f"{nom}: **{prob:.1f}%**")
        with col_under:
            st.markdown("**Under**")
            for nom, prob in under_items:
                st.markdown(f"{nom}: **{prob:.1f}%**")
    
    with tab3:
        cb1, cb2 = st.columns(2)
        cb1.markdown("**✅ SI**")
        cb1.markdown(f"<p class='big-font'>{mercados['ambos_marcan']['Si']:.1f}%</p>", unsafe_allow_html=True)
        cb2.markdown("**❌ NO**")
        cb2.markdown(f"<p class='big-font'>{mercados['ambos_marcan']['No']:.1f}%</p>", unsafe_allow_html=True)
    
    # ========================================================================
    # RESTO DE SECCIONES (sin cambios)
    # ========================================================================
    
    st.divider()
    st.subheader("🎯 Probabilidad de anotar")
    cg1,cg2,cg3 = st.columns([2,2,1])
    with cg1:
        st.markdown(f"**{local}**")
        st.markdown(f"<p class='{'green-big' if pronostico.prob_local_1>75 else 'big-font'}'>{pronostico.prob_local_1:.1f}%</p>", unsafe_allow_html=True)
    with cg2:
        st.markdown(f"**{visitante}**")
        st.markdown(f"<p class='{'green-big' if pronostico.prob_visitante_1>75 else 'big-font'}'>{pronostico.prob_visitante_1:.1f}%</p>", unsafe_allow_html=True)
    with cg3:
        fiab, colf, tip = pronostico.get_fiabilidad()
        st.markdown("**Fiabilidad**")
        st.markdown(f"<p style='color:{colf}; font-weight:bold;'>{fiab}</p>", unsafe_allow_html=True)
        st.caption(tip)
    
    st.divider()
    st.subheader("🔙 Historial")
    h2h = obtener_historial_h2h(df_total, local, visitante)
    if not h2h.empty:
        for _, p in h2h.iterrows():
            fecha = p['Date'].strftime('%d/%m/%Y') if pd.notna(p['Date']) else '?'
            gl = int(p['FTHG']); gv = int(p['FTAG'])
            if gl > gv: res = "🏠" if p['HomeTeam']==local else "🚀"
            elif gl < gv: res = "🚀" if p['HomeTeam']==local else "🏠"
            else: res = "🤝"
            corners = int(p.get('HC',0)+p.get('AC',0))
            tarjetas = int(p.get('HY',0)+p.get('AY',0)+p.get('HR',0)+p.get('AR',0))
            cuo = ""
            for casa in ['B365','PS','WH']:
                if f'{casa}H' in p and pd.notna(p[f'{casa}H']):
                    cuo = f" | Cuota: {p[f'{casa}H']:.2f}"
                    break
            st.markdown(f"📅 {fecha} {res} | **{p['HomeTeam']} {gl}-{gv} {p['AwayTeam']}** | 🎯 {corners} | 🟨 {tarjetas}{cuo}")
    else:
        st.info("Sin historial")
    
    st.divider()
    col_e1, col_e2 = st.columns(2)
    with col_e1:
        data = {
            'Fecha': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'Local': local, 'Visitante': visitante,
            'Prob_Local': round(pronostico.p_win,1),
            'Prob_Empate': round(pronostico.p_draw,1),
            'Prob_Visitante': round(pronostico.p_lose,1),
            'Over_2.5': round(pronostico.prob_over_25,1),
            'Ambos_Marcan': round(pronostico.prob_ambos,1),
            'Confianza_IA': rating
        }
        df_exp = pd.DataFrame([data])
        csv = df_exp.to_csv(index=False)
        st.download_button("📥 Exportar CSV", data=csv, file_name=f"pronostico_{local}_vs_{visitante}.csv", mime="text/csv", use_container_width=True)
    with col_e2:
        if st.button("🔄 Nuevo Pronóstico", use_container_width=True):
            st.rerun()

if __name__ == "__main__":
    main()
