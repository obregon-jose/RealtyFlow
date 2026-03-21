"""
RealtyFlow - Gestor completo (único archivo), versión mejorada:
- SQL manual ejecuta consultas reales contra la base de datos.
- SQL manual tiene su propio panel de respuesta (tabla) dentro de la misma pestaña.
- Formularios muestran título/etiqueta para cada campo.
- Variables y funciones en inglés; comentarios y mensajes en español.
- Usa mysqlclient con fallback a PyMySQL.
- Todo en un solo archivo, funcional.
"""

from __future__ import annotations

import json
import queue
import threading
import time
from typing import Optional, List, Tuple, Dict, Any

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# ----------------------------
# Configuración por defecto (XAMPP local)
# ----------------------------
DB_HOST = "127.0.0.1"
DB_PORT = 3306
DB_USER = "root"
DB_PASSWORD = "root"
DB_NAME = "realtyflow_db"

# ----------------------------
# Enums por defecto — se pueden sobreescribir cargando un JSON
# ----------------------------
DEFAULT_ENUMS = {
    "cliente": {
        "tipo_publicacion_preferida": ["venta", "alquiler"],
        "tipo_propiedad_preferida": ["casa", "apartamento", "terreno"],
    },
    "propiedad": {
        "tipo_publicacion": ["venta", "alquiler"],
        "tipo_propiedad": ["casa", "apartamento", "terreno"],
        "estado": ["disponible", "en_negociacion", "vendida", "alquilada", "inactiva"],
    },
    "visita": {"estado": ["programada", "realizada", "cancelada"]},
    "oferta": {"estado": ["pendiente", "aceptada", "rechazada"]},
    "transaccion": {"tipo_transaccion": ["venta", "alquiler"], "estado_transaccion": ["cerrada", "cancelada"]},
}

_enums: Dict[str, Dict[str, List[str]]] = DEFAULT_ENUMS.copy()

# ----------------------------
# Detectar driver MySQL
# ----------------------------
_DRIVER = None
MySQLdb = None
pymysql = None
try:
    import MySQLdb  # type: ignore

    _DRIVER = "mysqlclient"
except Exception:
    MySQLdb = None

if _DRIVER is None:
    try:
        import pymysql  # type: ignore

        _DRIVER = "pymysql"
    except Exception:
        pymysql = None


# ----------------------------
# Conexión y utilidades DB
# ----------------------------
class DbError(Exception):
    pass


def create_connection(database: str = DB_NAME):
    """Crea conexión; omitimos db si está vacío para evitar errores de driver."""
    if _DRIVER == "mysqlclient":
        params = {"host": DB_HOST, "user": DB_USER, "passwd": DB_PASSWORD, "port": DB_PORT, "charset": "utf8mb4", "use_unicode": True}
        if database:
            params["db"] = database
        return MySQLdb.connect(**params)  # type: ignore
    if _DRIVER == "pymysql":
        params = {"host": DB_HOST, "user": DB_USER, "password": DB_PASSWORD, "port": DB_PORT, "charset": "utf8mb4"}
        if database:
            params["database"] = database
        return pymysql.connect(**params)  # type: ignore
    raise DbError("No hay driver MySQL instalado. Instala 'mysqlclient' o 'PyMySQL'.")


def execute_sql_statements(sql_text: str, database: Optional[str] = DB_NAME) -> Tuple[bool, List[str], List[Tuple], List[str]]:
    """
    Ejecuta sentencias SQL separadas por ';'.
    Retorna (success, columns, rows, errors).
    """
    statements = [s.strip() for s in sql_text.split(";") if s.strip()]
    if not statements:
        return False, [], [], ["No hay sentencias SQL para ejecutar."]
    conn = create_connection(database or "")
    cur = conn.cursor()
    rows_result: List[Tuple] = []
    columns: List[str] = []
    errors: List[str] = []
    success = True
    try:
        for stmt in statements:
            lower = stmt.strip().lower()
            try:
                cur.execute(stmt)
                if lower.startswith("select"):
                    rows_result = cur.fetchall()
                    desc = cur.description
                    if desc:
                        columns = [d[0] for d in desc]
                else:
                    conn.commit()
            except Exception as e:
                errors.append(f"{str(e)} -- Sentencia: {stmt[:160]}")
                success = False
        cur.close()
        conn.close()
    except Exception as e_outer:
        errors.append(str(e_outer))
        success = False
    return success, columns, rows_result, errors


# ----------------------------
# Worker para ejecutar SQL sin bloquear UI
# ----------------------------
class SqlWorker(threading.Thread):
    def __init__(self, sql_text: str, ui_queue: queue.Queue):
        super().__init__(daemon=True)
        self.sql_text = sql_text
        self.ui_queue = ui_queue

    def run(self):
        start = time.time()
        try:
            ok, cols, rows, errors = execute_sql_statements(self.sql_text, DB_NAME)
            elapsed = time.time() - start
            self.ui_queue.put(("sql_done", {"ok": ok, "columns": cols, "rows": rows, "errors": errors, "elapsed": elapsed}))
        except Exception as e:
            elapsed = time.time() - start
            self.ui_queue.put(("sql_done", {"ok": False, "columns": [], "rows": [], "errors": [str(e)], "elapsed": elapsed}))


# ----------------------------
# Operaciones reutilizables para CRUD y selects
# ----------------------------
def fetch_all(table: str) -> List[Tuple]:
    conn = create_connection(DB_NAME)
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM {table}")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def fetch_one(table: str, pk: int) -> Optional[Tuple]:
    conn = create_connection(DB_NAME)
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM {table} WHERE id=%s", (pk,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row


def fetch_reference_list(table: str, id_col: str = "id", label_cols: List[str] = None) -> List[Tuple[int, str]]:
    """
    Devuelve lista de (id, label) usada en combobox para llaves foráneas.
    """
    conn = create_connection(DB_NAME)
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM {table}")
    rows = cur.fetchall()
    desc = [d[0] for d in cur.description]
    cur.close()
    conn.close()
    result: List[Tuple[int, str]] = []
    for r in rows:
        rdict = dict(zip(desc, r))
        idv = rdict.get(id_col)
        if label_cols:
            label = " - ".join(str(rdict.get(c, "")) for c in label_cols)
        else:
            label = rdict.get("nombre") or rdict.get("direccion") or str(idv)
        result.append((idv, str(label)))
    return result


# ----------------------------
# CRUD funciones específicas (agente, cliente, propiedad, precio_propiedad, visita, oferta, transaccion, transaccion_agente)
# ----------------------------
def insert_agente(data: dict) -> Tuple[bool, str]:
    try:
        conn = create_connection(DB_NAME)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO agente (nombre, telefono, correo, porcentaje_comision, fecha_ingreso, estado) VALUES (%s,%s,%s,%s,%s,%s)",
            (data.get("nombre"), data.get("telefono"), data.get("correo"), data.get("porcentaje_comision") or 3.0, data.get("fecha_ingreso"), 1 if data.get("estado", True) else 0),
        )
        conn.commit()
        cur.close()
        conn.close()
        return True, "Agente creado."
    except Exception as e:
        return False, str(e)


def update_agente(agent_id: int, data: dict) -> Tuple[bool, str]:
    try:
        conn = create_connection(DB_NAME)
        cur = conn.cursor()
        cur.execute(
            "UPDATE agente SET nombre=%s, telefono=%s, correo=%s, porcentaje_comision=%s, fecha_ingreso=%s, estado=%s WHERE id=%s",
            (data.get("nombre"), data.get("telefono"), data.get("correo"), data.get("porcentaje_comision") or 3.0, data.get("fecha_ingreso"), 1 if data.get("estado", True) else 0, agent_id),
        )
        conn.commit()
        cur.close()
        conn.close()
        return True, "Agente actualizado."
    except Exception as e:
        return False, str(e)


