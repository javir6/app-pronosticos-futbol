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
from io import StringIO  # <-- IMPORTANTE: Corrige el error de pandas.compat

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
    page_title="⚽ Pronósticos Fútbol Profesional",
    page_icon="⚽",
    layout="centered" if ES_MOVIL else "wide",
    initial_sidebar_state="collapsed" if ES_MOVIL else "expanded"
)

# Estilos personalizados
st.markdown("""
<style>
    .big-font { font-size:26px !important; font-weight: bold; }
    .green-big { color: #2ecc71; font-size:26px !important; font-weight: bold; }
    .red-big { color: #e74c3c; font-size:26px !important; font-weight: bold; }
    .yellow-big { color: #f1c40f; font-size:26px !important; font-weight: bold; }
    .info-box { padding: 1rem; border-radius: 0.5rem; background-color: #f0f2f6; }
    .stButton>button { width: 100%; }
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

@st.cache_data(ttl=3600)  # Cache de 1 hora
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
    """Actualiza la base de datos con progreso detallado y mejor manejo de errores"""
    temporadas = ['2526', '2425', '2324']
    ligas = ["SP1", "SP2", "E0", "E1", "I1", "D1", "F1", "P1"]
    
    total_archivos = len(temporadas) * len(ligas)
    contador = 0
    lista_dfs = []
    errores = []
    exitosos = 0
    
    # Crear un contenedor para mensajes de error detallados
    error_container = st.empty()
    
    for t in temporadas:
        for cod in ligas:
            contador += 1
            progreso = contador / total_archivos
            progreso_bar.progress(progreso)
            status_text.text(f"📥 Descargando: {t}/{cod} ({int(progreso*100)}%)")
            
            url = f"https://www.football-data.co.uk/mmz4281/{t}/{cod}.csv"
            try:
                # Añadir headers para simular un navegador
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                response = requests.get(url, timeout=10, headers=headers)
                
                if response.status_code == 200:
                    # Verificar que el contenido no está vacío
                    if len(response.text) > 100:  # Mínimo de contenido
                        df_temp = pd.read_csv(StringIO(response.text))  # <-- CORREGIDO
                        cols = ['Date', 'HomeTeam', 'AwayTeam', 'FTHG', 'FTAG', 'FTR', 
                               'HC', 'AC', 'HF', 'AF', 'HY', 'AY', 'HR', 'AR']
                        existentes = [c for c in cols if c in df_temp.columns]
                        if existentes:
                            lista_dfs.append(df_temp[existentes])
                            exitosos += 1
                    else:
                        errores.append(f"{t}/{cod} - archivo vacío")
                else:
                    errores.append(f"{t}/{cod} - HTTP {response.status_code}")
                    
            except requests.exceptions.Timeout:
                errores.append(f"{t}/{cod} - timeout")
            except requests.exceptions.ConnectionError:
                errores.append(f"{t}/{cod} - error de conexión")
            except Exception as e:
                errores.append(f"{t}/{cod} - {str(e)[:50]}")
    
    status_text.text("💾 Guardando datos...")
    
    # Mostrar resumen de errores si los hay
    if errores:
        with error_container.expander(f"⚠️ Ver detalles de errores ({len(errores)} archivos)"):
            st.write("Primeros 10 errores:")
            for err in errores[:10]:
                st.text(f"• {err}")
    
    if lista_dfs:
        # Hacer backup si existe
        if os.path.exists("datos_historicos.csv"):
            fecha = datetime.now().strftime("%Y%m%d_%H%M%S")
            os.makedirs("backups", exist_ok=True)
            try:
                os.rename("datos_historicos.csv", f"backups/backup_{fecha}.csv")
            except:
                pass  # Si no se puede renombrar, continuamos
        
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
                     markers=True,
                     hover_data={'rival': True, 'goles': True, 'fecha': False})
        
        fig.update_layout(
            hovermode='x unified',
            showlegend=True,
            height=400
        )
        
        return fig
    return None

# ============================================================================
# INTERFAZ PRINCIPAL
# ============================================================================

def main():
    """Función principal de la aplicación"""
    
    # Título y descripción
    st.title("⚽ Pronósticos de Fútbol Profesional")
    
    with st.expander("ℹ️ ¿Cómo funciona?", expanded=False):
        st.markdown("""
        ### 📊 Modelo Estadístico Poisson
        - Calcula probabilidades basadas en la media de goles de cada equipo
        - Últimos 20 partidos por defecto (configurable)
        - Elimina outliers para mayor precisión
        
        ### 🎯 Fiabilidad de los pronósticos
        - **ALTA** (🟢 >35 partidos): Muestra muy representativa
        - **MEDIA** (🟡 20-35 partidos): Tendencia fiable
        - **BAJA** (🔴 <20 partidos): Usar con precaución
        
        ### 📈 Estadísticas adicionales
        - Corners, tarjetas y faltas basadas en promedios históricos
        - Gráficos de tendencia para visualizar evolución
        """)
    
    # Barra lateral para configuración
    with st.sidebar:
        st.header("⚙️ Configuración")
        
        num_partidos = st.slider(
            "📊 Partidos a analizar",
            min_value=5,
            max_value=50,
            value=20,
            step=5,
            help="Número de partidos recientes para el cálculo"
        )
        
        mostrar_graficos = st.checkbox("📈 Mostrar gráficos", value=True)
        
        st.divider()
        
        # Botón de actualización
        if st.button("🔄 Actualizar Base de Datos", use_container_width=True):
            with st.spinner("Actualizando datos..."):
                progreso = st.progress(0)
                status = st.empty()
                
                exito, num_registros, errores = actualizar_csv(progreso, status)
                
                if exito:
                    st.success(f"✅ ¡Actualizado! {num_registros} registros")
                    if errores:
                        st.warning(f"⚠️ Fallos: {len(errores)} archivos")
                    st.cache_data.clear()
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("❌ Error en la actualización")
        
        st.divider()
        st.caption(f"📱 Modo: {'Móvil' if ES_MOVIL else 'Escritorio'}")
        st.caption(f"🕐 Última actualización: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    
    # Cargar datos
    df_total = cargar_datos()
    
    if df_total.empty:
        st.warning("⚠️ No hay datos disponibles. Pulsa 'Actualizar Base de Datos' en el menú lateral.")
        return
    
    # Obtener equipos únicos
    equipos = sorted(set(df_total['HomeTeam'].unique()) | set(df_total['AwayTeam'].unique()))
    
    # Selección de equipos
    col1, col2 = st.columns(2)
    with col1:
        local = st.selectbox("🏠 Equipo Local", equipos, index=0)
    with col2:
        visitante = st.selectbox("🚀 Equipo Visitante", equipos, index=min(1, len(equipos)-1))
    
    # Filtrar datos
    d_local = df_total[(df_total['HomeTeam'] == local) | (df_total['AwayTeam'] == local)]
    d_visitante = df_total[(df_total['HomeTeam'] == visitante) | (df_total['AwayTeam'] == visitante)]
    
    if d_local.empty or d_visitante.empty:
        st.error("No hay suficientes datos para estos equipos")
        return
    
    # Crear pronóstico
    pronostico = PronosticadorFutbol(d_local, d_visitante, local, visitante, num_partidos)
    
    # ========================================================================
    # VISUALIZACIÓN DE RESULTADOS
    # ========================================================================
    
    st.divider()
    
    # Métricas principales
    cols_metricas = st.columns(4)
    
    with cols_metricas[0]:
        st.subheader("🎯 Marcador")
        g_local, g_visit, prob_max = pronostico.get_marcador_sugerido()
        st.markdown(f"<h1 style='color:#FF4B4B; text-align:center;'>{g_local} - {g_visit}</h1>", 
                   unsafe_allow_html=True)
        st.caption(f"Probabilidad: {prob_max:.1f}%")
    
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
    
    # Probabilidades de gol individual
    st.divider()
    st.subheader("🎯 Probabilidad de anotar")
    
    col_g1, col_g2, col_g3 = st.columns([2, 2, 1])
    
    with col_g1:
        color_local = "green-big" if pronostico.prob_local_1 > 75 else "big-font"
        st.markdown(f"**{local}**")
        st.markdown(f"<p class='{color_local}'>{pronostico.prob_local_1:.1f}%</p>", 
                   unsafe_allow_html=True)
    
    with col_g2:
        color_visit = "green-big" if pronostico.prob_visitante_1 > 75 else "big-font"
        st.markdown(f"**{visitante}**")
        st.markdown(f"<p class='{color_visit}'>{pronostico.prob_visitante_1:.1f}%</p>", 
                   unsafe_allow_html=True)
    
    with col_g3:
        fiabilidad, color_fiab, tooltip = pronostico.get_fiabilidad()
        st.markdown("**Fiabilidad**")
        st.markdown(f"<p style='color:{color_fiab}; font-weight:bold;'>{fiabilidad}</p>", 
                   unsafe_allow_html=True)
        st.caption(tooltip)
    
    # Doble oportunidad
    st.divider()
    st.subheader("🛡️ Doble Oportunidad")
    
    col_d1, col_d2, col_d3 = st.columns(3)
    with col_d1:
        st.info(f"**1X:** {(pronostico.p_win + pronostico.p_draw):.1f}%")
    with col_d2:
        st.info(f"**12:** {(pronostico.p_win + pronostico.p_lose):.1f}%")
    with col_d3:
        st.info(f"**X2:** {(pronostico.p_draw + pronostico.p_lose):.1f}%")
    
    # Estadísticas del partido
    st.divider()
    st.subheader("📈 Estadísticas Previstas")
    
    col_e1, col_e2, col_e3 = st.columns(3)
    with col_e1:
        st.metric("🎯 Corners Totales", f"{pronostico.corners_total:.1f}")
    with col_e2:
        st.metric("🟨 Tarjetas", f"{pronostico.tarjetas_total:.1f}")
    with col_e3:
        st.metric("⚖️ Faltas", f"{pronostico.faltas_total:.1f}")
    
    # Gráficos de tendencia (opcional)
    if mostrar_graficos:
        st.divider()
        st.subheader("📊 Análisis de Tendencias")
        
        tab1, tab2 = st.tabs([f"📈 {local}", f"📈 {visitante}"])
        
        with tab1:
            fig_local = crear_grafico_tendencias(d_local.tail(30), local)
            if fig_local:
                st.plotly_chart(fig_local, use_container_width=True)
            else:
                st.info("No hay suficientes datos para mostrar tendencias")
        
        with tab2:
            fig_visit = crear_grafico_tendencias(d_visitante.tail(30), visitante)
            if fig_visit:
                st.plotly_chart(fig_visit, use_container_width=True)
            else:
                st.info("No hay suficientes datos para mostrar tendencias")
    
    # Historial H2H
    st.divider()
    st.subheader("🔙 Historial Enfrentamientos Directos")
    
    h2h = obtener_historial_h2h(df_total, local, visitante)
    
    if not h2h.empty:
        for _, partido in h2h.iterrows():
            fecha = partido['Date'].strftime('%d/%m/%Y') if pd.notna(partido['Date']) else 'Fecha desconocida'
            goles_l = int(partido['FTHG'])
            goles_v = int(partido['FTAG'])
            
            # Determinar resultado
            if goles_l > goles_v:
                resultado = "🏠" if partido['HomeTeam'] == local else "🚀"
            elif goles_l < goles_v:
                resultado = "🚀" if partido['HomeTeam'] == local else "🏠"
            else:
                resultado = "🤝"
            
            # Estadísticas adicionales
            corners = int(partido.get('HC', 0) + partido.get('AC', 0))
            tarjetas = int(partido.get('HY', 0) + partido.get('AY', 0) + 
                          partido.get('HR', 0) + partido.get('AR', 0))
            faltas = int(partido.get('HF', 0) + partido.get('AF', 0))
            
            st.markdown(
                f"📅 {fecha} {resultado} | "
                f"**{partido['HomeTeam']} {goles_l} - {goles_v} {partido['AwayTeam']}** | "
                f"🎯 {corners} | 🟨 {tarjetas} | ⚖️ {faltas}"
            )
    else:
        st.info("No hay enfrentamientos directos previos entre estos equipos")
    
    # Exportar pronóstico
    st.divider()
    col_export1, col_export2, _ = st.columns([1, 1, 2])
    
    with col_export1:
        # Preparar datos para exportar
        datos_export = {
            'Fecha': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'Local': local,
            'Visitante': visitante,
            'Prob_Local_%': round(pronostico.p_win, 1),
            'Prob_Empate_%': round(pronostico.p_draw, 1),
            'Prob_Visitante_%': round(pronostico.p_lose, 1),
            'Over_2.5_%': round(pronostico.prob_over_25, 1),
            'Under_2.5_%': round(pronostico.prob_under_25, 1),
            'Ambos_Marcan_%': round(pronostico.prob_ambos, 1),
            'Local_Marca_%': round(pronostico.prob_local_1, 1),
            'Visitante_Marca_%': round(pronostico.prob_visitante_1, 1),
            'Corners_Estimados': round(pronostico.corners_total, 1),
            'Tarjetas_Estimadas': round(pronostico.tarjetas_total, 1),
            'Faltas_Estimadas': round(pronostico.faltas_total, 1),
            'Fiabilidad': fiabilidad
        }
        
        df_export = pd.DataFrame([datos_export])
        csv = df_export.to_csv(index=False)
        
        st.download_button(
            label="📥 Exportar Pronóstico (CSV)",
            data=csv,
            file_name=f"pronostico_{local}_vs_{visitante}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
            use_container_width=True
        )
    
    with col_export2:
        if st.button("🔄 Nuevo Pronóstico", use_container_width=True):
            st.rerun()

# ============================================================================
# EJECUCIÓN PRINCIPAL
# ============================================================================

if __name__ == "__main__":
    main()