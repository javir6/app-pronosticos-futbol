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
    """Detecta si es dispositivo móvil por el user agent"""
    try:
        user_agent = st.query_params.get("user_agent", [""])
        mobile_keywords = ['mobile', 'android', 'iphone', 'ipad']
        return any(keyword in str(user_agent).lower() for keyword in mobile_keywords)
    except:
        return False

# Configuración responsive
ES_MOVIL = detectar_movil()

st.set_page_config(
    page_title="⚽ Asistente de Apuestas IA - Fútbol Profesional",
    page_icon="⚽",
    layout="centered" if ES_MOVIL else "wide",
    initial_sidebar_state="collapsed" if ES_MOVIL else "expanded"
)

# Estilos personalizados mejorados
st.markdown("""
<style>
    .big-font { font-size:26px !important; font-weight: bold; }
    .green-big { color: #2ecc71; font-size:26px !important; font-weight: bold; }
    .red-big { color: #e74c3c; font-size:26px !important; font-weight: bold; }
    .yellow-big { color: #f1c40f; font-size:26px !important; font-weight: bold; }
    .info-box { padding: 1rem; border-radius: 0.5rem; background-color: #f0f2f6; }
    .stButton>button { width: 100%; }
    
    /* Estilos para value bets */
    .value-alta { 
        background: linear-gradient(90deg, #27ae60 0%, #2ecc71 100%);
        color: white; 
        padding: 15px; 
        border-radius: 10px; 
        margin: 10px 0;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .value-media { 
        background: linear-gradient(90deg, #f39c12 0%, #f1c40f 100%);
        color: white; 
        padding: 15px; 
        border-radius: 10px; 
        margin: 10px 0;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .value-baja { 
        background: linear-gradient(90deg, #e74c3c 0%, #c0392b 100%);
        color: white; 
        padding: 15px; 
        border-radius: 10px; 
        margin: 10px 0;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    
    /* Tarjetas de partido */
    .partido-card {
        background-color: #f8f9fa;
        padding: 15px;
        border-radius: 10px;
        border-left: 5px solid #3498db;
        margin: 10px 0;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    
    /* Alertas */
    .alerta-card {
        padding: 15px;
        border-radius: 10px;
        margin: 10px 0;
        font-weight: bold;
    }
    .alerta-roja { background-color: #ffebee; border-left: 5px solid #c62828; }
    .alerta-verde { background-color: #e8f5e9; border-left: 5px solid #2e7d32; }
    .alerta-amarilla { background-color: #fff8e1; border-left: 5px solid #ff8f00; }
    
    /* Mejoras para móvil */
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
    """Clase que encapsula toda la lógica de pronósticos"""
    
    def __init__(self, df_local, df_visitante, local, visitante, num_partidos=20):
        self.df_local = df_local.tail(num_partidos)
        self.df_visitante = df_visitante.tail(num_partidos)
        self.local = local
        self.visitante = visitante
        self.num_partidos = num_partidos
        self.calcular_todo()
    
    def calcular_todo(self):
        """Calcula todas las métricas necesarias"""
        self.media_local = self._calcular_media_goles(self.df_local, self.local, 'local')
        self.media_visitante = self._calcular_media_goles(self.df_visitante, self.visitante, 'visitante')
        self.media_total = self.media_local + self.media_visitante
        
        # Probabilidades de goles
        self.prob_local_1 = (1 - poisson.pmf(0, self.media_local)) * 100
        self.prob_visitante_1 = (1 - poisson.pmf(0, self.media_visitante)) * 100
        self.prob_ambos = (self.prob_local_1/100 * self.prob_visitante_1/100) * 100
        self.prob_over_25 = (1 - poisson.cdf(2, self.media_total)) * 100
        self.prob_under_25 = poisson.cdf(2, self.media_total) * 100
        
        # Matriz de probabilidades para resultado
        self.matriz, self.p_win, self.p_draw, self.p_lose = self._calcular_matriz()
        
        # Estadísticas adicionales
        self.corners_total = self._calcular_media_estadistica('HC', 'AC')
        self.tarjetas_total = self._calcular_media_estadistica(['HY', 'HR'], ['AY', 'AR'])
        self.faltas_total = self._calcular_media_estadistica('HF', 'AF')
    
    def _calcular_media_goles(self, df, equipo, condicion):
        """Calcula media de goles con manejo de outliers"""
        if condicion == 'local':
            mask = df['HomeTeam'] == equipo
            goles = df.loc[mask, 'FTHG']
        else:
            mask = df['AwayTeam'] == equipo
            goles = df.loc[mask, 'FTAG']
        
        if len(goles) < 3:
            return goles.mean() if not goles.empty else 0.0
        
        # Eliminar outliers (goles > 5)
        goles_sin_outliers = goles[goles <= 5]
        return goles_sin_outliers.mean() if not goles_sin_outliers.empty else goles.mean()
    
    def _calcular_media_estadistica(self, col_local, col_visitante):
        """Calcula medias para estadísticas del partido"""
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
        
        return max(0, total)  # No negativos
    
    def _calcular_matriz(self):
        """Calcula matriz de probabilidades Poisson"""
        p_local = [poisson.pmf(i, self.media_local) for i in range(8)]
        p_visitante = [poisson.pmf(i, self.media_visitante) for i in range(8)]
        matriz = np.outer(p_local, p_visitante)
        
        p_win = np.sum(np.tril(matriz, -1))
        p_draw = np.diag(matriz).sum()
        p_lose = np.sum(np.triu(matriz, 1))
        
        return matriz, p_win * 100, p_draw * 100, p_lose * 100
    
    def get_fiabilidad(self):
        """Determina la fiabilidad del pronóstico basado en muestras"""
        muestras = len(self.df_local) + len(self.df_visitante)
        if muestras > 35:
            return "ALTA", "#2ecc71", "✅ Muestra muy representativa"
        elif muestras > 20:
            return "MEDIA", "#f1c40f", "⚠️ Muestra aceptable"
        else:
            return "BAJA", "#e74c3c", "❌ Pocos datos, usar con precaución"
    
    def get_marcador_sugerido(self):
        """Obtiene el marcador más probable"""
        idx_max = np.unravel_index(np.argmax(self.matriz), self.matriz.shape)
        prob_max = self.matriz[idx_max] * 100
        return idx_max[0], idx_max[1], prob_max

# ============================================================================
# FUNCIONES DE CARGA Y PROCESAMIENTO DE DATOS
# ============================================================================

@st.cache_data(ttl=3600)
def cargar_datos():
    """Carga los datos del CSV con caché"""
    try:
        if not os.path.exists("datos_historicos.csv"):
            return pd.DataFrame()
        
        df = pd.read_csv("datos_historicos.csv")
        df['Date'] = pd.to_datetime(df['Date'], dayfirst=True, errors='coerce')
        df['HomeTeam'] = df['HomeTeam'].str.strip()
        df['AwayTeam'] = df['AwayTeam'].str.strip()
        
        # Eliminar filas sin goles
        df = df.dropna(subset=['FTHG', 'FTAG'])
        return df
    except Exception as e:
        st.error(f"Error cargando datos: {e}")
        return pd.DataFrame()

def actualizar_csv(progreso_bar, status_text):
    """Actualiza la base de datos con progreso detallado"""
    temporadas = ['2526', '2425', '2324']
    ligas = ["SP1", "SP2", "E0", "E1", "I1", "D1", "F1", "P1"]
    
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
                    cols = ['Date', 'HomeTeam', 'AwayTeam', 'FTHG', 'FTAG', 'FTR', 'Div',
                           'HC', 'AC', 'HF', 'AF', 'HY', 'AY', 'HR', 'AR',
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
        with error_container.expander(f"⚠️ Ver detalles de errores ({len(errores)} archivos)"):
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
    """Obtiene el historial entre dos equipos"""
    mask = ((df['HomeTeam'] == local) & (df['AwayTeam'] == visitante)) | \
           ((df['HomeTeam'] == visitante) & (df['AwayTeam'] == local))
    return df[mask].sort_values('Date', ascending=False).head(limite)

def crear_grafico_tendencias(df, equipo):
    """Crea gráfico de tendencias de goles"""
    datos_goles = []
    
    for _, row in df.iterrows():
        if row['HomeTeam'] == equipo:
            datos_goles.append({
                'fecha': row['Date'],
                'goles': row['FTHG'],
                'condicion': 'Local',
                'rival': row['AwayTeam']
            })
        elif row['AwayTeam'] == equipo:
            datos_goles.append({
                'fecha': row['Date'],
                'goles': row['FTAG'],
                'condicion': 'Visitante',
                'rival': row['HomeTeam']
            })
    
    if datos_goles:
        df_goles = pd.DataFrame(datos_goles)
        df_goles = df_goles.sort_values('fecha').tail(15)
        
        fig = px.line(df_goles, x='fecha', y='goles', color='condicion',
                     title=f"📈 Tendencia de {equipo} (últimos 15 partidos)",
                     markers=True, hover_data={'rival': True, 'goles': True, 'fecha': False})
        
        fig.update_layout(hovermode='x unified', showlegend=True, height=400)
        return fig
    return None

# ============================================================================
# FUNCIONES DE ANÁLISIS AVANZADO
# ============================================================================

def calcular_probabilidades_todos_mercados(pronostico):
    """Calcula probabilidades para diferentes mercados de apuestas"""
    mercados = {}
    
    # Mercado 1X2
    mercados['1x2'] = {
        'local': pronostico.p_win,
        'empate': pronostico.p_draw,
        'visitante': pronostico.p_lose
    }
    
    # Mercado: Doble oportunidad
    mercados['doble_oportunidad'] = {
        '1X': pronostico.p_win + pronostico.p_draw,
        '12': pronostico.p_win + pronostico.p_lose,
        'X2': pronostico.p_draw + pronostico.p_lose
    }
    
    # Mercado: Over/Under
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
    
    # Mercado: Ambos marcan
    mercados['ambos_marcan'] = {
        'Si': pronostico.prob_ambos,
        'No': 100 - pronostico.prob_ambos
    }
    
    # Mercado: Goles exactos
    mercados['goles_exactos'] = {}
    for goles in range(7):
        mercados['goles_exactos'][f'Exactly {goles}'] = poisson.pmf(goles, pronostico.media_total) * 100
    
    # Mercado: Handicap asiático
    mercados['handicap'] = {
        'Local -0.5': pronostico.p_win,
        'Visitante +0.5': pronostico.p_draw + pronostico.p_lose,
        'Visitante -0.5': pronostico.p_lose,
        'Local +0.5': pronostico.p_win + pronostico.p_draw
    }
    
    return mercados

def encontrar_mejores_cuotas(df_partido):
    """Encuentra las mejores cuotas disponibles de todas las casas"""
    cuotas = {}
    
    if df_partido.empty:
        return None
    
    ultima_fila = df_partido.iloc[0] if not df_partido.empty else None
    
    mapping = {
        'local': ['B365H', 'PSH', 'WHH', 'VCH', 'MaxH'],
        'empate': ['B365D', 'PSD', 'WHD', 'VCD', 'MaxD'],
        'visitante': ['B365A', 'PSA', 'WHA', 'VCA', 'MaxA']
    }
    
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
            cuotas[mercado] = {
                'cuota': mejor_cuota,
                'casa': mejor_casa,
                'prob_implícita': 1 / mejor_cuota * 100,
                'tipo': 'real'
            }
    
    return cuotas if cuotas else None

def calcular_valor_esperado(prob_real, cuota):
    """Calcula el Valor Esperado de una apuesta"""
    if cuota <= 0 or prob_real <= 0:
        return -100
    valor_esperado = (prob_real / 100 * cuota) - 1
    return valor_esperado * 100

def recomendar_apuesta_segura(pronostico, cuotas_disponibles):
    """Encuentra la apuesta más segura basada en probabilidad real"""
    todas_apuestas = []
    
    # Apuestas 1X2
    todas_apuestas.append({
        'nombre': f'Local: {pronostico.local}',
        'tipo': '1X2', 'mercado': 'Local',
        'probabilidad': pronostico.p_win,
        'cuota': cuotas_disponibles.get('local', {}).get('cuota', 1.0) if cuotas_disponibles else 1.0,
        'seguridad': 'ALTA' if pronostico.p_win > 60 else 'MEDIA' if pronostico.p_win > 45 else 'BAJA'
    })
    
    todas_apuestas.append({
        'nombre': 'Empate',
        'tipo': '1X2', 'mercado': 'Empate',
        'probabilidad': pronostico.p_draw,
        'cuota': cuotas_disponibles.get('empate', {}).get('cuota', 1.0) if cuotas_disponibles else 1.0,
        'seguridad': 'ALTA' if pronostico.p_draw > 60 else 'MEDIA' if pronostico.p_draw > 45 else 'BAJA'
    })
    
    todas_apuestas.append({
        'nombre': f'Visitante: {pronostico.visitante}',
        'tipo': '1X2', 'mercado': 'Visitante',
        'probabilidad': pronostico.p_lose,
        'cuota': cuotas_disponibles.get('visitante', {}).get('cuota', 1.0) if cuotas_disponibles else 1.0,
        'seguridad': 'ALTA' if pronostico.p_lose > 60 else 'MEDIA' if pronostico.p_lose > 45 else 'BAJA'
    })
    
    # Over/Under
    todas_apuestas.append({
        'nombre': 'Over 2.5', 'tipo': 'Totales', 'mercado': 'Over 2.5',
        'probabilidad': pronostico.prob_over_25, 'cuota': 2.0,
        'seguridad': 'ALTA' if pronostico.prob_over_25 > 65 else 'MEDIA' if pronostico.prob_over_25 > 50 else 'BAJA'
    })
    
    todas_apuestas.append({
        'nombre': 'Under 2.5', 'tipo': 'Totales', 'mercado': 'Under 2.5',
        'probabilidad': pronostico.prob_under_25, 'cuota': 1.9,
        'seguridad': 'ALTA' if pronostico.prob_under_25 > 65 else 'MEDIA' if pronostico.prob_under_25 > 50 else 'BAJA'
    })
    
    # Ambos marcan
    todas_apuestas.append({
        'nombre': 'Ambos marcan - SI', 'tipo': 'Ambos Marcan', 'mercado': 'Si',
        'probabilidad': pronostico.prob_ambos, 'cuota': 1.95,
        'seguridad': 'ALTA' if pronostico.prob_ambos > 65 else 'MEDIA' if pronostico.prob_ambos > 50 else 'BAJA'
    })
    
    todas_apuestas.append({
        'nombre': 'Ambos marcan - NO', 'tipo': 'Ambos Marcan', 'mercado': 'No',
        'probabilidad': 100 - pronostico.prob_ambos, 'cuota': 1.85,
        'seguridad': 'ALTA' if (100 - pronostico.prob_ambos) > 65 else 'MEDIA' if (100 - pronostico.prob_ambos) > 50 else 'BAJA'
    })
    
    todas_apuestas.sort(key=lambda x: x['probabilidad'], reverse=True)
    return todas_apuestas

def generar_combinadas_inteligentes(pronostico):
    """Genera combinadas óptimas basadas en altas probabilidades"""
    combinadas = []
    
    if pronostico.p_win > 55 and pronostico.prob_over_25 > 55:
        prob_conjunta = (pronostico.p_win / 100) * (pronostico.prob_over_25 / 100) * 100
        combinadas.append({
            'nombre': 'Local gana + Over 2.5',
            'apuestas': [f'Gana {pronostico.local}', 'Over 2.5'],
            'probabilidad': prob_conjunta, 'cuota_estimada': 3.5,
            'seguridad': 'ALTA' if prob_conjunta > 35 else 'MEDIA'
        })
    
    if pronostico.p_draw > 30 and pronostico.prob_under_25 > 60:
        prob_1X = (pronostico.p_win + pronostico.p_draw) / 100
        prob_conjunta = prob_1X * (pronostico.prob_under_25 / 100) * 100
        combinadas.append({
            'nombre': 'Local o Empate + Under 2.5',
            'apuestas': ['1X (Local o Empate)', 'Under 2.5'],
            'probabilidad': prob_conjunta, 'cuota_estimada': 2.8,
            'seguridad': 'ALTA' if prob_conjunta > 40 else 'MEDIA'
        })
    
    if pronostico.prob_ambos > 60 and pronostico.prob_over_25 > 60:
        prob_conjunta = (pronostico.prob_ambos / 100) * (pronostico.prob_over_25 / 100) * 100
        combinadas.append({
            'nombre': 'Ambos marcan + Over 2.5',
            'apuestas': ['Ambos marcan - SI', 'Over 2.5'],
            'probabilidad': prob_conjunta, 'cuota_estimada': 3.2,
            'seguridad': 'ALTA' if prob_conjunta > 40 else 'MEDIA'
        })
    
    if pronostico.p_draw > 35 and pronostico.prob_under_25 > 65:
        prob_conjunta = (pronostico.p_draw / 100) * (pronostico.prob_under_25 / 100) * 100
        combinadas.append({
            'nombre': 'Empate + Under 2.5',
            'apuestas': ['Empate', 'Under 2.5'],
            'probabilidad': prob_conjunta, 'cuota_estimada': 4.0,
            'seguridad': 'MEDIA'
        })
    
    combinadas.sort(key=lambda x: x['probabilidad'], reverse=True)
    return combinadas

def calcular_rating_confianza(pronostico):
    """Calcula un rating de confianza global (0-100)"""
    rating = 0
    
    muestras = len(pronostico.df_local) + len(pronostico.df_visitante)
    if muestras > 35: rating += 30
    elif muestras > 20: rating += 20
    else: rating += 10
    
    max_prob = max(pronostico.p_win, pronostico.p_draw, pronostico.p_lose)
    if max_prob > 60: rating += 30
    elif max_prob > 50: rating += 20
    else: rating += 10
    
    over_under_diff = abs(pronostico.prob_over_25 - pronostico.prob_under_25)
    if over_under_diff > 30: rating += 20
    elif over_under_diff > 15: rating += 15
    else: rating += 5
    
    ambos_diff = abs(pronostico.prob_ambos - 50)
    if ambos_diff > 25: rating += 20
    elif ambos_diff > 10: rating += 15
    else: rating += 5
    
    return min(rating, 100)

def analizar_value_bets(pronostico, cuotas_disponibles):
    """Analiza si hay value bets según las mejores cuotas disponibles"""
    resultados = {}
    
    if not cuotas_disponibles:
        return None
    
    for mercado in ['local', 'empate', 'visitante']:
        if mercado in cuotas_disponibles:
            prob_real = getattr(pronostico, f'p_win' if mercado == 'local' else f'p_draw' if mercado == 'empate' else f'p_lose')
            value = prob_real - cuotas_disponibles[mercado]['prob_implícita']
            
            resultados[mercado] = {
                'value': value,
                'es_value': value > 5,
                'cuota': cuotas_disponibles[mercado]['cuota'],
                'casa': cuotas_disponibles[mercado]['casa'],
                'prob_impl': cuotas_disponibles[mercado]['prob_implícita'],
                'prob_real': prob_real
            }
    
    valores = [r['value'] for r in resultados.values() if r['value'] > 3]
    if valores:
        max_value = max(valores)
        for mercado, datos in resultados.items():
            if datos['value'] == max_value:
                resultados['mejor_value'] = {
                    'mercado': mercado,
                    'value': max_value,
                    'cuota': datos['cuota']
                }
                break
    else:
        resultados['mejor_value'] = None
    
    return resultados

def analizar_ligas(df_total):
    """Analiza qué ligas tienen mejores oportunidades"""
    if 'Div' not in df_total.columns:
        return pd.DataFrame()
    
    ligas_dict = {
        'SP1': 'La Liga', 'SP2': 'La Liga 2', 'E0': 'Premier',
        'E1': 'Championship', 'I1': 'Serie A', 'D1': 'Bundesliga',
        'F1': 'Ligue 1', 'P1': 'Liga Portugal'
    }
    
    stats_ligas = []
    for codigo, nombre in ligas_dict.items():
        df_liga = df_total[df_total['Div'] == codigo]
        if not df_liga.empty and len(df_liga) > 10:
            media_goles = (df_liga['FTHG'].mean() + df_liga['FTAG'].mean()) / 2
            stats_ligas.append({
                'Liga': nombre,
                'Partidos': len(df_liga),
                'Media Goles': round(media_goles, 2),
                'Over 2.5 %': round((df_liga['FTHG'] + df_liga['FTAG'] > 2.5).mean() * 100, 1)
            })
    
    return pd.DataFrame(stats_ligas).sort_values('Over 2.5 %', ascending=False)

def check_alertas(pronostico, cuotas_disponibles, value_analysis):
    """Verifica si hay condiciones para alertar"""
    alertas = []
    
    if cuotas_disponibles and value_analysis and value_analysis['mejor_value']:
        if value_analysis['mejor_value']['value'] > 10:
            alertas.append({
                'tipo': '🔴 VALUE BET FUERTE',
                'mensaje': f"{value_analysis['mejor_value']['mercado']} con +{value_analysis['mejor_value']['value']:.1f}%"
            })
    
    max_prob = max(pronostico.p_win, pronostico.p_draw, pronostico.p_lose)
    if max_prob > 70:
        alertas.append({
            'tipo': '🎯 FAVORITO CLARO',
            'mensaje': f"{max_prob:.1f}% de probabilidad"
        })
    
    if pronostico.prob_over_25 > 75:
        alertas.append({
            'tipo': '⚽ MUCHOS GOLES',
            'mensaje': f"Over 2.5 al {pronostico.prob_over_25:.1f}%"
        })
    
    if pronostico.prob_ambos > 75:
        alertas.append({
            'tipo': '🥅 AMBOS MARCAN SEGURO',
            'mensaje': f"{pronostico.prob_ambos:.1f}% de probabilidad"
        })
    
    return alertas

def analizar_tendencias_equipo(df, equipo):
    """Análisis detallado de forma reciente"""
    partidos_recientes = df[(df['HomeTeam'] == equipo) | (df['AwayTeam'] == equipo)].tail(10)
    
    if partidos_recientes.empty:
        return None
    
    resultados = []
    for _, p in partidos_recientes.iterrows():
        if p['HomeTeam'] == equipo:
            if p['FTHG'] > p['FTAG']: resultados.append('G')
            elif p['FTHG'] < p['FTAG']: resultados.append('P')
            else: resultados.append('E')
        else:
            if p['FTAG'] > p['FTHG']: resultados.append('G')
            elif p['FTAG'] < p['FTHG']: resultados.append('P')
            else: resultados.append('E')
    
    return {
        'forma': ''.join(resultados),
        'rachas': {
            'victorias': resultados.count('G'),
            'empates': resultados.count('E'),
            'derrotas': resultados.count('P')
        }
    }

# ============================================================================
# INTERFAZ PRINCIPAL
# ============================================================================

def main():
    """Función principal de la aplicación"""
    
    # Inicializar session state para favoritos
    if 'favoritos' not in st.session_state:
        st.session_state.favoritos = []
    
    # Título
    st.title("⚽ ASISTENTE DE APUESTAS IA - FÚTBOL PROFESIONAL")
    
    with st.expander("ℹ️ ¿Cómo funciona?", expanded=False):
        st.markdown("""
        ### 🎯 **Sistema Experto de Apuestas**
        
        #### 📊 Modelo Estadístico Poisson
        - Calcula probabilidades basadas en media de goles real
        - Análisis de últimos 20 partidos por equipo
        - Eliminación automática de outliers
        
        #### 🤖 **IA y Machine Learning**
        - **Value Bet Detection**: Identifica cuotas infravaloradas
        - **Rating de Confianza**: Puntuación 0-100 sobre la fiabilidad
        - **Alertas automáticas**: Notificaciones de oportunidades
        
        #### 🔥 **Value Bet**
        - **+5% de ventaja**: Apuesta con valor positivo
        - Basado en comparación con mejores cuotas del mercado
        """)
    
    # Cargar datos
    df_total = cargar_datos()
    
    if df_total.empty:
        st.warning("⚠️ No hay datos disponibles. Pulsa 'Actualizar Base de Datos' en el menú lateral.")
        with st.sidebar:
            if st.button("🔄 Actualizar Base de Datos", use_container_width=True):
                with st.spinner("Actualizando datos..."):
                    progreso = st.progress(0)
                    status = st.empty()
                    exito, num_registros, errores = actualizar_csv(progreso, status)
                    if exito:
                        st.success(f"✅ ¡Actualizado! {num_registros} registros")
                        st.cache_data.clear()
                        time.sleep(1)
                        st.rerun()
        return
    
    # Obtener equipos
    equipos = sorted(set(df_total['HomeTeam'].unique()) | set(df_total['AwayTeam'].unique()))
    
    # ========================================================================
    # BARRA LATERAL MEJORADA
    # ========================================================================
    
    with st.sidebar:
        st.header("⚙️ CONFIGURACIÓN")
        
        # Indicador de cuotas disponibles
        equipos_con_cuotas = []
        for eq in equipos[:30]:
            h2h_temp = obtener_historial_h2h(df_total, eq, eq)
            if not h2h_temp.empty:
                tiene_cuotas = any(col in h2h_temp.columns and not h2h_temp[col].isna().all() 
                                  for col in ['B365H', 'PSH', 'WHH'])
                if tiene_cuotas:
                    equipos_con_cuotas.append(eq)
        
        st.info(f"📊 {len(equipos_con_cuotas)} equipos con cuotas históricas")
        
        # Parámetros de análisis
        num_partidos = st.slider("📊 Partidos a analizar", 5, 50, 20, 5)
        mostrar_graficos = st.checkbox("📈 Mostrar gráficos", value=True)
        
        st.divider()
        
        # Sistema de favoritos
        st.header("⭐ MIS FAVORITOS")
        nuevo_fav = st.selectbox("Añadir equipo favorito", equipos, key='nuevo_fav')
        if st.button("➕ Añadir a favoritos", use_container_width=True):
            if nuevo_fav not in st.session_state.favoritos:
                st.session_state.favoritos.append(nuevo_fav)
                st.success(f"✅ {nuevo_fav} añadido")
        
        if st.session_state.favoritos:
            st.write("**Tus equipos:**")
            for fav in st.session_state.favoritos:
                col_f1, col_f2 = st.columns([3, 1])
                with col_f1:
                    st.write(f"• {fav}")
                with col_f2:
                    if st.button("❌", key=f"del_{fav}"):
                        st.session_state.favoritos.remove(fav)
                        st.rerun()
        
        st.divider()
        
        # Estadísticas por liga
        st.header("📊 ESTADÍSTICAS POR LIGA")
        df_ligas = analizar_ligas(df_total)
        if not df_ligas.empty:
            st.dataframe(df_ligas, use_container_width=True, height=200)
        
        st.divider()
        
        # Botón de actualización
        if st.button("🔄 Actualizar Base de Datos", use_container_width=True):
            with st.spinner("Actualizando datos..."):
                progreso = st.progress(0)
                status = st.empty()
                exito, num_registros, errores = actualizar_csv(progreso, status)
                if exito:
                    st.success(f"✅ ¡Actualizado! {num_registros} registros")
                    st.cache_data.clear()
                    time.sleep(1)
                    st.rerun()
        
        st.caption(f"📱 Modo: {'Móvil' if ES_MOVIL else 'Escritorio'}")
        st.caption(f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    
    # ========================================================================
    # SELECCIÓN DE EQUIPOS
    # ========================================================================
    
    # Si hay favoritos, dar opción de filtrar
    if st.session_state.favoritos:
        filtrar_fav = st.checkbox("⭐ Solo mostrar favoritos")
        if filtrar_fav:
            equipos_display = st.session_state.favoritos
        else:
            equipos_display = equipos
    else:
        equipos_display = equipos
    
    col1, col2 = st.columns(2)
    with col1:
        local = st.selectbox("🏠 Equipo Local", equipos_display, index=0)
    with col2:
        idx_visit = min(1, len(equipos_display)-1) if len(equipos_display) > 1 else 0
        visitante = st.selectbox("🚀 Equipo Visitante", equipos_display, index=idx_visit)
    
    # ========================================================================
    # ANÁLISIS DEL PARTIDO
    # ========================================================================
    
    d_local = df_total[(df_total['HomeTeam'] == local) | (df_total['AwayTeam'] == local)]
    d_visitante = df_total[(df_total['HomeTeam'] == visitante) | (df_total['AwayTeam'] == visitante)]
    
    if d_local.empty or d_visitante.empty:
        st.error("No hay suficientes datos para estos equipos")
        return
    
    # Crear pronóstico
    pronostico = PronosticadorFutbol(d_local, d_visitante, local, visitante, num_partidos)
    
    # Análisis de tendencias
    tendencia_local = analizar_tendencias_equipo(d_local, local)
    tendencia_visit = analizar_tendencias_equipo(d_visitante, visitante)
    
    # Obtener cuotas y análisis
    h2h_cuotas = obtener_historial_h2h(df_total, local, visitante, limite=1)
    cuotas_disponibles = encontrar_mejores_cuotas(h2h_cuotas) if not h2h_cuotas.empty else None
    
    mercados = calcular_probabilidades_todos_mercados(pronostico)
    apuestas_seguras = recomendar_apuesta_segura(pronostico, cuotas_disponibles)
    combinadas = generar_combinadas_inteligentes(pronostico)
    rating_confianza = calcular_rating_confianza(pronostico)
    value_analysis = analizar_value_bets(pronostico, cuotas_disponibles)
    alertas = check_alertas(pronostico, cuotas_disponibles, value_analysis)
    
    # ========================================================================
    # ALERTAS
    # ========================================================================
    
    if alertas:
        st.divider()
        st.subheader("🚨 ALERTAS DEL PARTIDO")
        for alerta in alertas:
            if "VALUE" in alerta['tipo']:
                st.markdown(f"""
                <div class="alerta-verde alerta-card">
                    <span style="font-size:20px;">{alerta['tipo']}</span><br>
                    {alerta['mensaje']}
                </div>
                """, unsafe_allow_html=True)
            elif "FAVORITO" in alerta['tipo']:
                st.markdown(f"""
                <div class="alerta-amarilla alerta-card">
                    <span style="font-size:20px;">{alerta['tipo']}</span><br>
                    {alerta['mensaje']}
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div class="alerta-verde alerta-card">
                    <span style="font-size:20px;">{alerta['tipo']}</span><br>
                    {alerta['mensaje']}
                </div>
                """, unsafe_allow_html=True)
    
    # ========================================================================
    # MÉTRICAS PRINCIPALES
    # ========================================================================
    
    st.divider()
    cols_metricas = st.columns(4)
    
    with cols_metricas[0]:
        st.subheader("🎯 Marcador")
        g_local, g_visit, prob_max = pronostico.get_marcador_sugerido()
        st.markdown(f"<h1 style='color:#FF4B4B; text-align:center;'>{g_local} - {g_visit}</h1>", 
                   unsafe_allow_html=True)
        st.caption(f"Prob: {prob_max:.1f}%")
    
    with cols_metricas[1]:
        st.subheader("📊 Resultado")
        st.metric("Local", f"{pronostico.p_win:.1f}%")
        st.metric("Empate", f"{pronostico.p_draw:.1f}%")
        st.metric("Visitante", f"{pronostico.p_lose:.1f}%")
    
    with cols_metricas[2]:
        st.subheader("⚽ Goles")
        color_over = "green-big" if pronostico.prob_over_25 > 70 else "big-font"
        st.markdown(f"<p class='{color_over}'>Over 2.5: {pronostico.prob_over_25:.1f}%</p>", 
                   unsafe_allow_html=True)
        st.markdown(f"<p class='big-font'>Under 2.5: {pronostico.prob_under_25:.1f}%</p>", 
                   unsafe_allow_html=True)
    
    with cols_metricas[3]:
        st.subheader("🥅 Ambos Marcan")
        color_ambos = "green-big" if pronostico.prob_ambos > 65 else "big-font"
        st.markdown(f"<p class='{color_ambos}'>{pronostico.prob_ambos:.1f}%</p>", 
                   unsafe_allow_html=True)
    
    # ========================================================================
    # RATING DE CONFIANZA Y CUOTAS
    # ========================================================================
    
    col_r1, col_r2, col_r3 = st.columns(3)
    
    with col_r1:
        st.metric("📊 Confianza Global", f"{rating_confianza}%")
        if rating_confianza > 70:
            st.success("🔒 Confianza ALTA")
        elif rating_confianza > 50:
            st.warning("⚠️ Confianza MEDIA")
        else:
            st.error("🔓 Confianza BAJA")
    
    with col_r2:
        if cuotas_disponibles and 'local' in cuotas_disponibles:
            st.metric("💰 Mejor Cuota Local", f"{cuotas_disponibles['local']['cuota']:.2f}")
            st.caption(f"{cuotas_disponibles['local']['casa']}")
        else:
            st.metric("💰 Mejor Cuota Local", "No disponible")
    
    with col_r3:
        if cuotas_disponibles and 'visitante' in cuotas_disponibles:
            st.metric("💰 Mejor Cuota Visitante", f"{cuotas_disponibles['visitante']['cuota']:.2f}")
            st.caption(f"{cuotas_disponibles['visitante']['casa']}")
        else:
            st.metric("💰 Mejor Cuota Visitante", "No disponible")
    
    # ========================================================================
    # TENDENCIAS DE EQUIPOS
    # ========================================================================
    
    st.divider()
    st.subheader("📈 FORMA RECIENTE")
    col_t1, col_t2 = st.columns(2)
    
    with col_t1:
        st.markdown(f"**{local}**")
        if tendencia_local:
            st.markdown(f"Forma: **{tendencia_local['forma']}**")
            st.markdown(f"V: {tendencia_local['rachas']['victorias']} "
                       f"E: {tendencia_local['rachas']['empates']} "
                       f"D: {tendencia_local['rachas']['derrotas']}")
    
    with col_t2:
        st.markdown(f"**{visitante}**")
        if tendencia_visit:
            st.markdown(f"Forma: **{tendencia_visit['forma']}**")
            st.markdown(f"V: {tendencia_visit['rachas']['victorias']} "
                       f"E: {tendencia_visit['rachas']['empates']} "
                       f"D: {tendencia_visit['rachas']['derrotas']}")
    
    # ========================================================================
    # VALUE BET DESTACADO
    # ========================================================================
    
    if value_analysis and value_analysis['mejor_value']:
        st.divider()
        value = value_analysis['mejor_value']['value']
        if value > 10:
            st.markdown(f"""
            <div class="value-alta">
                <span style="font-size:24px;">🔥 VALUE BET FUERTE</span><br>
                Apuesta por <b>{value_analysis['mejor_value']['mercado']}</b><br>
                Cuota: {value_analysis['mejor_value']['cuota']:.2f} | Ventaja: +{value:.1f}%
            </div>
            """, unsafe_allow_html=True)
        elif value > 5:
            st.markdown(f"""
            <div class="value-media">
                <span style="font-size:24px;">💰 VALUE BET DETECTADO</span><br>
                Apuesta por <b>{value_analysis['mejor_value']['mercado']}</b><br>
                Cuota: {value_analysis['mejor_value']['cuota']:.2f} | Ventaja: +{value:.1f}%
            </div>
            """, unsafe_allow_html=True)
    
    # ========================================================================
    # TOP 5 APUESTAS MÁS SEGURAS
    # ========================================================================
    
    st.divider()
    st.subheader("🎯 TOP 5 - APUESTAS MÁS SEGURAS")
    
    for i, apuesta in enumerate(apuestas_seguras[:5]):
        if apuesta['seguridad'] == 'ALTA':
            color = "#2ecc71"; emoji = "🟢"
        elif apuesta['seguridad'] == 'MEDIA':
            color = "#f1c40f"; emoji = "🟡"
        else:
            color = "#e74c3c"; emoji = "🔴"
        
        ve = calcular_valor_esperado(apuesta['probabilidad'], apuesta['cuota'])
        
        col_a1, col_a2, col_a3, col_a4 = st.columns([3, 1, 1, 1])
        
        with col_a1:
            st.markdown(f"**{i+1}. {apuesta['nombre']}**")
            st.caption(f"{apuesta['tipo']}")
        
        with col_a2:
            st.markdown(f"<p style='color:{color}; font-weight:bold; font-size:20px;'>{apuesta['probabilidad']:.1f}%</p>", 
                       unsafe_allow_html=True)
        
        with col_a3:
            st.markdown(f"<p style='font-size:20px;'>{emoji}</p>", unsafe_allow_html=True)
        
        with col_a4:
            if ve > 5:
                st.markdown(f"<p style='color:#2ecc71; font-weight:bold;'>+{ve:.1f}%</p>", unsafe_allow_html=True)
            elif ve < -5:
                st.markdown(f"<p style='color:#e74c3c;'>{ve:.1f}%</p>", unsafe_allow_html=True)
            else:
                st.markdown(f"{ve:.1f}%")
    
    # ========================================================================
    # COMBINADAS RECOMENDADAS
    # ========================================================================
    
    if combinadas:
        st.divider()
        st.subheader("🔗 COMBINADAS INTELIGENTES")
        
        for i, comb in enumerate(combinadas):
            with st.expander(f"📊 Combinada {i+1}: {comb['nombre']} - Prob: {comb['probabilidad']:.1f}%"):
                col_c1, col_c2 = st.columns(2)
                with col_c1:
                    st.markdown("**Apuestas:**")
                    for apuesta in comb['apuestas']:
                        st.markdown(f"• {apuesta}")
                with col_c2:
                    st.metric("Probabilidad conjunta", f"{comb['probabilidad']:.1f}%")
                    st.metric("Cuota estimada", f"{comb['cuota_estimada']:.2f}")
    
    # ========================================================================
    # ANÁLISIS POR MERCADOS
    # ========================================================================
    
    st.divider()
    st.subheader("📊 ANÁLISIS POR MERCADOS")
    
    tab1, tab2, tab3, tab4 = st.tabs(["📊 1X2", "⚽ Over/Under", "🥅 Ambos Marcan", "📈 Handicap"])
    
    with tab1:
        col_m1, col_m2, col_m3 = st.columns(3)
        with col_m1:
            st.markdown(f"**🏠 {local}**")
            st.markdown(f"<p class='big-font'>{mercados['1x2']['local']:.1f}%</p>", unsafe_allow_html=True)
        with col_m2:
            st.markdown(f"**🤝 Empate**")
            st.markdown(f"<p class='big-font'>{mercados['1x2']['empate']:.1f}%</p>", unsafe_allow_html=True)
        with col_m3:
            st.markdown(f"**🚀 {visitante}**")
            st.markdown(f"<p class='big-font'>{mercados['1x2']['visitante']:.1f}%</p>", unsafe_allow_html=True)
    
    with tab2:
        cols_ou = st.columns(3)
        mercados_ou = list(mercados['over_under'].items())
        for i, (nombre, prob) in enumerate(mercados_ou[:6]):
            with cols_ou[i % 3]:
                st.markdown(f"**{nombre}**")
                st.markdown(f"<p class='big-font'>{prob:.1f}%</p>", unsafe_allow_html=True)
    
    with tab3:
        col_b1, col_b2 = st.columns(2)
        with col_b1:
            st.markdown(f"**✅ SI**")
            st.markdown(f"<p class='big-font'>{mercados['ambos_marcan']['Si']:.1f}%</p>", unsafe_allow_html=True)
        with col_b2:
            st.markdown(f"**❌ NO**")
            st.markdown(f"<p class='big-font'>{mercados['ambos_marcan']['No']:.1f}%</p>", unsafe_allow_html=True)
    
    with tab4:
        cols_h1, cols_h2 = st.columns(2)
        with cols_h1:
            st.metric("Local -0.5", f"{mercados['handicap']['Local -0.5']:.1f}%")
            st.metric("Local +0.5", f"{mercados['handicap']['Local +0.5']:.1f}%")
        with cols_h2:
            st.metric("Visitante -0.5", f"{mercados['handicap']['Visitante -0.5']:.1f}%")
            st.metric("Visitante +0.5", f"{mercados['handicap']['Visitante +0.5']:.1f}%")
    
    # ========================================================================
    # PROBABILIDAD DE GOL INDIVIDUAL
    # ========================================================================
    
    st.divider()
    st.subheader("🎯 Probabilidad de anotar")
    
    col_g1, col_g2, col_g3 = st.columns([2, 2, 1])
    
    with col_g1:
        color_local = "green-big" if pronostico.prob_local_1 > 75 else "big-font"
        st.markdown(f"**{local}**")
        st.markdown(f"<p class='{color_local}'>{pronostico.prob_local_1:.1f}%</p>", unsafe_allow_html=True)
    
    with col_g2:
        color_visit = "green-big" if pronostico.prob_visitante_1 > 75 else "big-font"
        st.markdown(f"**{visitante}**")
        st.markdown(f"<p class='{color_visit}'>{pronostico.prob_visitante_1:.1f}%</p>", unsafe_allow_html=True)
    
    with col_g3:
        fiabilidad, color_fiab, tooltip = pronostico.get_fiabilidad()
        st.markdown("**Fiabilidad**")
        st.markdown(f"<p style='color:{color_fiab}; font-weight:bold;'>{fiabilidad}</p>", unsafe_allow_html=True)
        st.caption(tooltip)
    
    # ========================================================================
    # ESTADÍSTICAS DEL PARTIDO
    # ========================================================================
    
    st.divider()
    st.subheader("📈 Estadísticas Previstas")
    
    col_e1, col_e2, col_e3 = st.columns(3)
    with col_e1:
        st.metric("🎯 Corners", f"{pronostico.corners_total:.1f}")
    with col_e2:
        st.metric("🟨 Tarjetas", f"{pronostico.tarjetas_total:.1f}")
    with col_e3:
        st.metric("⚖️ Faltas", f"{pronostico.faltas_total:.1f}")
    
    # ========================================================================
    # GRÁFICOS
    # ========================================================================
    
    if mostrar_graficos:
        st.divider()
        st.subheader("📊 Tendencias")
        tab_g1, tab_g2 = st.tabs([f"📈 {local}", f"📈 {visitante}"])
        
        with tab_g1:
            fig_local = crear_grafico_tendencias(d_local.tail(30), local)
            if fig_local: st.plotly_chart(fig_local, use_container_width=True)
            else: st.info("No hay suficientes datos")
        
        with tab_g2:
            fig_visit = crear_grafico_tendencias(d_visitante.tail(30), visitante)
            if fig_visit: st.plotly_chart(fig_visit, use_container_width=True)
            else: st.info("No hay suficientes datos")
    
    # ========================================================================
    # HISTORIAL H2H
    # ========================================================================
    
    st.divider()
    st.subheader("🔙 Historial Enfrentamientos")
    
    h2h = obtener_historial_h2h(df_total, local, visitante)
    
    if not h2h.empty:
        for _, partido in h2h.iterrows():
            fecha = partido['Date'].strftime('%d/%m/%Y') if pd.notna(partido['Date']) else 'Fecha?'
            goles_l = int(partido['FTHG']); goles_v = int(partido['FTAG'])
            
            if goles_l > goles_v: resultado = "🏠" if partido['HomeTeam'] == local else "🚀"
            elif goles_l < goles_v: resultado = "🚀" if partido['HomeTeam'] == local else "🏠"
            else: resultado = "🤝"
            
            corners = int(partido.get('HC', 0) + partido.get('AC', 0))
            tarjetas = int(partido.get('HY', 0) + partido.get('AY', 0) + 
                          partido.get('HR', 0) + partido.get('AR', 0))
            
            cuotas_text = ""
            for casa in ['B365', 'PS', 'WH']:
                if f'{casa}H' in partido and pd.notna(partido[f'{casa}H']):
                    cuotas_text = f" | Cuota: {partido[f'{casa}H']:.2f}"
                    break
            
            st.markdown(f"📅 {fecha} {resultado} | **{partido['HomeTeam']} {goles_l}-{goles_v} {partido['AwayTeam']}** | 🎯 {corners} | 🟨 {tarjetas}{cuotas_text}")
    else:
        st.info("No hay historial entre estos equipos")
    
    # ========================================================================
    # EXPORTAR
    # ========================================================================
    
    st.divider()
    col_exp1, col_exp2 = st.columns(2)
    
    with col_exp1:
        datos_export = {
            'Fecha': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'Local': local, 'Visitante': visitante,
            'Prob_Local': round(pronostico.p_win, 1),
            'Prob_Empate': round(pronostico.p_draw, 1),
            'Prob_Visitante': round(pronostico.p_lose, 1),
            'Over_2.5': round(pronostico.prob_over_25, 1),
            'Ambos_Marcan': round(pronostico.prob_ambos, 1),
            'Confianza_IA': rating_confianza
        }
        df_export = pd.DataFrame([datos_export])
        csv = df_export.to_csv(index=False)
        
        st.download_button("📥 Exportar CSV", data=csv, 
                          file_name=f"pronostico_{local}_vs_{visitante}.csv",
                          mime="text/csv", use_container_width=True)
    
    with col_exp2:
        if st.button("🔄 Nuevo Pronóstico", use_container_width=True):
            st.rerun()

# ============================================================================
# EJECUCIÓN
# ============================================================================

if __name__ == "__main__":
    main()