def delete_agente(agent_id: int) -> Tuple[bool, str]:
    try:
        conn = create_connection(DB_NAME)
        cur = conn.cursor()
        cur.execute("DELETE FROM agente WHERE id=%s", (agent_id,))
        conn.commit()
        cur.close()
        conn.close()
        return True, "Agente eliminado."
    except Exception as e:
        return False, str(e)


def insert_cliente(data: dict) -> Tuple[bool, str]:
    try:
        conn = create_connection(DB_NAME)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO cliente (nombre, telefono, correo, tipo_publicacion_preferida, tipo_propiedad_preferida, ubicacion_preferida, presupuesto_min, presupuesto_max) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (data.get("nombre"), data.get("telefono"), data.get("correo"), data.get("tipo_publicacion_preferida"), data.get("tipo_propiedad_preferida"), data.get("ubicacion_preferida"), data.get("presupuesto_min") or 0, data.get("presupuesto_max") or 0),
        )
        conn.commit()
        cur.close()
        conn.close()
        return True, "Cliente creado."
    except Exception as e:
        return False, str(e)


def update_cliente(client_id: int, data: dict) -> Tuple[bool, str]:
    try:
        conn = create_connection(DB_NAME)
        cur = conn.cursor()
        cur.execute(
            "UPDATE cliente SET nombre=%s, telefono=%s, correo=%s, tipo_publicacion_preferida=%s, tipo_propiedad_preferida=%s, ubicacion_preferida=%s, presupuesto_min=%s, presupuesto_max=%s WHERE id=%s",
            (data.get("nombre"), data.get("telefono"), data.get("correo"), data.get("tipo_publicacion_preferida"), data.get("tipo_propiedad_preferida"), data.get("ubicacion_preferida"), data.get("presupuesto_min") or 0, data.get("presupuesto_max") or 0, client_id),
        )
        conn.commit()
        cur.close()
        conn.close()
        return True, "Cliente actualizado."
    except Exception as e:
        return False, str(e)


def delete_cliente(client_id: int) -> Tuple[bool, str]:
    try:
        conn = create_connection(DB_NAME)
        cur = conn.cursor()
        cur.execute("DELETE FROM cliente WHERE id=%s", (client_id,))
        conn.commit()
        cur.close()
        conn.close()
        return True, "Cliente eliminado."
    except Exception as e:
        return False, str(e)


def insert_propiedad(data: dict) -> Tuple[bool, str]:
    try:
        conn = create_connection(DB_NAME)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO propiedad (tipo_publicacion, tipo_propiedad, direccion, ciudad, area_m2, habitaciones, banos, anio_construccion, estado, fecha_publicacion, agente_esclusivo_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                data.get("tipo_publicacion"),
                data.get("tipo_propiedad"),
                data.get("direccion"),
                data.get("ciudad"),
                data.get("area_m2"),
                data.get("habitaciones"),
                data.get("banos"),
                data.get("anio_construccion"),
                data.get("estado"),
                data.get("fecha_publicacion"),
                data.get("agente_esclusivo_id") or None,
            ),
        )
        conn.commit()
        cur.close()
        conn.close()
        return True, "Propiedad creada."
    except Exception as e:
        return False, str(e)


def update_propiedad(prop_id: int, data: dict) -> Tuple[bool, str]:
    try:
        conn = create_connection(DB_NAME)
        cur = conn.cursor()
        cur.execute(
            "UPDATE propiedad SET tipo_publicacion=%s, tipo_propiedad=%s, direccion=%s, ciudad=%s, area_m2=%s, habitaciones=%s, banos=%s, anio_construccion=%s, estado=%s, fecha_publicacion=%s, agente_esclusivo_id=%s WHERE id=%s",
            (
                data.get("tipo_publicacion"),
                data.get("tipo_propiedad"),
                data.get("direccion"),
                data.get("ciudad"),
                data.get("area_m2"),
                data.get("habitaciones"),
                data.get("banos"),
                data.get("anio_construccion"),
                data.get("estado"),
                data.get("fecha_publicacion"),
                data.get("agente_esclusivo_id") or None,
                prop_id,
            ),
        )
        conn.commit()
        cur.close()
        conn.close()
        return True, "Propiedad actualizada."
    except Exception as e:
        return False, str(e)


def delete_propiedad(prop_id: int) -> Tuple[bool, str]:
    try:
        conn = create_connection(DB_NAME)
        cur = conn.cursor()
        cur.execute("DELETE FROM propiedad WHERE id=%s", (prop_id,))
        conn.commit()
        cur.close()
        conn.close()
        return True, "Propiedad eliminada."
    except Exception as e:
        return False, str(e)


def insert_precio_propiedad(data: dict) -> Tuple[bool, str]:
    try:
        conn = create_connection(DB_NAME)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO precio_propiedad (propiedad_id, precio, desde, hasta) VALUES (%s,%s,%s,%s)",
            (data.get("propiedad_id"), data.get("precio"), data.get("desde"), data.get("hasta") or None),
        )
        conn.commit()
        cur.close()
        conn.close()
        return True, "Precio agregado."
    except Exception as e:
        return False, str(e)


def update_precio_propiedad(pp_id: int, data: dict) -> Tuple[bool, str]:
    try:
        conn = create_connection(DB_NAME)
        cur = conn.cursor()
        cur.execute("UPDATE precio_propiedad SET propiedad_id=%s, precio=%s, desde=%s, hasta=%s WHERE id=%s", (data.get("propiedad_id"), data.get("precio"), data.get("desde"), data.get("hasta") or None, pp_id))
        conn.commit()
        cur.close()
        conn.close()
        return True, "Precio actualizado."
    except Exception as e:
        return False, str(e)


def delete_precio_propiedad(pp_id: int) -> Tuple[bool, str]:
    try:
        conn = create_connection(DB_NAME)
        cur = conn.cursor()
        cur.execute("DELETE FROM precio_propiedad WHERE id=%s", (pp_id,))
        conn.commit()
        cur.close()
        conn.close()
        return True, "Registro de precio eliminado."
    except Exception as e:
        return False, str(e)


def insert_visita(data: dict) -> Tuple[bool, str]:
    try:
        conn = create_connection(DB_NAME)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO visita (propiedad_id, cliente_id, agente_id, fecha, hora, estado, notas) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (data.get("propiedad_id"), data.get("cliente_id"), data.get("agente_id") or None, data.get("fecha"), data.get("hora"), data.get("estado"), data.get("notas")),
        )
        conn.commit()
        cur.close()
        conn.close()
        return True, "Visita creada."
    except Exception as e:
        return False, str(e)


def update_visita(vis_id: int, data: dict) -> Tuple[bool, str]:
    try:
        conn = create_connection(DB_NAME)
        cur = conn.cursor()
        cur.execute(
            "UPDATE visita SET propiedad_id=%s, cliente_id=%s, agente_id=%s, fecha=%s, hora=%s, estado=%s, notas=%s WHERE id=%s",
            (data.get("propiedad_id"), data.get("cliente_id"), data.get("agente_id") or None, data.get("fecha"), data.get("hora"), data.get("estado"), data.get("notas"), vis_id),
        )
        conn.commit()
        cur.close()
        conn.close()
        return True, "Visita actualizada."
    except Exception as e:
        return False, str(e)


def delete_visita(vis_id: int) -> Tuple[bool, str]:
    try:
        conn = create_connection(DB_NAME)
        cur = conn.cursor()
        cur.execute("DELETE FROM visita WHERE id=%s", (vis_id,))
        conn.commit()
        cur.close()
        conn.close()
        return True, "Visita eliminada."
    except Exception as e:
        return False, str(e)


def insert_oferta(data: dict) -> Tuple[bool, str]:
    try:
        conn = create_connection(DB_NAME)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO oferta (propiedad_id, cliente_id, fecha, monto, estado, comentarios) VALUES (%s,%s,%s,%s,%s,%s)",
            (data.get("propiedad_id"), data.get("cliente_id"), data.get("fecha") or None, data.get("monto"), data.get("estado"), data.get("comentarios")),
        )
        conn.commit()
        cur.close()
        conn.close()
        return True, "Oferta creada."
    except Exception as e:
        return False, str(e)


