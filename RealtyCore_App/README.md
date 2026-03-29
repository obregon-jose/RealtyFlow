# RealtyFlow App — Gestor de escritorio

Aplicación de escritorio desarrollada en Python con **CustomTkinter** para gestionar
la base de datos `realtyflow_db`. Permite operar todas las tablas del
sistema mediante formularios, ver un dashboard con KPIs en tiempo real y ejecutar
SQL directamente contra la base de datos.

---

## Requisitos

| Requisito | Versión mínima |
|---|---|
| Python | 3.9+ |
| MySQL / MariaDB | 8.0+ (o XAMPP) |
| customtkinter | 5.2+ |
| mysqlclient **o** PyMySQL | cualquiera |

### Instalación de dependencias

```bash
pip install customtkinter
# Opción A — mysqlclient (más rápido, requiere compilador C en Windows)
pip install mysqlclient
# Opción B — PyMySQL (puro Python, más fácil de instalar)
pip install PyMySQL
```

> Si estás en Windows y mysqlclient falla al instalar, usa PyMySQL.
> La app detecta automáticamente cuál está disponible.

---

## Configuración de conexión

Edita las variables al inicio del archivo `realtyflow_app.py`:

```python
DB_HOST     = "127.0.0.1"   # host del servidor MySQL
DB_PORT     = 3306           # puerto (por defecto XAMPP)
DB_USER     = "root"         # usuario
DB_PASSWORD = "root"         # contraseña
DB_NAME     = "realtyflow_db"
```

Asegúrate de que la base de datos `realtyflow_db` esté creada e importada
(usa el script `realtyflow_db.sql`).

---

## Ejecución

```bash
python realtyflow_app.py
```

---
<!-- 
## Estructura de la aplicación

```
realtyflow_app.py
│
├── Capa de datos
│   ├── create_connection()       conexión MySQL con fallback mysqlclient/PyMySQL
│   ├── execute_sql()             ejecuta sentencias arbitrarias
│   ├── fetch_all()               carga tabla completa
│   ├── fetch_kpis()              consulta los 6 KPIs del dashboard
│   ├── fetch_reference_list()    carga (id, etiqueta) para combobox de FK
│   └── CRUD por tabla            insert_*/update_*/delete_* para las 9 tablas
│
├── SqlWorker (threading.Thread)  ejecuta SQL en hilo aparte — UI nunca se congela
│
├── Utilidades de formulario
│   ├── _lbl / _entry / _combo    widgets reutilizables con estilo consistente
│   ├── _cities_combo()           combobox especial para FK ciudad
│   ├── _form_window()            ventana modal con scroll automático
│   └── _sel_id()                 extrae el id de un combobox "id: etiqueta"
│
└── App (ctk.CTk)
    ├── Dashboard (tab Inicio)    KPIs + últimas propiedades + agentes por ciudad
    ├── Tab SQL                   consola con editor, resultado en tabla y carga de .sql
    └── Tab por tabla (×9)        lista con barra de desplazamiento + CRUD completo
```

--- -->
<!-- 
## Pantallas

### Dashboard — pantalla de inicio

Muestra 6 tarjetas KPI con el estado actual de la base de datos:

| Tarjeta | Qué muestra |
|---|---|
| Propiedades | Total de inmuebles en el portafolio |
| Disponibles | Propiedades con estado `disponible` |
| Clientes | Total de clientes registrados |
| Agentes activos | Agentes con estado activo |
| Cierres | Transacciones con estado `cerrada` |
| Ofertas pendientes | Ofertas sin resolver (estado `pendiente`) |

Cada tarjeta tiene un botón **Gestionar →** que navega directamente a la pestaña
de esa tabla. En la parte inferior hay dos mini-tablas: últimas propiedades
disponibles y distribución de agentes activos por ciudad.

### Consola SQL

Editor de texto libre donde puedes escribir o cargar un archivo `.sql`.
Al ejecutar, los resultados de `SELECT` aparecen en la tabla de respuesta
dentro de la misma pestaña. La ejecución corre en un hilo aparte, así la
interfaz no se congela con consultas largas.

