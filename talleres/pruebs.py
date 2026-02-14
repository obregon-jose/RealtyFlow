# Importar librerías
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

# Configuración para mejorar visualizaciones
plt.style.use('seaborn-v0_8-darkgrid')  # Estilo de gráficos
sns.set_palette("husl")  # Paleta de colores
# %matplotlib inline

# Configurar tamaño de figura por defecto
plt.rcParams['figure.figsize'] = (10, 6)
plt.rcParams['font.size'] = 10

print("✅ Librerías importadas correctamente")

# Ejercicio 0.1: Cargar el dataset limpio
# TODO: Lee el archivo 'transacciones_bancarias_limpio.csv'
# IMPORTANTE: Este es el resultado del taller anterior de Pandas

df = pd.read_csv('transacciones_bancarias_limpio.csv')

# Convertir la columna fecha a datetime (si no está ya)
df['fecha'] = pd.to_datetime(df['fecha'])

print(f"Dataset cargado: {len(df)} registros")
print(f"Columnas: {df.columns.tolist()}")
df.head()

# Ejercicio 1.1: Gráfico de barras - Transacciones por tipo
# TODO: Crea un gráfico de barras que muestre la cantidad de transacciones por tipo
# Pista: 
# 1. Calcula value_counts() de tipo_transaccion
# 2. Usa plt.bar() o el método .plot(kind='bar')
# 3. Agrega título, etiquetas de ejes y rota las etiquetas del eje x

# Tu código aquí
transacciones_tipo = df['tipo_transaccion'].value_counts()

plt.figure(figsize=(10, 6))
# Crear gráfico de barras

plt.title('', fontsize=14, fontweight='bold')
plt.xlabel('')
plt.ylabel('')
plt.xticks(rotation=45, ha='right')
plt.tight_layout()
plt.show()


# Ejercicio 1.2: Gráfico de barras horizontales - Top 10 clientes
# TODO: Crea un gráfico de barras HORIZONTALES con los 10 clientes con más transacciones
# Pista: 
# 1. value_counts() de cliente_id y toma los primeros 10 (.head(10))
# 2. Usa plt.barh() o .plot(kind='barh')
# 3. Invierte el orden para que el mayor esté arriba (.iloc[::-1])

# Tu código aquí
top_clientes = df['cliente_id'].value_counts().head(10).iloc[::-1]

plt.title('Top 10 Clientes con Más Transacciones', fontsize=14, fontweight='bold')
plt.xlabel('Cantidad de Transacciones')
plt.ylabel('Cliente ID')
plt.tight_layout()
plt.show()