def update_oferta(oferta_id: int, data: dict) -> Tuple[bool, str]:
    try:
        conn = create_connection(DB_NAME)
        cur = conn.cursor()
        cur.execute(
            "UPDATE oferta SET propiedad_id=%s, cliente_id=%s, fecha=%s, monto=%s, estado=%s, comentarios=%s WHERE id=%s",
            (data.get("propiedad_id"), data.get("cliente_id"), data.get("fecha") or None, data.get("monto"), data.get("estado"), data.get("comentarios"), oferta_id),
        )
        conn.commit()
        cur.close()
        conn.close()
        return True, "Oferta actualizada."
    except Exception as e:
        return False, str(e)


def delete_oferta(oferta_id: int) -> Tuple[bool, str]:
    try:
        conn = create_connection(DB_NAME)
        cur = conn.cursor()
        cur.execute("DELETE FROM oferta WHERE id=%s", (oferta_id,))
        conn.commit()
        cur.close()
        conn.close()
        return True, "Oferta eliminada."
    except Exception as e:
        return False, str(e)


def insert_transaccion(data: dict) -> Tuple[bool, str]:
    try:
        conn = create_connection(DB_NAME)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO transaccion (propiedad_id, fecha_cierre, precio_final, tipo_transaccion, estado_transaccion, oferta_id) VALUES (%s,%s,%s,%s,%s,%s)",
            (data.get("propiedad_id"), data.get("fecha_cierre") or None, data.get("precio_final"), data.get("tipo_transaccion"), data.get("estado_transaccion"), data.get("oferta_id") or None),
        )
        conn.commit()
        cur.close()
        conn.close()
        return True, "Transacción creada."
    except Exception as e:
        return False, str(e)


def update_transaccion(tr_id: int, data: dict) -> Tuple[bool, str]:
    try:
        conn = create_connection(DB_NAME)
        cur = conn.cursor()
        cur.execute(
            "UPDATE transaccion SET propiedad_id=%s, fecha_cierre=%s, precio_final=%s, tipo_transaccion=%s, estado_transaccion=%s, oferta_id=%s WHERE id=%s",
            (data.get("propiedad_id"), data.get("fecha_cierre") or None, data.get("precio_final"), data.get("tipo_transaccion"), data.get("estado_transaccion"), data.get("oferta_id") or None, tr_id),
        )
        conn.commit()
        cur.close()
        conn.close()
        return True, "Transacción actualizada."
    except Exception as e:
        return False, str(e)


def delete_transaccion(tr_id: int) -> Tuple[bool, str]:
    try:
        conn = create_connection(DB_NAME)
        cur = conn.cursor()
        cur.execute("DELETE FROM transaccion WHERE id=%s", (tr_id,))
        conn.commit()
        cur.close()
        conn.close()
        return True, "Transacción eliminada."
    except Exception as e:
        return False, str(e)


def insert_transaccion_agente(data: dict) -> Tuple[bool, str]:
    try:
        conn = create_connection(DB_NAME)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO transaccion_agente (transaccion_id, agente_id, comision_monto, comision_porcentaje) VALUES (%s,%s,%s,%s)",
            (data.get("transaccion_id"), data.get("agente_id"), data.get("comision_monto") or None, data.get("comision_porcentaje") or 0),
        )
        conn.commit()
        cur.close()
        conn.close()
        return True, "Registro transaccion_agente creado."
    except Exception as e:
        return False, str(e)


def update_transaccion_agente(tr_id: int, agente_id: int, data: dict) -> Tuple[bool, str]:
    try:
        conn = create_connection(DB_NAME)
        cur = conn.cursor()
        cur.execute(
            "UPDATE transaccion_agente SET comision_monto=%s, comision_porcentaje=%s WHERE transaccion_id=%s AND agente_id=%s",
            (data.get("comision_monto") or None, data.get("comision_porcentaje") or 0, tr_id, agente_id),
        )
        conn.commit()
        cur.close()
        conn.close()
        return True, "Transaccion_agente actualizada."
    except Exception as e:
        return False, str(e)


def delete_transaccion_agente(tr_id: int, agente_id: int) -> Tuple[bool, str]:
    try:
        conn = create_connection(DB_NAME)
        cur = conn.cursor()
        cur.execute("DELETE FROM transaccion_agente WHERE transaccion_id=%s AND agente_id=%s", (tr_id, agente_id))
        conn.commit()
        cur.close()
        conn.close()
        return True, "Registro transaccion_agente eliminado."
    except Exception as e:
        return False, str(e)