También permite cargar un archivo `.json` con ENUMs personalizados para
que los combobox de los formularios reflejen los valores correctos.

### Gestión por tabla

Cada una de las 9 tablas tiene su propia pestaña con:
- Lista completa con barra de desplazamiento
- Botones **Nuevo**, **Editar**, **Eliminar**, **Refrescar**
- Formulario modal con scroll y validación de campos obligatorios
- Combobox con datos reales de la BD para todas las claves foráneas

---

## Tablas gestionadas

| Tabla | Campos clave |
|---|---|
| `ciudad` | nombre, departamento, región |
| `agente` | nombre, correo, comisión, ciudad (FK) |
| `cliente` | nombre, correo, presupuesto, ciudad preferida (FK) |
| `propiedad` | tipo, dirección, ciudad (FK), agente exclusivo (FK) |
| `precio_propiedad` | propiedad (FK), precio, desde, hasta |
| `visita` | propiedad (FK), cliente (FK), agente (FK), fecha, estado |
| `oferta` | propiedad (FK), cliente (FK), monto, estado |
| `transaccion` | propiedad (FK), cliente (FK), oferta (FK), precio final |
| `transaccion_agente` | transaccion (FK), agente (FK), comisión |

---

## Reglas de negocio aplicadas en formularios

- Los combobox de ciudad cargan los valores desde la tabla `ciudad` en la BD,
  no desde texto libre — garantiza integridad referencial.
- El campo `estado` de propiedad no incluye `inactiva` (eliminado en v5).
- `transaccion` requiere `cliente_id` obligatorio (campo añadido en v5).
- `propiedad` usa `agente_exclusivo_id` (corregido el typo `agente_esclusivo_id` de v1).
- `cliente` usa `ciudad_preferida_id` en lugar de texto libre `ubicacion_preferida`.

---

## Formato de ENUMs personalizados (JSON)

Si necesitas modificar los valores de los combobox sin tocar el código,
crea un archivo `.json` con esta estructura y cárgalo desde la consola SQL:

```json
{
  "propiedad": {
    "tipo_publicacion": ["venta", "alquiler"],
    "tipo_propiedad":   ["casa", "apartamento", "terreno"],
    "estado":           ["disponible", "en_negociacion", "vendida", "alquilada"]
  },
  "visita": {
    "estado": ["programada", "realizada", "cancelada"]
  },
  "oferta": {
    "estado": ["pendiente", "aceptada", "rechazada"]
  },
  "transaccion": {
    "tipo_transaccion":   ["venta", "alquiler"],
    "estado_transaccion": ["cerrada", "cancelada"]
  },
  "cliente": {
    "tipo_publicacion_preferida": ["venta", "alquiler"],
    "tipo_propiedad_preferida":   ["casa", "apartamento", "terreno"]
  }
}
```

---

## Escalabilidad — notas técnicas

La arquitectura está diseñada para crecer sin reescrituras:

- **Nueva tabla:** agrega su nombre en `TABLE_COLS`, crea las funciones
  `insert_*/update_*/delete_*` y un método `_form_*` en la clase `App`.
  El resto (pestaña, lista, botones CRUD, sidebar) se genera automáticamente.

- **Nuevo KPI:** agrega la consulta en `fetch_kpis()` y una entrada en
  `kpi_defs` dentro de `_build_dashboard()`.

- **Cambio de host/credenciales:** modifica las variables `DB_*` al inicio
  del archivo o externaliza la configuración a un `.env` con `python-dotenv`.

- **Múltiples conexiones:** la función `create_connection()` está aislada —
  puedes reemplazarla por un pool de conexiones (ej. `DBUtils`) sin tocar
  el resto de la app.

----->

## Archivos relacionados

| Archivo | Descripción |
|---|---|
| `app.py` | Aplicación completa (este archivo) |
| `realtyflow_db.sql` | DDL + DML — base de datos completa | 