# ----------------------------
# UI: aplicación principal con pestañas para cada tabla y panel SQL
# ----------------------------
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")
        self.title("RealtyFlow - Gestor completo")
        self.geometry("1200x720")

        self.ui_queue: queue.Queue = queue.Queue()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_main_ui()
        self._schedule_queue()

    def _build_main_ui(self):
        container = ctk.CTkFrame(self, corner_radius=8)
        container.pack(fill="both", expand=True, padx=12, pady=12)

        self.tab_control = ttk.Notebook(container)
        self.tab_control.pack(fill="both", expand=True)

        # Pestaña SQL manual
        tab_sql = ttk.Frame(self.tab_control)
        self.tab_control.add(tab_sql, text="SQL manual")
        self._build_sql_tab(tab_sql)

        # Crear pestañas para cada tabla
        self._create_table_tab("agente", ["id", "nombre", "telefono", "correo", "porcentaje_comision", "fecha_ingreso", "estado"])
        self._create_table_tab("cliente", ["id", "nombre", "telefono", "correo", "tipo_publicacion_preferida", "tipo_propiedad_preferida", "ubicacion_preferida", "presupuesto_min", "presupuesto_max"])
        self._create_table_tab("propiedad", ["id", "tipo_publicacion", "tipo_propiedad", "direccion", "ciudad", "area_m2", "habitaciones", "banos", "anio_construccion", "estado", "fecha_publicacion", "agente_esclusivo_id"])
        self._create_table_tab("precio_propiedad", ["id", "propiedad_id", "precio", "desde", "hasta"])
        self._create_table_tab("visita", ["id", "propiedad_id", "cliente_id", "agente_id", "fecha", "hora", "estado", "notas"])
        self._create_table_tab("oferta", ["id", "propiedad_id", "cliente_id", "fecha", "monto", "estado", "comentarios"])
        self._create_table_tab("transaccion", ["id", "propiedad_id", "fecha_cierre", "precio_final", "tipo_transaccion", "estado_transaccion", "oferta_id"])
        self._create_table_tab("transaccion_agente", ["transaccion_id", "agente_id", "comision_monto", "comision_porcentaje"])

    # ------------------------
    # SQL tab (ahora con panel de respuesta propio)
    # ------------------------
    def _build_sql_tab(self, parent):
        parent.grid_rowconfigure(1, weight=1)
        parent.grid_columnconfigure(0, weight=1)

        lbl = ctk.CTkLabel(parent, text="Pegar sentencias SQL o abrir archivo .sql", anchor="w")
        lbl.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))

        self.sql_text = tk.Text(parent, height=12, wrap="none")
        self.sql_text.grid(row=1, column=0, sticky="nsew", padx=8, pady=4)

        # Resultado dentro mismo panel SQL
        res_lbl = ctk.CTkLabel(parent, text="Respuesta de la base de datos (si SELECT):", anchor="w")
        res_lbl.grid(row=2, column=0, sticky="ew", padx=8, pady=(6, 2))

        self.sql_result_tree = ttk.Treeview(parent)
        self.sql_result_tree.grid(row=3, column=0, sticky="nsew", padx=8, pady=(0, 8))

        btns = ctk.CTkFrame(parent, fg_color="transparent")
        btns.grid(row=4, column=0, sticky="ew", padx=8, pady=8)
        open_btn = ctk.CTkButton(btns, text="Abrir .sql", width=120, command=self.on_open_sql)
        open_btn.grid(row=0, column=0, padx=6)
        run_btn = ctk.CTkButton(btns, text="Ejecutar SQL", width=140, command=self.on_run_sql)
        run_btn.grid(row=0, column=1, padx=6)
        enum_btn = ctk.CTkButton(btns, text="Cargar enums (.json)", width=180, command=self.on_load_enums)
        enum_btn.grid(row=0, column=2, padx=6)

        self.sql_status_lbl = ctk.CTkLabel(btns, text="Estado: listo", anchor="w")
        self.sql_status_lbl.grid(row=0, column=3, sticky="w", padx=12)

    def on_open_sql(self):
        path = filedialog.askopenfilename(title="Selecciona archivo .sql", filetypes=[("SQL", "*.sql"), ("Todos", "*.*")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            self.sql_text.delete("1.0", "end")
            self.sql_text.insert("1.0", content)
            self.sql_status_lbl.configure(text=f"Archivo cargado: {path.split('/')[-1]}")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo leer el archivo: {e}")

    def on_run_sql(self):
        sql = self.sql_text.get("1.0", "end").strip()
        if not sql:
            messagebox.showerror("Error", "Ingresa alguna sentencia SQL antes de ejecutar.")
            return
        if _DRIVER is None:
            messagebox.showerror("Error", "No hay driver MySQL instalado. Instala 'mysqlclient' o 'PyMySQL'.")
            return
        self.sql_status_lbl.configure(text="Ejecutando...")
        worker = SqlWorker(sql, self.ui_queue)
        worker.start()

    def on_load_enums(self):
        path = filedialog.askopenfilename(title="Selecciona enums JSON", filetypes=[("JSON", "*.json"), ("Todos", "*.*")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                obj = json.load(f)
            if not isinstance(obj, dict):
                raise ValueError("Formato JSON inválido.")
            global _enums
            _enums = obj
            messagebox.showinfo("Enums", "Enums cargados desde JSON.")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo cargar JSON: {e}")

    # ------------------------
    # Generador de pestañas por tabla (lista + botones CRUD)
    # ------------------------
    def _create_table_tab(self, table: str, columns: List[str]):
        tab = ttk.Frame(self.tab_control)
        self.tab_control.add(tab, text=table)
        tab.grid_rowconfigure(0, weight=1)
        tab.grid_columnconfigure(0, weight=1)

        tree = ttk.Treeview(tab, columns=columns, show="headings")
        for c in columns:
            tree.heading(c, text=c)
            tree.column(c, width=140, anchor="w")
        tree.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

        btn_frame = ctk.CTkFrame(tab, fg_color="transparent")
        btn_frame.grid(row=1, column=0, sticky="ew", padx=8, pady=8)
        add_btn = ctk.CTkButton(btn_frame, text="Nuevo", width=120, command=lambda t=table: self.on_new_record(t))
        add_btn.grid(row=0, column=0, padx=6)
        edit_btn = ctk.CTkButton(btn_frame, text="Editar", width=120, command=lambda t=table, tr=tree: self.on_edit_record(t, tr))
        edit_btn.grid(row=0, column=1, padx=6)
        del_btn = ctk.CTkButton(btn_frame, text="Eliminar", width=120, command=lambda t=table, tr=tree: self.on_delete_record(t, tr))
        del_btn.grid(row=0, column=2, padx=6)
        ref_btn = ctk.CTkButton(btn_frame, text="Refrescar", width=120, command=lambda t=table, tr=tree: self.load_table(t, tr))
        ref_btn.grid(row=0, column=3, padx=6)

        setattr(self, f"{table}_tree", tree)
        self.load_table(table, tree)

    def load_table(self, table: str, tree: ttk.Treeview):
        try:
            rows = fetch_all(table)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo cargar {table}: {e}")
            return
        for i in tree.get_children():
            tree.delete(i)
        for r in rows:
            display = tuple("" if v is None else str(v) for v in r)
            tree.insert("", "end", values=display)

    # ------------------------
    # Handlers CRUD genéricos
    # ------------------------
    def on_new_record(self, table: str):
        if table == "agente":
            self._open_agente_form()
        elif table == "cliente":
            self._open_cliente_form()
        elif table == "propiedad":
            self._open_propiedad_form()
        elif table == "precio_propiedad":
            self._open_precio_propiedad_form()
        elif table == "visita":
            self._open_visita_form()
        elif table == "oferta":
            self._open_oferta_form()
        elif table == "transaccion":
            self._open_transaccion_form()
        elif table == "transaccion_agente":
            self._open_transaccion_agente_form()
        else:
            messagebox.showinfo("Info", f"No implementado nuevo para {table}")

    def on_edit_record(self, table: str, tree: ttk.Treeview):
        sel = tree.selection()
        if not sel:
            messagebox.showinfo("Info", "Selecciona un registro para editar.")
            return
        values = tree.item(sel[0], "values")
        if table == "transaccion_agente":
            trans_id = int(values[0])
            agente_id = int(values[1])
            self._open_transaccion_agente_form(edit_key=(trans_id, agente_id), initial=values)
            return
        record_id = int(values[0])
        if table == "agente":
            self._open_agente_form(agent_id=record_id, initial=values)
        elif table == "cliente":
            self._open_cliente_form(client_id=record_id, initial=values)
        elif table == "propiedad":
            self._open_propiedad_form(prop_id=record_id, initial=values)
        elif table == "precio_propiedad":
            self._open_precio_propiedad_form(pp_id=record_id, initial=values)
        elif table == "visita":
            self._open_visita_form(vis_id=record_id, initial=values)
        elif table == "oferta":
            self._open_oferta_form(oferta_id=record_id, initial=values)
        elif table == "transaccion":
            self._open_transaccion_form(tr_id=record_id, initial=values)
        else:
            messagebox.showinfo("Info", f"No implementado editar para {table}")

    def on_delete_record(self, table: str, tree: ttk.Treeview):
        sel = tree.selection()
        if not sel:
            messagebox.showinfo("Info", "Selecciona un registro para eliminar.")
            return
        values = tree.item(sel[0], "values")
        if table == "transaccion_agente":
            trans_id = int(values[0])
            agente_id = int(values[1])
            if not messagebox.askyesno("Confirmar", "Eliminar registro transaccion_agente?"):
                return
            ok, msg = delete_transaccion_agente(trans_id, agente_id)
            if ok:
                messagebox.showinfo("OK", msg)
                self.load_table(table, tree)
            else:
                messagebox.showerror("Error", msg)
            return
        record_id = int(values[0])
        if not messagebox.askyesno("Confirmar", f"Eliminar registro id={record_id} de {table}?"):
            return
        fn_map = {
            "agente": delete_agente,
            "cliente": delete_cliente,
            "propiedad": delete_propiedad,
            "precio_propiedad": delete_precio_propiedad,
            "visita": delete_visita,
            "oferta": delete_oferta,
            "transaccion": delete_transaccion,
        }
        fn = fn_map.get(table)
        if fn:
            ok, msg = fn(record_id)
            if ok:
                messagebox.showinfo("OK", msg)
                self.load_table(table, tree)
            else:
                messagebox.showerror("Error", msg)
        else:
            messagebox.showinfo("Info", f"No implementado eliminar para {table}")

    # ------------------------
    # Formularios (ahora con etiquetas para cada campo)
    # ------------------------
    def _open_agente_form(self, agent_id: Optional[int] = None, initial: Optional[Tuple] = None):
        win = ctk.CTkToplevel(self)
        win.title("Agente" + (" - editar" if agent_id else " - nuevo"))
        win.geometry("480x360")

        ctk.CTkLabel(win, text="Nombre").pack(padx=8, pady=(12, 2), anchor="w")
        ent_nombre = ctk.CTkEntry(win); ent_nombre.pack(fill="x", padx=8); ent_nombre.insert(0, initial[1] if initial else "")

        ctk.CTkLabel(win, text="Teléfono").pack(padx=8, pady=(8, 2), anchor="w")
        ent_tel = ctk.CTkEntry(win); ent_tel.pack(fill="x", padx=8); ent_tel.insert(0, initial[2] if initial else "")

        ctk.CTkLabel(win, text="Correo").pack(padx=8, pady=(8, 2), anchor="w")
        ent_mail = ctk.CTkEntry(win); ent_mail.pack(fill="x", padx=8); ent_mail.insert(0, initial[3] if initial else "")

        ctk.CTkLabel(win, text="Porcentaje comisión").pack(padx=8, pady=(8, 2), anchor="w")
        ent_pct = ctk.CTkEntry(win); ent_pct.pack(fill="x", padx=8); ent_pct.insert(0, initial[4] if initial else "")

        ctk.CTkLabel(win, text="Fecha ingreso (YYYY-MM-DD)").pack(padx=8, pady=(8, 2), anchor="w")
        ent_fecha = ctk.CTkEntry(win); ent_fecha.pack(fill="x", padx=8); ent_fecha.insert(0, initial[5] if initial else "")

        chk_estado_var = tk.IntVar(value=1 if (initial and initial[6] in ("1", "True", "true")) else 1)
        chk_estado = ctk.CTkCheckBox(win, text="Activo", variable=chk_estado_var); chk_estado.pack(padx=8, pady=(8, 12), anchor="w")

        def on_save():
            data = {"nombre": ent_nombre.get().strip(), "telefono": ent_tel.get().strip(), "correo": ent_mail.get().strip(), "porcentaje_comision": ent_pct.get().strip() or None, "fecha_ingreso": ent_fecha.get().strip() or None, "estado": bool(chk_estado_var.get())}
            if agent_id:
                ok, msg = update_agente(agent_id, data)
            else:
                ok, msg = insert_agente(data)
            if ok:
                messagebox.showinfo("OK", msg); win.destroy(); self.load_table("agente", getattr(self, "agente_tree"))
            else:
                messagebox.showerror("Error", msg)

        save_btn = ctk.CTkButton(win, text="Guardar", command=on_save); save_btn.pack(pady=8)

    def _open_cliente_form(self, client_id: Optional[int] = None, initial: Optional[Tuple] = None):
        win = ctk.CTkToplevel(self); win.title("Cliente" + (" - editar" if client_id else " - nuevo")); win.geometry("520x520")

        ctk.CTkLabel(win, text="Nombre").pack(padx=8, pady=(12,2), anchor="w")
        ent_nombre = ctk.CTkEntry(win); ent_nombre.pack(fill="x", padx=8); ent_nombre.insert(0, initial[1] if initial else "")

        ctk.CTkLabel(win, text="Teléfono").pack(padx=8, pady=(8,2), anchor="w")
        ent_tel = ctk.CTkEntry(win); ent_tel.pack(fill="x", padx=8); ent_tel.insert(0, initial[2] if initial else "")

        ctk.CTkLabel(win, text="Correo").pack(padx=8, pady=(8,2), anchor="w")
        ent_mail = ctk.CTkEntry(win); ent_mail.pack(fill="x", padx=8); ent_mail.insert(0, initial[3] if initial else "")

        cliente_enums = _enums.get("cliente", {})
        tipo_pub_vals = cliente_enums.get("tipo_publicacion_preferida", [])
        tipo_prop_vals = cliente_enums.get("tipo_propiedad_preferida", [])

        ctk.CTkLabel(win, text="Tipo publicación preferida").pack(padx=8, pady=(8,2), anchor="w")
        if tipo_pub_vals:
            cb_tipo_pub = ctk.CTkComboBox(win, values=tipo_pub_vals); cb_tipo_pub.pack(fill="x", padx=8)
            if initial and initial[4] not in ("None", ""): cb_tipo_pub.set(initial[4])
        else:
            cb_tipo_pub = ctk.CTkEntry(win); cb_tipo_pub.pack(fill="x", padx=8)
            if initial: cb_tipo_pub.insert(0, initial[4] if initial[4] not in ("None", "") else "")

        ctk.CTkLabel(win, text="Tipo propiedad preferida").pack(padx=8, pady=(8,2), anchor="w")
        if tipo_prop_vals:
            cb_tipo_prop = ctk.CTkComboBox(win, values=tipo_prop_vals); cb_tipo_prop.pack(fill="x", padx=8)
            if initial and initial[5] not in ("None", ""): cb_tipo_prop.set(initial[5])
        else:
            cb_tipo_prop = ctk.CTkEntry(win); cb_tipo_prop.pack(fill="x", padx=8)
            if initial: cb_tipo_prop.insert(0, initial[5] if initial[5] not in ("None", "") else "")

        ctk.CTkLabel(win, text="Ubicación preferida").pack(padx=8, pady=(8,2), anchor="w")
        ent_ubic = ctk.CTkEntry(win); ent_ubic.pack(fill="x", padx=8); ent_ubic.insert(0, initial[6] if initial else "")

        ctk.CTkLabel(win, text="Presupuesto mínimo").pack(padx=8, pady=(8,2), anchor="w")
        ent_min = ctk.CTkEntry(win); ent_min.pack(fill="x", padx=8); ent_min.insert(0, initial[7] if initial else "")

        ctk.CTkLabel(win, text="Presupuesto máximo").pack(padx=8, pady=(8,2), anchor="w")
        ent_max = ctk.CTkEntry(win); ent_max.pack(fill="x", padx=8); ent_max.insert(0, initial[8] if initial else "")

        def on_save():
            tipo_pub_val = cb_tipo_pub.get() if isinstance(cb_tipo_pub, ctk.CTkComboBox) else cb_tipo_pub.get().strip()
            tipo_prop_val = cb_tipo_prop.get() if isinstance(cb_tipo_prop, ctk.CTkComboBox) else cb_tipo_prop.get().strip()
            data = {"nombre": ent_nombre.get().strip(), "telefono": ent_tel.get().strip(), "correo": ent_mail.get().strip(), "tipo_publicacion_preferida": tipo_pub_val or None, "tipo_propiedad_preferida": tipo_prop_val or None, "ubicacion_preferida": ent_ubic.get().strip() or None, "presupuesto_min": ent_min.get().strip() or None, "presupuesto_max": ent_max.get().strip() or None}
            if client_id:
                ok, msg = update_cliente(client_id, data)
            else:
                ok, msg = insert_cliente(data)
            if ok:
                messagebox.showinfo("OK", msg); win.destroy(); self.load_table("cliente", getattr(self, "cliente_tree"))
            else:
                messagebox.showerror("Error", msg)

        save_btn = ctk.CTkButton(win, text="Guardar", command=on_save); save_btn.pack(pady=8)

    def _open_propiedad_form(self, prop_id: Optional[int] = None, initial: Optional[Tuple] = None):
        win = ctk.CTkToplevel(self); win.title("Propiedad" + (" - editar" if prop_id else " - nuevo")); win.geometry("600x640")
        entidad_enums = _enums.get("propiedad", {})
        tipo_pub_vals = entidad_enums.get("tipo_publicacion", []); tipo_prop_vals = entidad_enums.get("tipo_propiedad", []); estado_vals = entidad_enums.get("estado", [])

        ctk.CTkLabel(win, text="Tipo publicación").pack(padx=8, pady=(12,2), anchor="w")
        tipo_pub_cb = ctk.CTkComboBox(win, values=tipo_pub_vals) if tipo_pub_vals else ctk.CTkEntry(win); tipo_pub_cb.pack(fill="x", padx=8)
        if initial and initial[1] not in ("None", ""):
            try: tipo_pub_cb.set(initial[1])
            except Exception: pass

        ctk.CTkLabel(win, text="Tipo propiedad").pack(padx=8, pady=(8,2), anchor="w")
        tipo_prop_cb = ctk.CTkComboBox(win, values=tipo_prop_vals) if tipo_prop_vals else ctk.CTkEntry(win); tipo_prop_cb.pack(fill="x", padx=8)
        if initial and initial[2] not in ("None", ""):
            try: tipo_prop_cb.set(initial[2])
            except Exception: pass

        ctk.CTkLabel(win, text="Dirección").pack(padx=8, pady=(8,2), anchor="w")
        ent_direccion = ctk.CTkEntry(win); ent_direccion.pack(fill="x", padx=8); ent_direccion.insert(0, initial[3] if initial else "")

        ctk.CTkLabel(win, text="Ciudad").pack(padx=8, pady=(8,2), anchor="w")
        ent_ciudad = ctk.CTkEntry(win); ent_ciudad.pack(fill="x", padx=8); ent_ciudad.insert(0, initial[4] if initial else "")

        ctk.CTkLabel(win, text="Área (m2)").pack(padx=8, pady=(8,2), anchor="w")
        ent_area = ctk.CTkEntry(win); ent_area.pack(fill="x", padx=8); ent_area.insert(0, initial[5] if initial else "")

        ctk.CTkLabel(win, text="Habitaciones").pack(padx=8, pady=(8,2), anchor="w")
        ent_habs = ctk.CTkEntry(win); ent_habs.pack(fill="x", padx=8); ent_habs.insert(0, initial[6] if initial else "")

        ctk.CTkLabel(win, text="Baños").pack(padx=8, pady=(8,2), anchor="w")
        ent_banos = ctk.CTkEntry(win); ent_banos.pack(fill="x", padx=8); ent_banos.insert(0, initial[7] if initial else "")

        ctk.CTkLabel(win, text="Año construcción").pack(padx=8, pady=(8,2), anchor="w")
        ent_anio = ctk.CTkEntry(win); ent_anio.pack(fill="x", padx=8); ent_anio.insert(0, initial[8] if initial else "")

        ctk.CTkLabel(win, text="Estado").pack(padx=8, pady=(8,2), anchor="w")
        estado_cb = ctk.CTkComboBox(win, values=estado_vals) if estado_vals else ctk.CTkEntry(win); estado_cb.pack(fill="x", padx=8)
        if initial and initial[9] not in ("None", ""):
            try: estado_cb.set(initial[9])
            except Exception: pass

        ctk.CTkLabel(win, text="Fecha publicación (YYYY-MM-DD)").pack(padx=8, pady=(8,2), anchor="w")
        ent_fecha_pub = ctk.CTkEntry(win); ent_fecha_pub.pack(fill="x", padx=8); ent_fecha_pub.insert(0, initial[10] if initial else "")

        ctk.CTkLabel(win, text="Agente exclusivo (id: etiqueta)").pack(padx=8, pady=(8,2), anchor="w")
        agentes = fetch_reference_list("agente", label_cols=["nombre", "correo"])
        agente_vals = [f"{a[0]}: {a[1]}" for a in agentes]
        agente_cb = ctk.CTkComboBox(win, values=agente_vals) if agente_vals else ctk.CTkEntry(win); agente_cb.pack(fill="x", padx=8)
        if initial and initial[11] not in ("None", "") and initial[11] != "":
            try:
                match = [v for v in agente_vals if v.startswith(str(initial[11]) + ":")]
                if match:
                    agente_cb.set(match[0])
            except Exception:
                pass

        def on_save():
            agente_sel = None
            if isinstance(agente_cb, ctk.CTkComboBox):
                sel = agente_cb.get()
                if sel:
                    try:
                        agente_sel = int(sel.split(":")[0])
                    except Exception:
                        agente_sel = None
            data = {
                "tipo_publicacion": tipo_pub_cb.get() if hasattr(tipo_pub_cb, "get") else tipo_pub_cb.get(),
                "tipo_propiedad": tipo_prop_cb.get() if hasattr(tipo_prop_cb, "get") else tipo_prop_cb.get(),
                "direccion": ent_direccion.get().strip(),
                "ciudad": ent_ciudad.get().strip(),
                "area_m2": ent_area.get().strip() or None,
                "habitaciones": ent_habs.get().strip() or None,
                "banos": ent_banos.get().strip() or None,
                "anio_construccion": ent_anio.get().strip() or None,
                "estado": estado_cb.get() if hasattr(estado_cb, "get") else estado_cb.get(),
                "fecha_publicacion": ent_fecha_pub.get().strip() or None,
                "agente_esclusivo_id": agente_sel,
            }
            if prop_id:
                ok, msg = update_propiedad(prop_id, data)
            else:
                ok, msg = insert_propiedad(data)
            if ok:
                messagebox.showinfo("OK", msg); win.destroy(); self.load_table("propiedad", getattr(self, "propiedad_tree"))
            else:
                messagebox.showerror("Error", msg)

        save_btn = ctk.CTkButton(win, text="Guardar", command=on_save); save_btn.pack(pady=10)

    def _open_precio_propiedad_form(self, pp_id: Optional[int] = None, initial: Optional[Tuple] = None):
        win = ctk.CTkToplevel(self); win.title("Precio propiedad"); win.geometry("420x360")

        ctk.CTkLabel(win, text="Propiedad (id: etiqueta)").pack(padx=8, pady=(12,2), anchor="w")
        propiedades = fetch_reference_list("propiedad", label_cols=["direccion", "ciudad"])
        prop_vals = [f"{p[0]}: {p[1]}" for p in propiedades]
        prop_cb = ctk.CTkComboBox(win, values=prop_vals) if prop_vals else ctk.CTkEntry(win); prop_cb.pack(fill="x", padx=8)

        ctk.CTkLabel(win, text="Precio").pack(padx=8, pady=(8,2), anchor="w")
        ent_precio = ctk.CTkEntry(win); ent_precio.pack(fill="x", padx=8); ent_precio.insert(0, initial[2] if initial else "")

        ctk.CTkLabel(win, text="Desde (YYYY-MM-DD)").pack(padx=8, pady=(8,2), anchor="w")
        ent_desde = ctk.CTkEntry(win); ent_desde.pack(fill="x", padx=8); ent_desde.insert(0, initial[3] if initial else "")

        ctk.CTkLabel(win, text="Hasta (YYYY-MM-DD) opcional").pack(padx=8, pady=(8,2), anchor="w")
        ent_hasta = ctk.CTkEntry(win); ent_hasta.pack(fill="x", padx=8); ent_hasta.insert(0, initial[4] if initial else "")

        def on_save():
            prop_sel = None
            if isinstance(prop_cb, ctk.CTkComboBox):
                sel = prop_cb.get()
                if sel:
                    try: prop_sel = int(sel.split(":")[0])
                    except Exception: prop_sel = None
            data = {"propiedad_id": prop_sel, "precio": ent_precio.get().strip(), "desde": ent_desde.get().strip() or None, "hasta": ent_hasta.get().strip() or None}
            if pp_id:
                ok, msg = update_precio_propiedad(pp_id, data)
            else:
                ok, msg = insert_precio_propiedad(data)
            if ok:
                messagebox.showinfo("OK", msg); win.destroy(); self.load_table("precio_propiedad", getattr(self, "precio_propiedad_tree"))
            else:
                messagebox.showerror("Error", msg)

        save_btn = ctk.CTkButton(win, text="Guardar", command=on_save); save_btn.pack(pady=8)

    def _open_visita_form(self, vis_id: Optional[int] = None, initial: Optional[Tuple] = None):
        win = ctk.CTkToplevel(self); win.title("Visita" + (" - editar" if vis_id else " - nueva")); win.geometry("520x520")

        ctk.CTkLabel(win, text="Propiedad (id: etiqueta)").pack(padx=8, pady=(12,2), anchor="w")
        propiedades = fetch_reference_list("propiedad", label_cols=["direccion","ciudad"]); prop_vals=[f"{p[0]}: {p[1]}" for p in propiedades]
        prop_cb = ctk.CTkComboBox(win, values=prop_vals) if prop_vals else ctk.CTkEntry(win); prop_cb.pack(fill="x", padx=8)

        ctk.CTkLabel(win, text="Cliente (id: etiqueta)").pack(padx=8, pady=(8,2), anchor="w")
        clientes = fetch_reference_list("cliente", label_cols=["nombre","correo"]); client_vals=[f"{c[0]}: {c[1]}" for c in clientes]
        client_cb = ctk.CTkComboBox(win, values=client_vals) if client_vals else ctk.CTkEntry(win); client_cb.pack(fill="x", padx=8)

        ctk.CTkLabel(win, text="Agente (id: etiqueta) opcional").pack(padx=8, pady=(8,2), anchor="w")
        agentes = fetch_reference_list("agente", label_cols=["nombre","correo"]); agente_vals=[f"{a[0]}: {a[1]}" for a in agentes]
        agente_cb = ctk.CTkComboBox(win, values=agente_vals) if agente_vals else ctk.CTkEntry(win); agente_cb.pack(fill="x", padx=8)

        ctk.CTkLabel(win, text="Fecha (YYYY-MM-DD)").pack(padx=8, pady=(8,2), anchor="w")
        ent_fecha = ctk.CTkEntry(win); ent_fecha.pack(fill="x", padx=8); ent_fecha.insert(0, initial[4] if initial else "")

        ctk.CTkLabel(win, text="Hora (HH:MM:SS)").pack(padx=8, pady=(8,2), anchor="w")
        ent_hora = ctk.CTkEntry(win); ent_hora.pack(fill="x", padx=8); ent_hora.insert(0, initial[5] if initial else "")

        visita_enums = _enums.get("visita", {}); estado_vals = visita_enums.get("estado", [])
        ctk.CTkLabel(win, text="Estado").pack(padx=8, pady=(8,2), anchor="w")
        estado_cb = ctk.CTkComboBox(win, values=estado_vals) if estado_vals else ctk.CTkEntry(win); estado_cb.pack(fill="x", padx=8)
        if initial and initial[6] not in ("None", ""):
            try: estado_cb.set(initial[6])
            except Exception: pass

        ctk.CTkLabel(win, text="Notas").pack(padx=8, pady=(8,2), anchor="w")
        ent_notas = ctk.CTkEntry(win); ent_notas.pack(fill="x", padx=8); ent_notas.insert(0, initial[7] if initial else "")

        def on_save():
            def sel_id(cb):
                if isinstance(cb, ctk.CTkComboBox):
                    s = cb.get()
                    if s:
                        try: return int(s.split(":")[0])
                        except Exception: return None
                else:
                    try: return int(cb.get().strip())
                    except Exception: return None

            data = {"propiedad_id": sel_id(prop_cb), "cliente_id": sel_id(client_cb), "agente_id": sel_id(agente_cb), "fecha": ent_fecha.get().strip() or None, "hora": ent_hora.get().strip() or None, "estado": estado_cb.get() if hasattr(estado_cb,"get") else estado_cb.get(), "notas": ent_notas.get().strip() or None}
            if vis_id:
                ok,msg = update_visita(vis_id, data)
            else:
                ok,msg = insert_visita(data)
            if ok:
                messagebox.showinfo("OK", msg); win.destroy(); self.load_table("visita", getattr(self, "visita_tree"))
            else:
                messagebox.showerror("Error", msg)

        save_btn = ctk.CTkButton(win, text="Guardar", command=on_save); save_btn.pack(pady=8)

    def _open_oferta_form(self, oferta_id: Optional[int] = None, initial: Optional[Tuple] = None):
        win = ctk.CTkToplevel(self); win.title("Oferta" + (" - editar" if oferta_id else " - nueva")); win.geometry("520x480")

        ctk.CTkLabel(win, text="Propiedad (id: etiqueta)").pack(padx=8, pady=(12,2), anchor="w")
        propiedades = fetch_reference_list("propiedad", label_cols=["direccion","ciudad"]); prop_vals=[f"{p[0]}: {p[1]}" for p in propiedades]
        prop_cb = ctk.CTkComboBox(win, values=prop_vals) if prop_vals else ctk.CTkEntry(win); prop_cb.pack(fill="x", padx=8)

        ctk.CTkLabel(win, text="Cliente (id: etiqueta)").pack(padx=8, pady=(8,2), anchor="w")
        clientes = fetch_reference_list("cliente", label_cols=["nombre","correo"]); client_vals=[f"{c[0]}: {c[1]}" for c in clientes]
        client_cb = ctk.CTkComboBox(win, values=client_vals) if client_vals else ctk.CTkEntry(win); client_cb.pack(fill="x", padx=8)

        ctk.CTkLabel(win, text="Fecha (YYYY-MM-DD)").pack(padx=8, pady=(8,2), anchor="w")
        ent_fecha = ctk.CTkEntry(win); ent_fecha.pack(fill="x", padx=8); ent_fecha.insert(0, initial[3] if initial else "")

        ctk.CTkLabel(win, text="Monto").pack(padx=8, pady=(8,2), anchor="w")
        ent_monto = ctk.CTkEntry(win); ent_monto.pack(fill="x", padx=8); ent_monto.insert(0, initial[4] if initial else "")

        oferta_enums = _enums.get("oferta", {}); estado_vals = oferta_enums.get("estado", [])
        ctk.CTkLabel(win, text="Estado").pack(padx=8, pady=(8,2), anchor="w")
        estado_cb = ctk.CTkComboBox(win, values=estado_vals) if estado_vals else ctk.CTkEntry(win); estado_cb.pack(fill="x", padx=8)
        if initial and initial[5] not in ("None", ""):
            try: estado_cb.set(initial[5])
            except Exception: pass

        ctk.CTkLabel(win, text="Comentarios").pack(padx=8, pady=(8,2), anchor="w")
        ent_coment = ctk.CTkEntry(win); ent_coment.pack(fill="x", padx=8); ent_coment.insert(0, initial[6] if initial else "")

        def on_save():
            def sel_id(cb):
                if isinstance(cb, ctk.CTkComboBox):
                    s = cb.get(); 
                    if s:
                        try: return int(s.split(":")[0])
                        except: return None
                return None
            data = {"propiedad_id": sel_id(prop_cb), "cliente_id": sel_id(client_cb), "fecha": ent_fecha.get().strip() or None, "monto": ent_monto.get().strip(), "estado": estado_cb.get() if hasattr(estado_cb, "get") else estado_cb.get(), "comentarios": ent_coment.get().strip() or None}
            if oferta_id:
                ok,msg = update_oferta(oferta_id, data)
            else:
                ok,msg = insert_oferta(data)
            if ok:
                messagebox.showinfo("OK", msg); win.destroy(); self.load_table("oferta", getattr(self, "oferta_tree"))
            else:
                messagebox.showerror("Error", msg)

        save_btn = ctk.CTkButton(win, text="Guardar", command=on_save); save_btn.pack(pady=8)

    def _open_transaccion_form(self, tr_id: Optional[int] = None, initial: Optional[Tuple] = None):
        win = ctk.CTkToplevel(self); win.title("Transacción" + (" - editar" if tr_id else " - nueva")); win.geometry("520x520")

        ctk.CTkLabel(win, text="Propiedad (id: etiqueta)").pack(padx=8, pady=(12,2), anchor="w")
        propiedades = fetch_reference_list("propiedad", label_cols=["direccion","ciudad"]); prop_vals=[f"{p[0]}: {p[1]}" for p in propiedades]
        prop_cb = ctk.CTkComboBox(win, values=prop_vals) if prop_vals else ctk.CTkEntry(win); prop_cb.pack(fill="x", padx=8)

        ctk.CTkLabel(win, text="Oferta (id: etiqueta) opcional").pack(padx=8, pady=(8,2), anchor="w")
        ofertas = fetch_reference_list("oferta", label_cols=["monto"]); oferta_vals=[f"{o[0]}: {o[1]}" for o in ofertas]
        oferta_cb = ctk.CTkComboBox(win, values=oferta_vals) if oferta_vals else ctk.CTkEntry(win); oferta_cb.pack(fill="x", padx=8)

        ctk.CTkLabel(win, text="Fecha cierre (YYYY-MM-DD)").pack(padx=8, pady=(8,2), anchor="w")
        ent_fecha = ctk.CTkEntry(win); ent_fecha.pack(fill="x", padx=8); ent_fecha.insert(0, initial[2] if initial else "")

        ctk.CTkLabel(win, text="Precio final").pack(padx=8, pady=(8,2), anchor="w")
        ent_precio = ctk.CTkEntry(win); ent_precio.pack(fill="x", padx=8); ent_precio.insert(0, initial[3] if initial else "")

        trans_enums = _enums.get("transaccion", {}); tipo_vals = trans_enums.get("tipo_transaccion", []); estado_vals = trans_enums.get("estado_transaccion", [])
        ctk.CTkLabel(win, text="Tipo transacción").pack(padx=8, pady=(8,2), anchor="w")
        tipo_cb = ctk.CTkComboBox(win, values=tipo_vals) if tipo_vals else ctk.CTkEntry(win); tipo_cb.pack(fill="x", padx=8)
        ctk.CTkLabel(win, text="Estado transacción").pack(padx=8, pady=(8,2), anchor="w")
        estado_cb = ctk.CTkComboBox(win, values=estado_vals) if estado_vals else ctk.CTkEntry(win); estado_cb.pack(fill="x", padx=8)
        if initial:
            try:
                if initial[4]: tipo_cb.set(initial[4])
            except Exception: pass
            try:
                if initial[5]: estado_cb.set(initial[5])
            except Exception: pass

        def on_save():
            def sel_id(cb):
                if isinstance(cb, ctk.CTkComboBox):
                    s = cb.get()
                    if s:
                        try: return int(s.split(":")[0])
                        except: return None
                return None
            data = {"propiedad_id": sel_id(prop_cb), "fecha_cierre": ent_fecha.get().strip() or None, "precio_final": ent_precio.get().strip(), "tipo_transaccion": tipo_cb.get() if hasattr(tipo_cb,"get") else tipo_cb.get(), "estado_transaccion": estado_cb.get() if hasattr(estado_cb,"get") else estado_cb.get(), "oferta_id": sel_id(oferta_cb)}
            if tr_id:
                ok,msg = update_transaccion(tr_id, data)
            else:
                ok,msg = insert_transaccion(data)
            if ok:
                messagebox.showinfo("OK", msg); win.destroy(); self.load_table("transaccion", getattr(self, "transaccion_tree"))
            else:
                messagebox.showerror("Error", msg)

        save_btn = ctk.CTkButton(win, text="Guardar", command=on_save); save_btn.pack(pady=8)

    def _open_transaccion_agente_form(self, edit_key: Optional[Tuple[int,int]] = None, initial: Optional[Tuple] = None):
        win = ctk.CTkToplevel(self); title = "Transaccion-Agente"
        win.title(title + (" - editar" if edit_key else " - nuevo")); win.geometry("520x420")

        ctk.CTkLabel(win, text="Transacción (id: etiqueta)").pack(padx=8, pady=(12,2), anchor="w")
        trans = fetch_reference_list("transaccion", label_cols=["precio_final"]); trans_vals=[f"{t[0]}: {t[1]}" for t in trans]
        trans_cb = ctk.CTkComboBox(win, values=trans_vals) if trans_vals else ctk.CTkEntry(win); trans_cb.pack(fill="x", padx=8)

        ctk.CTkLabel(win, text="Agente (id: etiqueta)").pack(padx=8, pady=(8,2), anchor="w")
        agentes = fetch_reference_list("agente", label_cols=["nombre","correo"]); agente_vals=[f"{a[0]}: {a[1]}" for a in agentes]
        agente_cb = ctk.CTkComboBox(win, values=agente_vals) if agente_vals else ctk.CTkEntry(win); agente_cb.pack(fill="x", padx=8)

        ctk.CTkLabel(win, text="Comisión monto").pack(padx=8, pady=(8,2), anchor="w")
        ent_monto = ctk.CTkEntry(win); ent_monto.pack(fill="x", padx=8); ent_monto.insert(0, initial[2] if initial else "")

        ctk.CTkLabel(win, text="Comisión porcentaje").pack(padx=8, pady=(8,2), anchor="w")
        ent_pct = ctk.CTkEntry(win); ent_pct.pack(fill="x", padx=8); ent_pct.insert(0, initial[3] if initial else "")

        if edit_key:
            tid, aid = edit_key
            try:
                matcht = [v for v in trans_vals if v.startswith(str(tid)+":")]
                if matcht: trans_cb.set(matcht[0])
                matcha = [v for v in agente_vals if v.startswith(str(aid)+":")]
                if matcha: agente_cb.set(matcha[0])
            except Exception: pass

        def on_save():
            def sel_id(cb):
                if isinstance(cb, ctk.CTkComboBox):
                    s = cb.get()
                    if s:
                        try: return int(s.split(":")[0])
                        except: return None
                return None
            tid = sel_id(trans_cb); aid = sel_id(agente_cb)
            data = {"transaccion_id": tid, "agente_id": aid, "comision_monto": ent_monto.get().strip() or None, "comision_porcentaje": ent_pct.get().strip() or None}
            if edit_key:
                ok,msg = update_transaccion_agente(edit_key[0], edit_key[1], data)
            else:
                ok,msg = insert_transaccion_agente(data)
            if ok:
                messagebox.showinfo("OK", msg); win.destroy(); self.load_table("transaccion_agente", getattr(self, "transaccion_agente_tree"))
            else:
                messagebox.showerror("Error", msg)

        save_btn = ctk.CTkButton(win, text="Guardar", command=on_save); save_btn.pack(pady=8)

    # ------------------------
    # Cola UI (para SQL worker) - ahora llena el panel propio de SQL
    # ------------------------
    def _schedule_queue(self):
        self.after(120, self._pump_queue)

    def _pump_queue(self):
        try:
            while True:
                ev, data = self.ui_queue.get_nowait()
                if ev == "sql_done":
                    ok = data.get("ok", False)
                    cols = data.get("columns", [])
                    rows = data.get("rows", [])
                    errors = data.get("errors", [])
                    elapsed = data.get("elapsed", 0.0)
                    if errors:
                        messagebox.showwarning("Ejecución SQL - Errores", f"Hubo errores. Primer error:\n{errors[0]}")
                        self.sql_status_lbl.configure(text=f"Error. Tiempo: {elapsed:.2f}s")
                    else:
                        # Mostrar filas en panel SQL (self.sql_result_tree)
                        tr = self.sql_result_tree
                        tr.delete(*tr.get_children())
                        tr["columns"] = cols
                        tr["show"] = "headings" if cols else ""
                        for c in cols:
                            tr.heading(c, text=c); tr.column(c, width=160, anchor="w")
                        for r in rows:
                            tr.insert("", "end", values=tuple("" if v is None else str(v) for v in r))
                        self.sql_status_lbl.configure(text=f"Listo. Tiempo: {elapsed:.2f}s")
        except Exception:
            pass
        finally:
            self._schedule_queue()

def main():
    if _DRIVER is None:
        root = tk.Tk(); root.withdraw()
        messagebox.showerror("Error", "No hay driver MySQL instalado. Instala 'mysqlclient' o 'PyMySQL' y vuelve a ejecutar.")
        return
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()