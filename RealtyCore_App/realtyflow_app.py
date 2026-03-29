from __future__ import annotations

import json
import queue
import threading
import time
from typing import Optional, List, Tuple, Dict, Any

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# ─── Configuración de conexión ────────────────────────────────
DB_HOST     = "127.0.0.1"
DB_PORT     = 3306
DB_USER     = "root"
DB_PASSWORD = "root"
DB_NAME     = "realtyflow_db"

# ─── Paleta de colores ────────────────────────────────────────
ACCENT       = "#14B8A6"   # teal-500
ACCENT_DARK  = "#0D9488"   # teal-600
ACCENT_LIGHT = "#99F6E4"   # teal-200
BG_CARD      = "#1E293B"   # slate-800
BG_MAIN      = "#0F172A"   # slate-900
TEXT_MUTED   = "#94A3B8"   # slate-400
TEXT_PRIMARY = "#F1F5F9"   # slate-100
DANGER       = "#F43F5E"   # rose-500
SUCCESS      = "#22C55E"   # green-500
WARNING      = "#F59E0B"   # amber-500

# ─── ENUMs por defecto (sin 'inactiva') ──────────────────────
DEFAULT_ENUMS: Dict[str, Dict[str, List[str]]] = {
    "cliente": {
        "tipo_publicacion_preferida": ["venta", "alquiler"],
        "tipo_inmueble_preferida":   ["casa", "apartamento", "terreno"],
    },
    "inmueble": {
        "tipo_publicacion": ["venta", "alquiler"],
        "tipo_inmueble":   ["casa", "apartamento", "terreno"],
        "estado":           ["disponible", "en_negociacion", "vendida", "alquilada"],
    },
    "visita":     {"estado": ["programada", "realizada", "cancelada"]},
    "oferta":     {"estado": ["pendiente", "aceptada", "rechazada"]},
    "transaccion": {
        "tipo_transaccion":   ["venta", "alquiler"],
        "estado_transaccion": ["cerrada", "cancelada"],
    },
}

_enums: Dict[str, Dict[str, List[str]]] = DEFAULT_ENUMS.copy()

# ─── Driver MySQL ─────────────────────────────────────────────
_DRIVER = None
MySQLdb = None
pymysql = None
try:
    import MySQLdb as _m  # type: ignore
    MySQLdb = _m
    _DRIVER = "mysqlclient"
except ImportError:
    pass

if _DRIVER is None:
    try:
        import pymysql as _p  # type: ignore
        pymysql = _p
        _DRIVER = "pymysql"
    except ImportError:
        pass


class DbError(Exception):
    pass


# ─────────────────────────────────────────────────────────────
# Capa de base de datos
# ─────────────────────────────────────────────────────────────

def create_connection(database: str = DB_NAME):
    if _DRIVER == "mysqlclient":
        params: dict = {
            "host": DB_HOST, "user": DB_USER, "passwd": DB_PASSWORD,
            "port": DB_PORT, "charset": "utf8mb4", "use_unicode": True,
        }
        if database:
            params["db"] = database
        return MySQLdb.connect(**params)  # type: ignore
    if _DRIVER == "pymysql":
        params = {
            "host": DB_HOST, "user": DB_USER, "password": DB_PASSWORD,
            "port": DB_PORT, "charset": "utf8mb4",
        }
        if database:
            params["database"] = database
        return pymysql.connect(**params)  # type: ignore
    raise DbError("No hay driver MySQL. Instala 'mysqlclient' o 'PyMySQL'.")


def execute_sql(sql_text: str, database: str = DB_NAME
                ) -> Tuple[bool, List[str], List[Tuple], List[str]]:
    """Ejecuta sentencias separadas por ';'. Retorna (ok, cols, rows, errors)."""
    statements = [s.strip() for s in sql_text.split(";") if s.strip()]
    if not statements:
        return False, [], [], ["Sin sentencias SQL."]
    conn = create_connection(database)
    cur  = conn.cursor()
    cols: List[str]  = []
    rows: List[Tuple] = []
    errors: List[str] = []
    ok = True
    try:
        for stmt in statements:
            try:
                cur.execute(stmt)
                if stmt.strip().lower().startswith("select"):
                    rows = list(cur.fetchall())
                    cols = [d[0] for d in (cur.description or [])]
                else:
                    conn.commit()
            except Exception as e:
                errors.append(f"{e} — {stmt[:120]}")
                ok = False
    finally:
        cur.close()
        conn.close()
    return ok, cols, rows, errors


def fetch_all(table: str) -> Tuple[List[str], List[Tuple]]:
    """Devuelve (columnas, filas) de una tabla completa."""
    conn = create_connection()
    cur  = conn.cursor()
    cur.execute(f"SELECT * FROM `{table}`")
    rows = list(cur.fetchall())
    cols = [d[0] for d in (cur.description or [])]
    cur.close(); conn.close()
    return cols, rows


def fetch_kpis() -> Dict[str, int]:
    """Consulta los KPIs del dashboard en una sola conexión."""
    conn = create_connection()
    cur  = conn.cursor()
    kpis: Dict[str, int] = {}
    queries = {
        "inmuebles":          "SELECT COUNT(*) FROM inmueble",
        "inmuebles_disp":     "SELECT COUNT(*) FROM inmueble WHERE estado='disponible'",
        "clientes":             "SELECT COUNT(*) FROM cliente",
        "agentes":              "SELECT COUNT(*) FROM agente",
        "transacciones":        "SELECT COUNT(*) FROM transaccion WHERE estado_transaccion='cerrada'",
        "ofertas_pendientes":   "SELECT COUNT(*) FROM oferta WHERE estado='pendiente'",
    }
    for key, sql in queries.items():
        try:
            cur.execute(sql)
            row = cur.fetchone()
            kpis[key] = int(row[0]) if row else 0
        except Exception:
            kpis[key] = 0
    cur.close(); conn.close()
    return kpis


def fetch_reference_list(table: str, label_cols: List[str] = None
                          ) -> List[Tuple[int, str]]:
    """Devuelve [(id, etiqueta)] para usar en combobox de FK."""
    cols, rows = fetch_all(table)
    col_idx = {c: i for i, c in enumerate(cols)}
    result: List[Tuple[int, str]] = []
    for r in rows:
        rid = r[col_idx.get("id", 0)]
        if label_cols:
            label = " – ".join(str(r[col_idx[c]]) for c in label_cols if c in col_idx)
        else:
            label = str(r[col_idx.get("nombre", col_idx.get("direccion", 1))])
        result.append((rid, label))
    return result


def run_crud(sql: str, params: tuple = ()) -> Tuple[bool, str]:
    """Ejecuta INSERT/UPDATE/DELETE con parámetros."""
    try:
        conn = create_connection()
        cur  = conn.cursor()
        cur.execute(sql, params)
        conn.commit()
        cur.close(); conn.close()
        return True, "OK"
    except Exception as e:
        return False, str(e)


# ─────────────────────────────────────────────────────────────
# CRUD por tabla — ajustado a modelo v5
# ─────────────────────────────────────────────────────────────

# ── Ciudad ────────────────────────────────────────────────────
def insert_ciudad(d: dict)         -> Tuple[bool, str]:
    return run_crud("INSERT INTO ciudad (nombre,departamento,region) VALUES (%s,%s,%s)",
                    (d.get("nombre"), d.get("departamento"), d.get("region")))

def update_ciudad(cid: int, d: dict) -> Tuple[bool, str]:
    return run_crud("UPDATE ciudad SET nombre=%s,departamento=%s,region=%s WHERE id=%s",
                    (d.get("nombre"), d.get("departamento"), d.get("region"), cid))

def delete_ciudad(cid: int)        -> Tuple[bool, str]:
    return run_crud("DELETE FROM ciudad WHERE id=%s", (cid,))


# ── Agente ────────────────────────────────────────────────────
def insert_agente(d: dict)             -> Tuple[bool, str]:
    return run_crud(
        "INSERT INTO agente (nombre,telefono,correo,porcentaje_comision,fecha_ingreso,estado,ciudad_id) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s)",
        (d["nombre"], d["telefono"], d["correo"],
         d.get("porcentaje_comision") or 3.0,
         d.get("fecha_ingreso") or None,
         1 if d.get("estado", True) else 0,
         d.get("ciudad_id") or None))

def update_agente(aid: int, d: dict)   -> Tuple[bool, str]:
    return run_crud(
        "UPDATE agente SET nombre=%s,telefono=%s,correo=%s,porcentaje_comision=%s,"
        "fecha_ingreso=%s,estado=%s,ciudad_id=%s WHERE id=%s",
        (d["nombre"], d["telefono"], d["correo"],
         d.get("porcentaje_comision") or 3.0,
         d.get("fecha_ingreso") or None,
         1 if d.get("estado", True) else 0,
         d.get("ciudad_id") or None, aid))

def delete_agente(aid: int)            -> Tuple[bool, str]:
    return run_crud("DELETE FROM agente WHERE id=%s", (aid,))


# ── Cliente ───────────────────────────────────────────────────
def insert_cliente(d: dict)            -> Tuple[bool, str]:
    return run_crud(
        "INSERT INTO cliente (nombre,telefono,correo,tipo_publicacion_preferida,"
        "tipo_inmueble_preferida,ciudad_preferida_id,presupuesto_min,presupuesto_max) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        (d["nombre"], d["telefono"], d["correo"],
         d.get("tipo_publicacion_preferida") or None,
         d.get("tipo_inmueble_preferida") or None,
         d.get("ciudad_preferida_id") or None,
         d.get("presupuesto_min") or 0,
         d.get("presupuesto_max") or 0))

def update_cliente(cid: int, d: dict)  -> Tuple[bool, str]:
    return run_crud(
        "UPDATE cliente SET nombre=%s,telefono=%s,correo=%s,"
        "tipo_publicacion_preferida=%s,tipo_inmueble_preferida=%s,"
        "ciudad_preferida_id=%s,presupuesto_min=%s,presupuesto_max=%s WHERE id=%s",
        (d["nombre"], d["telefono"], d["correo"],
         d.get("tipo_publicacion_preferida") or None,
         d.get("tipo_inmueble_preferida") or None,
         d.get("ciudad_preferida_id") or None,
         d.get("presupuesto_min") or 0,
         d.get("presupuesto_max") or 0, cid))

def delete_cliente(cid: int)           -> Tuple[bool, str]:
    return run_crud("DELETE FROM cliente WHERE id=%s", (cid,))


# ── inmueble ─────────────────────────────────────────────────
def insert_inmueble(d: dict)          -> Tuple[bool, str]:
    return run_crud(
        "INSERT INTO inmueble (tipo_publicacion,tipo_inmueble,direccion,ciudad_id,"
        "area_m2,habitaciones,banos,anio_construccion,estado,fecha_publicacion,agente_exclusivo_id) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (d["tipo_publicacion"], d["tipo_inmueble"], d["direccion"],
         d.get("ciudad_id") or None,
         d.get("area_m2"), d.get("habitaciones") or 0,
         d.get("banos") or 0, d.get("anio_construccion") or None,
         d.get("estado") or "disponible",
         d.get("fecha_publicacion") or None,
         d.get("agente_exclusivo_id") or None))

def update_inmueble(pid: int, d: dict) -> Tuple[bool, str]:
    return run_crud(
        "UPDATE inmueble SET tipo_publicacion=%s,tipo_inmueble=%s,direccion=%s,"
        "ciudad_id=%s,area_m2=%s,habitaciones=%s,banos=%s,anio_construccion=%s,"
        "estado=%s,fecha_publicacion=%s,agente_exclusivo_id=%s WHERE id=%s",
        (d["tipo_publicacion"], d["tipo_inmueble"], d["direccion"],
         d.get("ciudad_id") or None,
         d.get("area_m2"), d.get("habitaciones") or 0,
         d.get("banos") or 0, d.get("anio_construccion") or None,
         d.get("estado") or "disponible",
         d.get("fecha_publicacion") or None,
         d.get("agente_exclusivo_id") or None, pid))

def delete_inmueble(pid: int)         -> Tuple[bool, str]:
    return run_crud("DELETE FROM inmueble WHERE id=%s", (pid,))


# ── Precio inmueble ──────────────────────────────────────────
def insert_precio(d: dict)             -> Tuple[bool, str]:
    return run_crud(
        "INSERT INTO precio (inmueble_id,precio,desde,hasta) VALUES (%s,%s,%s,%s)",
        (d.get("inmueble_id"), d.get("precio"), d.get("desde"), d.get("hasta") or None))

def update_precio(ppid: int, d: dict)  -> Tuple[bool, str]:
    return run_crud(
        "UPDATE precio SET inmueble_id=%s,precio=%s,desde=%s,hasta=%s WHERE id=%s",
        (d.get("inmueble_id"), d.get("precio"), d.get("desde"), d.get("hasta") or None, ppid))

def delete_precio(ppid: int)           -> Tuple[bool, str]:
    return run_crud("DELETE FROM precio WHERE id=%s", (ppid,))


# ── Visita ────────────────────────────────────────────────────
def insert_visita(d: dict)             -> Tuple[bool, str]:
    return run_crud(
        "INSERT INTO visita (inmueble_id,cliente_id,agente_id,fecha,hora,estado,notas) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s)",
        (d.get("inmueble_id"), d.get("cliente_id"), d.get("agente_id") or None,
         d.get("fecha"), d.get("hora"), d.get("estado"), d.get("notas")))

def update_visita(vid: int, d: dict)   -> Tuple[bool, str]:
    return run_crud(
        "UPDATE visita SET inmueble_id=%s,cliente_id=%s,agente_id=%s,"
        "fecha=%s,hora=%s,estado=%s,notas=%s WHERE id=%s",
        (d.get("inmueble_id"), d.get("cliente_id"), d.get("agente_id") or None,
         d.get("fecha"), d.get("hora"), d.get("estado"), d.get("notas"), vid))

def delete_visita(vid: int)            -> Tuple[bool, str]:
    return run_crud("DELETE FROM visita WHERE id=%s", (vid,))


# ── Oferta ────────────────────────────────────────────────────
def insert_oferta(d: dict)             -> Tuple[bool, str]:
    return run_crud(
        "INSERT INTO oferta (inmueble_id,cliente_id,fecha,monto,estado,comentarios) "
        "VALUES (%s,%s,%s,%s,%s,%s)",
        (d.get("inmueble_id"), d.get("cliente_id"),
         d.get("fecha") or None, d.get("monto"),
         d.get("estado"), d.get("comentarios")))

def update_oferta(oid: int, d: dict)   -> Tuple[bool, str]:
    return run_crud(
        "UPDATE oferta SET inmueble_id=%s,cliente_id=%s,fecha=%s,"
        "monto=%s,estado=%s,comentarios=%s WHERE id=%s",
        (d.get("inmueble_id"), d.get("cliente_id"),
         d.get("fecha") or None, d.get("monto"),
         d.get("estado"), d.get("comentarios"), oid))

def delete_oferta(oid: int)            -> Tuple[bool, str]:
    return run_crud("DELETE FROM oferta WHERE id=%s", (oid,))


# ── Transaccion ───────────────────────────────────────────────
def insert_transaccion(d: dict)        -> Tuple[bool, str]:
    return run_crud(
        "INSERT INTO transaccion (inmueble_id,cliente_id,fecha_cierre,precio_final,"
        "tipo_transaccion,estado_transaccion,oferta_id) VALUES (%s,%s,%s,%s,%s,%s,%s)",
        (d.get("inmueble_id"), d.get("cliente_id"),
         d.get("fecha_cierre") or None, d.get("precio_final"),
         d.get("tipo_transaccion"), d.get("estado_transaccion"),
         d.get("oferta_id") or None))

def update_transaccion(tid: int, d: dict) -> Tuple[bool, str]:
    return run_crud(
        "UPDATE transaccion SET inmueble_id=%s,cliente_id=%s,fecha_cierre=%s,"
        "precio_final=%s,tipo_transaccion=%s,estado_transaccion=%s,oferta_id=%s WHERE id=%s",
        (d.get("inmueble_id"), d.get("cliente_id"),
         d.get("fecha_cierre") or None, d.get("precio_final"),
         d.get("tipo_transaccion"), d.get("estado_transaccion"),
         d.get("oferta_id") or None, tid))

def delete_transaccion(tid: int)       -> Tuple[bool, str]:
    return run_crud("DELETE FROM transaccion WHERE id=%s", (tid,))


# ── Transaccion_agente ────────────────────────────────────────
def insert_ta(d: dict)                 -> Tuple[bool, str]:
    return run_crud(
        "INSERT INTO transaccion_agente (transaccion_id,agente_id,comision_monto,comision_porcentaje) "
        "VALUES (%s,%s,%s,%s)",
        (d.get("transaccion_id"), d.get("agente_id"),
         d.get("comision_monto") or None, d.get("comision_porcentaje") or 0))

def update_ta(tid: int, aid: int, d: dict) -> Tuple[bool, str]:
    return run_crud(
        "UPDATE transaccion_agente SET comision_monto=%s,comision_porcentaje=%s "
        "WHERE transaccion_id=%s AND agente_id=%s",
        (d.get("comision_monto") or None, d.get("comision_porcentaje") or 0, tid, aid))

def delete_ta(tid: int, aid: int)      -> Tuple[bool, str]:
    return run_crud("DELETE FROM transaccion_agente WHERE transaccion_id=%s AND agente_id=%s", (tid, aid))


# ─────────────────────────────────────────────────────────────
# Worker SQL asíncrono
# ─────────────────────────────────────────────────────────────

class SqlWorker(threading.Thread):
    def __init__(self, sql: str, q: queue.Queue):
        super().__init__(daemon=True)
        self.sql = sql
        self.q   = q

    def run(self):
        t0 = time.time()
        try:
            ok, cols, rows, errors = execute_sql(self.sql)
            self.q.put(("sql_done", {
                "ok": ok, "columns": cols, "rows": rows,
                "errors": errors, "elapsed": time.time() - t0,
            }))
        except Exception as e:
            self.q.put(("sql_done", {
                "ok": False, "columns": [], "rows": [],
                "errors": [str(e)], "elapsed": time.time() - t0,
            }))


# ─────────────────────────────────────────────────────────────
# Utilidades de formulario
# ─────────────────────────────────────────────────────────────

def _sel_id(widget) -> Optional[int]:
    """Extrae el id entero de un combobox con formato 'id: etiqueta'."""
    val = widget.get() if hasattr(widget, "get") else ""
    if val:
        try:
            return int(str(val).split(":")[0].strip())
        except ValueError:
            pass
    return None


def _str(widget, default="") -> str:
    return widget.get().strip() if hasattr(widget, "get") else default


def _lbl(parent, text: str):
    return ctk.CTkLabel(parent, text=text, anchor="w",
                        text_color=TEXT_MUTED, font=("", 12))


def _entry(parent, value="") -> ctk.CTkEntry:
    e = ctk.CTkEntry(parent, height=36,
                     fg_color=BG_MAIN, border_color=ACCENT_DARK,
                     text_color=TEXT_PRIMARY)
    e.insert(0, str(value) if value not in (None, "None", "") else "")
    return e


def _combo(parent, values: list, value="") -> ctk.CTkComboBox:
    cb = ctk.CTkComboBox(parent, values=values, height=36,
                         fg_color=BG_MAIN, border_color=ACCENT_DARK,
                         button_color=ACCENT_DARK, dropdown_fg_color=BG_CARD,
                         text_color=TEXT_PRIMARY)
    if value and str(value) not in ("None", ""):
        cb.set(str(value))
    return cb


def _cities_combo(parent, selected_id=None) -> ctk.CTkComboBox:
    cities = fetch_reference_list("ciudad")
    vals   = [f"{c[0]}: {c[1]}" for c in cities]
    cb     = _combo(parent, vals)
    if selected_id:
        match = [v for v in vals if v.startswith(f"{selected_id}:")]
        if match:
            cb.set(match[0])
    return cb


def _form_window(master, title: str, width=500, height=600) -> Tuple[ctk.CTkToplevel, ctk.CTkScrollableFrame]:
    """Abre una ventana de formulario con fondo oscuro y frame scrollable."""
    win = ctk.CTkToplevel(master)
    win.title(title)
    win.geometry(f"{width}x{height}")
    win.configure(fg_color=BG_MAIN)
    win.grab_set()
    frame = ctk.CTkScrollableFrame(win, fg_color=BG_MAIN,
                                   scrollbar_button_color=ACCENT_DARK)
    frame.pack(fill="both", expand=True, padx=16, pady=16)
    return win, frame


def _save_btn(parent, command) -> ctk.CTkButton:
    return ctk.CTkButton(parent, text="Guardar", height=40,
                         fg_color=ACCENT, hover_color=ACCENT_DARK,
                         text_color=BG_MAIN, font=("", 14, "bold"),
                         command=command)


# ─────────────────────────────────────────────────────────────
# Aplicación principal
# ─────────────────────────────────────────────────────────────

class App(ctk.CTk):

    # ── Tablas y columnas de vista ────────────────────────────
    TABLE_COLS: Dict[str, List[str]] = {
        "ciudad":             ["id","nombre","departamento","region"],
        "agente":             ["id","nombre","telefono","correo","porcentaje_comision","fecha_ingreso","estado","ciudad_id"],
        "cliente":            ["id","nombre","telefono","correo","tipo_publicacion_preferida","tipo_inmueble_preferida","ciudad_preferida_id","presupuesto_min","presupuesto_max"],
        "inmueble":          ["id","tipo_publicacion","tipo_inmueble","direccion","ciudad_id","area_m2","habitaciones","banos","anio_construccion","estado","fecha_publicacion","agente_exclusivo_id"],
        "precio":   ["id","inmueble_id","precio","desde","hasta"],
        "visita":             ["id","inmueble_id","cliente_id","agente_id","fecha","hora","estado","notas"],
        "oferta":             ["id","inmueble_id","cliente_id","fecha","monto","estado","comentarios"],
        "transaccion":        ["id","inmueble_id","cliente_id","fecha_cierre","precio_final","tipo_transaccion","estado_transaccion","oferta_id"],
        "transaccion_agente": ["transaccion_id","agente_id","comision_monto","comision_porcentaje"],
    }

    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("RealtyFlow — Gestor")
        self.geometry("1280x780")
        self.configure(fg_color=BG_MAIN)

        self.ui_queue: queue.Queue = queue.Queue()
        self._trees: Dict[str, ttk.Treeview] = {}

        self._build_ui()
        self._poll_queue()

    # ── Layout principal ──────────────────────────────────────
    def _build_ui(self):
        # Sidebar
        sidebar = ctk.CTkFrame(self, width=200, fg_color=BG_CARD, corner_radius=0)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        ctk.CTkLabel(sidebar, text="RealtyFlow", font=("", 20, "bold"),
                     text_color=ACCENT).pack(pady=(24, 4), padx=16)
        ctk.CTkLabel(sidebar, text="Sistema de gestión",
                     text_color=TEXT_MUTED, font=("", 11)).pack(padx=16, pady=(0, 24))

        self._tab_view = ctk.CTkTabview(self, fg_color=BG_MAIN,
                                        segmented_button_fg_color=BG_CARD,
                                        segmented_button_selected_color=ACCENT,
                                        segmented_button_selected_hover_color=ACCENT_DARK,
                                        segmented_button_unselected_color=BG_CARD,
                                        text_color=TEXT_PRIMARY)
        self._tab_view.pack(side="left", fill="both", expand=True, padx=0, pady=0)

        # Tabs
        self._tab_view.add("Inicio")
        self._tab_view.add("Terminal SQL")
        for t in self.TABLE_COLS:
            self._tab_view.add(t)

        # Botones sidebar
        nav_items = [("Inicio", "Inicio"), ("Terminal SQL", "Terminal SQL")] + [(t, t) for t in self.TABLE_COLS]
        for label, tab_name in nav_items:
            b = ctk.CTkButton(sidebar, text=label, height=36, anchor="w",
                              fg_color="transparent", hover_color=BG_MAIN,
                              text_color=TEXT_PRIMARY, font=("", 13),
                              command=lambda n=tab_name: self._tab_view.set(n))
            b.pack(fill="x", padx=8, pady=2)

        # Construir contenido de cada tab
        self._build_dashboard(self._tab_view.tab("Inicio"))
        self._build_sql_tab(self._tab_view.tab("Terminal SQL"))
        for t in self.TABLE_COLS:
            self._build_table_tab(t, self._tab_view.tab(t))

    # ── Dashboard ─────────────────────────────────────────────
    def _build_dashboard(self, parent):
        parent.configure(fg_color=BG_MAIN)

        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(24, 4))
        ctk.CTkLabel(header, text="Panel de control", font=("", 22, "bold"),
                     text_color=TEXT_PRIMARY).pack(side="left")
        self._dash_status = ctk.CTkLabel(header, text="", text_color=TEXT_MUTED, font=("", 12))
        self._dash_status.pack(side="right")
        refresh_btn = ctk.CTkButton(header, text="Actualizar", width=110, height=32,
                                    fg_color=ACCENT, hover_color=ACCENT_DARK,
                                    text_color=BG_MAIN, font=("", 12),
                                    command=self.refresh_dashboard)
        refresh_btn.pack(side="right", padx=8)

        # Fila de tarjetas KPI
        self._kpi_frame = ctk.CTkFrame(parent, fg_color="transparent")
        self._kpi_frame.pack(fill="x", padx=24, pady=12)

        kpi_defs = [
            ("inmuebles",        "inmuebles",          "total en portafolio",  ACCENT,   "inmueble"),
            ("inmuebles_disp",   "Disponibles",          "en portafolio activo", "#60A5FA","inmueble"),
            ("clientes",           "Clientes",             "registrados",          "#A78BFA","cliente"),
            ("agentes",            "Agentes activos",      "en todas las sedes",   SUCCESS,  "agente"),
            ("transacciones",      "Cierres",              "transacciones cerradas",WARNING, "transaccion"),
            ("ofertas_pendientes", "Ofertas pendientes",   "últimos 90 días",      DANGER,   "oferta"),
        ]

        self._kpi_labels: Dict[str, ctk.CTkLabel] = {}

        for col_idx, (key, title, subtitle, color, nav_tab) in enumerate(kpi_defs):
            card = ctk.CTkFrame(self._kpi_frame, fg_color=BG_CARD,
                                corner_radius=14, border_width=1,
                                border_color=color)
            card.grid(row=0, column=col_idx, padx=8, sticky="nsew")
            self._kpi_frame.grid_columnconfigure(col_idx, weight=1)


            ctk.CTkLabel(card, text=title, font=("", 13, "bold"),
                         text_color=TEXT_MUTED).pack(anchor="w", padx=14, pady=(12, 0))

            val_lbl = ctk.CTkLabel(card, text="—", font=("", 32, "bold"),
                                   text_color=color)
            val_lbl.pack(anchor="w", padx=14, pady=(2, 0))
            self._kpi_labels[key] = val_lbl

            ctk.CTkLabel(card, text=subtitle, font=("", 11),
                         text_color=TEXT_MUTED).pack(anchor="w", padx=14, pady=(0, 8))

            manage_btn = ctk.CTkButton(card, text="Gestionar ⨠", height=30,
                                       fg_color="transparent", hover_color=BG_MAIN,
                                       text_color=color, font=("", 12),
                                       border_width=1, border_color=color,
                                       command=lambda t=nav_tab: self._tab_view.set(t))
            manage_btn.pack(fill="x", padx=12, pady=(0, 12))

        # Sección de resumen inferior
        bottom = ctk.CTkFrame(parent, fg_color="transparent")
        bottom.pack(fill="both", expand=True, padx=24, pady=8)
        bottom.grid_columnconfigure(0, weight=1)
        bottom.grid_columnconfigure(1, weight=1)

        # Últimas inmuebles disponibles
        left_card = ctk.CTkFrame(bottom, fg_color=BG_CARD, corner_radius=12)
        left_card.grid(row=0, column=0, padx=(0, 8), sticky="nsew")
        ctk.CTkLabel(left_card, text="Últimas inmuebles disponibles",
                     font=("", 14, "bold"), text_color=ACCENT).pack(anchor="w", padx=14, pady=(14, 6))
        self._recent_tree = self._mini_tree(left_card, ["ID","Tipo","Ciudad","Año de Construcción","Estado"])


        self.refresh_dashboard()

    def _mini_tree(self, parent, cols: List[str]) -> ttk.Treeview:
        style = ttk.Style()
        style.configure("Mini.Treeview", background=BG_CARD,
                        fieldbackground=BG_CARD, foreground=TEXT_PRIMARY,
                        rowheight=26, font=("", 11))
        style.configure("Mini.Treeview.Heading", background=BG_MAIN,
                        foreground=ACCENT_LIGHT, font=("", 11, "bold"))
        tr = ttk.Treeview(parent, columns=cols, show="headings",
                          style="Mini.Treeview", height=8)
        for c in cols:
            tr.heading(c, text=c)
            tr.column(c, width=120, anchor="w")
        tr.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        return tr

    def refresh_dashboard(self):
        try:
            kpis = fetch_kpis()
            for key, lbl in self._kpi_labels.items():
                lbl.configure(text=f"{kpis.get(key, 0):,}")

            # Últimas inmuebles disponibles
            _, rows = fetch_all("inmueble")
            self._recent_tree.delete(*self._recent_tree.get_children())
            _, rcols = fetch_all("inmueble")  # ignorar, usamos rows
            cols_p, rows_p = fetch_all("inmueble")
            ci = {c: i for i, c in enumerate(cols_p)}
            disp = [r for r in rows_p if str(r[ci.get("estado","")]) == "disponible"][-10:]
            for r in reversed(disp):
                self._recent_tree.insert("", "end", values=(
                    r[ci.get("id",0)], r[ci.get("tipo_inmueble",2)],
                    r[ci.get("ciudad_id",4)], r[ci.get("anio_construccion",5)], r[ci.get("estado",9)],
                ))


            self._dash_status.configure(
                text=f"Actualizado — {time.strftime('%H:%M:%S')}", text_color=TEXT_MUTED)
        except Exception as e:
            self._dash_status.configure(text=f"Error: {e}", text_color=DANGER)

    # ── Tab SQL ───────────────────────────────────────────────
    def _build_sql_tab(self, parent):
        parent.configure(fg_color=BG_MAIN)
        parent.grid_rowconfigure(2, weight=1)
        parent.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(parent, text="Consola SQL", font=("", 16, "bold"),
                     text_color=TEXT_PRIMARY).grid(row=0, column=0, sticky="w", padx=16, pady=(16, 4))

        self.sql_text = tk.Text(parent, height=10, wrap="none",
                                bg=BG_CARD, fg=TEXT_PRIMARY, insertbackground=ACCENT,
                                font=("Courier New", 12), relief="flat",
                                selectbackground=ACCENT_DARK)
        self.sql_text.grid(row=1, column=0, sticky="nsew", padx=16, pady=4)

        ctk.CTkLabel(parent, text="Resultado", font=("", 13),
                     text_color=TEXT_MUTED).grid(row=2, column=0, sticky="w", padx=16, pady=(8, 2))

        result_frame = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=8)
        result_frame.grid(row=3, column=0, sticky="nsew", padx=16, pady=(0, 8))
        parent.grid_rowconfigure(3, weight=1)

        self.sql_tree = ttk.Treeview(result_frame, style="Mini.Treeview")
        self.sql_tree.pack(fill="both", expand=True, padx=4, pady=4)

        bar = ctk.CTkFrame(parent, fg_color="transparent")
        bar.grid(row=4, column=0, sticky="ew", padx=16, pady=8)

        ctk.CTkButton(bar, text="Abrir .sql", width=120, height=36,
                      fg_color=BG_CARD, hover_color=ACCENT_DARK,
                      text_color=TEXT_PRIMARY, command=self._open_sql_file).grid(row=0, column=0, padx=4)
        ctk.CTkButton(bar, text="Ejecutar  ▶", width=140, height=36,
                      fg_color=ACCENT, hover_color=ACCENT_DARK,
                      text_color=BG_MAIN, font=("", 13, "bold"),
                      command=self._run_sql).grid(row=0, column=1, padx=4)
        ctk.CTkButton(bar, text="Cargar enums (.json)", width=180, height=36,
                      fg_color=BG_CARD, hover_color=ACCENT_DARK,
                      text_color=TEXT_PRIMARY, command=self._load_enums).grid(row=0, column=2, padx=4)
        self.sql_status = ctk.CTkLabel(bar, text="Listo", text_color=TEXT_MUTED, font=("", 12))
        self.sql_status.grid(row=0, column=3, padx=12, sticky="w")

    def _open_sql_file(self):
        path = filedialog.askopenfilename(filetypes=[("SQL","*.sql"),("Todos","*.*")])
        if path:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                self.sql_text.delete("1.0","end")
                self.sql_text.insert("1.0", f.read())

    def _run_sql(self):
        sql = self.sql_text.get("1.0","end").strip()
        if not sql:
            return
        self.sql_status.configure(text="Ejecutando…", text_color=WARNING)
        SqlWorker(sql, self.ui_queue).start()

    def _load_enums(self):
        path = filedialog.askopenfilename(filetypes=[("JSON","*.json"),("Todos","*.*")])
        if path:
            with open(path, "r", encoding="utf-8") as f:
                global _enums
                _enums = json.load(f)
            messagebox.showinfo("Enums", "Enums actualizados.")

    # ── Tab por tabla ─────────────────────────────────────────
    def _build_table_tab(self, table: str, parent):
        parent.configure(fg_color=BG_MAIN)
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)

        cols = self.TABLE_COLS[table]

        style = ttk.Style()
        style.configure("RF.Treeview", background=BG_CARD,
                        fieldbackground=BG_CARD, foreground=TEXT_PRIMARY,
                        rowheight=28, font=("", 12))
        style.configure("RF.Treeview.Heading", background=BG_MAIN,
                        foreground=ACCENT_LIGHT, font=("", 12, "bold"))
        style.map("RF.Treeview", background=[("selected", ACCENT_DARK)])

        frame = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=10)
        frame.grid(row=0, column=0, sticky="nsew", padx=16, pady=16)
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        tree = ttk.Treeview(frame, columns=cols, show="headings", style="RF.Treeview")
        for c in cols:
            tree.heading(c, text=c)
            tree.column(c, width=max(80, 160 if c in ("nombre","direccion","correo") else 100), anchor="w")
        tree.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)

        sb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        sb.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=sb.set)

        self._trees[table] = tree

        btn_row = ctk.CTkFrame(parent, fg_color="transparent")
        btn_row.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 12))

        for txt, cmd_fn, color in [
            ("+ Nuevo",    lambda t=table: self._on_new(t),         ACCENT),
            ("✎ Editar",   lambda t=table: self._on_edit(t),        "#60A5FA"),
            ("✕ Eliminar", lambda t=table: self._on_delete(t),      DANGER),
            ("↻ Refrescar",lambda t=table: self._load_tree(t),      TEXT_MUTED),
        ]:
            ctk.CTkButton(btn_row, text=txt, height=36, width=120,
                          fg_color=BG_CARD, hover_color=BG_MAIN,
                          text_color=color, border_color=color, border_width=1,
                          command=cmd_fn).pack(side="left", padx=6)

        self._load_tree(table)

    def _load_tree(self, table: str):
        tree = self._trees.get(table)
        if not tree:
            return
        try:
            _, rows = fetch_all(table)
            tree.delete(*tree.get_children())
            for r in rows:
                tree.insert("", "end",
                            values=tuple("" if v is None else str(v) for v in r))
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo cargar {table}:\n{e}")

    def _selected_values(self, table: str) -> Optional[tuple]:
        tree = self._trees.get(table)
        sel  = tree.selection() if tree else []
        return tree.item(sel[0], "values") if sel else None

    # ── Handlers CRUD ─────────────────────────────────────────
    def _on_new(self, table: str):
        self._open_form(table, None, None)

    def _on_edit(self, table: str):
        vals = self._selected_values(table)
        if not vals:
            messagebox.showinfo("Info", "Selecciona un registro para editar.")
            return
        self._open_form(table, vals, vals)

    def _on_delete(self, table: str):
        vals = self._selected_values(table)
        if not vals:
            messagebox.showinfo("Info", "Selecciona un registro para eliminar.")
            return
        if not messagebox.askyesno("Confirmar", f"¿Eliminar el registro seleccionado de {table}?"):
            return
        fn_map = {
            "ciudad": lambda: delete_ciudad(int(vals[0])),
            "agente": lambda: delete_agente(int(vals[0])),
            "cliente": lambda: delete_cliente(int(vals[0])),
            "inmueble": lambda: delete_inmueble(int(vals[0])),
            "precio": lambda: delete_precio(int(vals[0])),
            "visita": lambda: delete_visita(int(vals[0])),
            "oferta": lambda: delete_oferta(int(vals[0])),
            "transaccion": lambda: delete_transaccion(int(vals[0])),
            "transaccion_agente": lambda: delete_ta(int(vals[0]), int(vals[1])),
        }
        fn = fn_map.get(table)
        if fn:
            ok, msg = fn()
            (messagebox.showinfo if ok else messagebox.showerror)("Resultado", msg)
            if ok:
                self._load_tree(table)
        else:
            messagebox.showinfo("Info", f"Eliminar no implementado para {table}.")

    # ── Formularios ───────────────────────────────────────────
    def _open_form(self, table: str, edit_vals: Optional[tuple], initial: Optional[tuple]):
        dispatch = {
            "ciudad":             self._form_ciudad,
            "agente":             self._form_agente,
            "cliente":            self._form_cliente,
            "inmueble":          self._form_inmueble,
            "precio":   self._form_precio,
            "visita":             self._form_visita,
            "oferta":             self._form_oferta,
            "transaccion":        self._form_transaccion,
            "transaccion_agente": self._form_ta,
        }
        fn = dispatch.get(table)
        if fn:
            fn(edit_vals)
        else:
            messagebox.showinfo("Info", f"Formulario no implementado para {table}.")

    def _after_save(self, table: str, win):
        self._load_tree(table)
        self.refresh_dashboard()
        win.destroy()

    # Ciudad
    def _form_ciudad(self, vals=None):
        is_edit = vals is not None
        win, f = _form_window(self, "Ciudad – " + ("editar" if is_edit else "nuevo"))
        _lbl(f, "Nombre *").pack(anchor="w", pady=(8,0))
        e_nombre = _entry(f, vals[1] if is_edit else ""); e_nombre.pack(fill="x")
        _lbl(f, "Departamento").pack(anchor="w", pady=(8,0))
        e_dep = _entry(f, vals[2] if is_edit else ""); e_dep.pack(fill="x")
        _lbl(f, "Región").pack(anchor="w", pady=(8,0))
        e_reg = _entry(f, vals[3] if is_edit else ""); e_reg.pack(fill="x")

        def save():
            if not _str(e_nombre):
                messagebox.showerror("Error", "El nombre es obligatorio."); return
            d = {"nombre": _str(e_nombre), "departamento": _str(e_dep) or None, "region": _str(e_reg) or None}
            ok, msg = update_ciudad(int(vals[0]), d) if is_edit else insert_ciudad(d)
            (messagebox.showinfo if ok else messagebox.showerror)("Resultado", msg)
            if ok: self._after_save("ciudad", win)
        _save_btn(f, save).pack(fill="x", pady=(16, 0))

    # Agente
    def _form_agente(self, vals=None):
        is_edit = vals is not None
        win, f = _form_window(self, "Agente – " + ("editar" if is_edit else "nuevo"))
        _lbl(f, "Nombre *").pack(anchor="w", pady=(8,0))
        e_n = _entry(f, vals[1] if is_edit else ""); e_n.pack(fill="x")
        _lbl(f, "Teléfono *").pack(anchor="w", pady=(8,0))
        e_t = _entry(f, vals[2] if is_edit else ""); e_t.pack(fill="x")
        _lbl(f, "Correo *").pack(anchor="w", pady=(8,0))
        e_m = _entry(f, vals[3] if is_edit else ""); e_m.pack(fill="x")
        _lbl(f, "Porcentaje comisión").pack(anchor="w", pady=(8,0))
        e_p = _entry(f, vals[4] if is_edit else "3.0"); e_p.pack(fill="x")
        _lbl(f, "Fecha ingreso (YYYY-MM-DD)").pack(anchor="w", pady=(8,0))
        e_fi = _entry(f, vals[5] if is_edit else ""); e_fi.pack(fill="x")
        _lbl(f, "Ciudad (sede) *").pack(anchor="w", pady=(8,0))
        cb_ciudad = _cities_combo(f, vals[7] if is_edit else None); cb_ciudad.pack(fill="x")
        est_var = tk.IntVar(value=1 if (is_edit and str(vals[6]) in ("1","True")) else 1)
        ctk.CTkCheckBox(f, text="Agente activo", variable=est_var,
                        text_color=TEXT_PRIMARY, fg_color=ACCENT,
                        hover_color=ACCENT_DARK).pack(anchor="w", pady=(10,0))

        def save():
            if not _str(e_n) or not _str(e_t) or not _str(e_m):
                messagebox.showerror("Error", "Nombre, teléfono y correo son obligatorios."); return
            d = {"nombre": _str(e_n), "telefono": _str(e_t), "correo": _str(e_m),
                 "porcentaje_comision": _str(e_p) or 3.0,
                 "fecha_ingreso": _str(e_fi) or None,
                 "estado": bool(est_var.get()),
                 "ciudad_id": _sel_id(cb_ciudad)}
            ok, msg = update_agente(int(vals[0]), d) if is_edit else insert_agente(d)
            (messagebox.showinfo if ok else messagebox.showerror)("Resultado", msg)
            if ok: self._after_save("agente", win)
        _save_btn(f, save).pack(fill="x", pady=(16, 0))

    # Cliente
    def _form_cliente(self, vals=None):
        is_edit = vals is not None
        win, f = _form_window(self, "Cliente – " + ("editar" if is_edit else "nuevo"), height=680)
        _lbl(f, "Nombre *").pack(anchor="w", pady=(8,0))
        e_n = _entry(f, vals[1] if is_edit else ""); e_n.pack(fill="x")
        _lbl(f, "Teléfono *").pack(anchor="w", pady=(8,0))
        e_t = _entry(f, vals[2] if is_edit else ""); e_t.pack(fill="x")
        _lbl(f, "Correo *").pack(anchor="w", pady=(8,0))
        e_m = _entry(f, vals[3] if is_edit else ""); e_m.pack(fill="x")
        _lbl(f, "Tipo publicación preferida").pack(anchor="w", pady=(8,0))
        cb_tp = _combo(f, _enums["cliente"]["tipo_publicacion_preferida"],
                       vals[4] if is_edit else ""); cb_tp.pack(fill="x")
        _lbl(f, "Tipo inmueble preferida").pack(anchor="w", pady=(8,0))
        cb_pp = _combo(f, _enums["cliente"]["tipo_inmueble_preferida"],
                       vals[5] if is_edit else ""); cb_pp.pack(fill="x")
        _lbl(f, "Ciudad preferida").pack(anchor="w", pady=(8,0))
        cb_ciu = _cities_combo(f, vals[6] if is_edit else None); cb_ciu.pack(fill="x")
        _lbl(f, "Presupuesto mínimo").pack(anchor="w", pady=(8,0))
        e_min = _entry(f, vals[7] if is_edit else ""); e_min.pack(fill="x")
        _lbl(f, "Presupuesto máximo").pack(anchor="w", pady=(8,0))
        e_max = _entry(f, vals[8] if is_edit else ""); e_max.pack(fill="x")

        def save():
            if not _str(e_n) or not _str(e_t) or not _str(e_m):
                messagebox.showerror("Error", "Nombre, teléfono y correo son obligatorios."); return
            d = {"nombre": _str(e_n), "telefono": _str(e_t), "correo": _str(e_m),
                 "tipo_publicacion_preferida": cb_tp.get() or None,
                 "tipo_inmueble_preferida":   cb_pp.get() or None,
                 "ciudad_preferida_id":        _sel_id(cb_ciu),
                 "presupuesto_min": _str(e_min) or 0,
                 "presupuesto_max": _str(e_max) or 0}
            ok, msg = update_cliente(int(vals[0]), d) if is_edit else insert_cliente(d)
            (messagebox.showinfo if ok else messagebox.showerror)("Resultado", msg)
            if ok: self._after_save("cliente", win)
        _save_btn(f, save).pack(fill="x", pady=(16, 0))

    # inmueble
    def _form_inmueble(self, vals=None):
        is_edit = vals is not None
        win, f = _form_window(self, "inmueble – " + ("editar" if is_edit else "nuevo"), height=740)
        _lbl(f, "Tipo publicación *").pack(anchor="w", pady=(8,0))
        cb_tpub = _combo(f, _enums["inmueble"]["tipo_publicacion"],
                         vals[1] if is_edit else ""); cb_tpub.pack(fill="x")
        _lbl(f, "Tipo inmueble *").pack(anchor="w", pady=(8,0))
        cb_tprop = _combo(f, _enums["inmueble"]["tipo_inmueble"],
                          vals[2] if is_edit else ""); cb_tprop.pack(fill="x")
        _lbl(f, "Dirección *").pack(anchor="w", pady=(8,0))
        e_dir = _entry(f, vals[3] if is_edit else ""); e_dir.pack(fill="x")
        _lbl(f, "Ciudad *").pack(anchor="w", pady=(8,0))
        cb_ciu = _cities_combo(f, vals[4] if is_edit else None); cb_ciu.pack(fill="x")
        _lbl(f, "Área m²").pack(anchor="w", pady=(8,0))
        e_area = _entry(f, vals[5] if is_edit else ""); e_area.pack(fill="x")
        _lbl(f, "Habitaciones").pack(anchor="w", pady=(8,0))
        e_hab = _entry(f, vals[6] if is_edit else "0"); e_hab.pack(fill="x")
        _lbl(f, "Baños").pack(anchor="w", pady=(8,0))
        e_ban = _entry(f, vals[7] if is_edit else "0"); e_ban.pack(fill="x")
        _lbl(f, "Año construcción").pack(anchor="w", pady=(8,0))
        e_anio = _entry(f, vals[8] if is_edit else ""); e_anio.pack(fill="x")
        _lbl(f, "Estado *").pack(anchor="w", pady=(8,0))
        cb_est = _combo(f, _enums["inmueble"]["estado"],
                        vals[9] if is_edit else "disponible"); cb_est.pack(fill="x")
        _lbl(f, "Fecha publicación (YYYY-MM-DD)").pack(anchor="w", pady=(8,0))
        e_fp = _entry(f, vals[10] if is_edit else ""); e_fp.pack(fill="x")
        _lbl(f, "Agente exclusivo (opcional)").pack(anchor="w", pady=(8,0))
        ags = fetch_reference_list("agente", label_cols=["nombre"])
        ag_vals = [""] + [f"{a[0]}: {a[1]}" for a in ags]
        cb_ag = _combo(f, ag_vals, ""); cb_ag.pack(fill="x")
        if is_edit and vals[11] not in (None, "", "None"):
            match = [v for v in ag_vals if v.startswith(f"{vals[11]}:")]
            if match: cb_ag.set(match[0])

        def save():
            if not _str(e_dir) or not cb_tpub.get() or not cb_tprop.get():
                messagebox.showerror("Error", "Tipo publicación, tipo inmueble y dirección son obligatorios."); return
            d = {"tipo_publicacion": cb_tpub.get(), "tipo_inmueble": cb_tprop.get(),
                 "direccion": _str(e_dir), "ciudad_id": _sel_id(cb_ciu),
                 "area_m2": _str(e_area) or None, "habitaciones": _str(e_hab) or 0,
                 "banos": _str(e_ban) or 0, "anio_construccion": _str(e_anio) or None,
                 "estado": cb_est.get() or "disponible", "fecha_publicacion": _str(e_fp) or None,
                 "agente_exclusivo_id": _sel_id(cb_ag)}
            ok, msg = update_inmueble(int(vals[0]), d) if is_edit else insert_inmueble(d)
            (messagebox.showinfo if ok else messagebox.showerror)("Resultado", msg)
            if ok: self._after_save("inmueble", win)
        _save_btn(f, save).pack(fill="x", pady=(16, 0))

    # Precio inmueble
    def _form_precio(self, vals=None):
        is_edit = vals is not None
        win, f = _form_window(self, "Precio inmueble – " + ("editar" if is_edit else "nuevo"), height=420)
        _lbl(f, "inmueble *").pack(anchor="w", pady=(8,0))
        props = fetch_reference_list("inmueble", label_cols=["direccion"])
        p_vals = [f"{p[0]}: {p[1]}" for p in props]
        cb_p = _combo(f, p_vals, ""); cb_p.pack(fill="x")
        if is_edit and vals[1] not in (None,"","None"):
            match = [v for v in p_vals if v.startswith(f"{vals[1]}:")]
            if match: cb_p.set(match[0])
        _lbl(f, "Precio *").pack(anchor="w", pady=(8,0))
        e_pr = _entry(f, vals[2] if is_edit else ""); e_pr.pack(fill="x")
        _lbl(f, "Desde (YYYY-MM-DD) *").pack(anchor="w", pady=(8,0))
        e_de = _entry(f, vals[3] if is_edit else ""); e_de.pack(fill="x")
        _lbl(f, "Hasta (YYYY-MM-DD, vacío = vigente)").pack(anchor="w", pady=(8,0))
        e_ha = _entry(f, vals[4] if is_edit else ""); e_ha.pack(fill="x")

        def save():
            d = {"inmueble_id": _sel_id(cb_p), "precio": _str(e_pr),
                 "desde": _str(e_de) or None, "hasta": _str(e_ha) or None}
            ok, msg = update_precio(int(vals[0]), d) if is_edit else insert_precio(d)
            (messagebox.showinfo if ok else messagebox.showerror)("Resultado", msg)
            if ok: self._after_save("precio", win)
        _save_btn(f, save).pack(fill="x", pady=(16, 0))

    # Visita
    def _form_visita(self, vals=None):
        is_edit = vals is not None
        win, f = _form_window(self, "Visita – " + ("editar" if is_edit else "nueva"), height=620)
        _lbl(f, "inmueble *").pack(anchor="w", pady=(8,0))
        props = fetch_reference_list("inmueble", label_cols=["direccion"])
        p_vals = [f"{p[0]}: {p[1]}" for p in props]
        cb_p = _combo(f, p_vals, ""); cb_p.pack(fill="x")
        _lbl(f, "Cliente *").pack(anchor="w", pady=(8,0))
        clis = fetch_reference_list("cliente", label_cols=["nombre"])
        c_vals = [f"{c[0]}: {c[1]}" for c in clis]
        cb_c = _combo(f, c_vals, ""); cb_c.pack(fill="x")
        _lbl(f, "Agente (opcional)").pack(anchor="w", pady=(8,0))
        ags = fetch_reference_list("agente", label_cols=["nombre"])
        a_vals = [""] + [f"{a[0]}: {a[1]}" for a in ags]
        cb_a = _combo(f, a_vals, ""); cb_a.pack(fill="x")
        _lbl(f, "Fecha (YYYY-MM-DD) *").pack(anchor="w", pady=(8,0))
        e_f = _entry(f, vals[4] if is_edit else ""); e_f.pack(fill="x")
        _lbl(f, "Hora (HH:MM) *").pack(anchor="w", pady=(8,0))
        e_h = _entry(f, vals[5] if is_edit else ""); e_h.pack(fill="x")
        _lbl(f, "Estado *").pack(anchor="w", pady=(8,0))
        cb_est = _combo(f, _enums["visita"]["estado"], vals[6] if is_edit else "programada"); cb_est.pack(fill="x")
        _lbl(f, "Notas").pack(anchor="w", pady=(8,0))
        e_no = _entry(f, vals[7] if is_edit else ""); e_no.pack(fill="x")
        if is_edit:
            for ref, cb in ((vals[1], cb_p), (vals[2], cb_c), (vals[3], cb_a)):
                if ref not in (None,"","None"):
                    match = [v for v in cb.cget("values") if v.startswith(f"{ref}:")]
                    if match: cb.set(match[0])

        def save():
            d = {"inmueble_id": _sel_id(cb_p), "cliente_id": _sel_id(cb_c),
                 "agente_id": _sel_id(cb_a), "fecha": _str(e_f) or None,
                 "hora": _str(e_h) or None, "estado": cb_est.get(), "notas": _str(e_no) or None}
            ok, msg = update_visita(int(vals[0]), d) if is_edit else insert_visita(d)
            (messagebox.showinfo if ok else messagebox.showerror)("Resultado", msg)
            if ok: self._after_save("visita", win)
        _save_btn(f, save).pack(fill="x", pady=(16, 0))

    # Oferta
    def _form_oferta(self, vals=None):
        is_edit = vals is not None
        win, f = _form_window(self, "Oferta – " + ("editar" if is_edit else "nueva"), height=560)
        _lbl(f, "inmueble *").pack(anchor="w", pady=(8,0))
        props = fetch_reference_list("inmueble", label_cols=["direccion"])
        p_vals = [f"{p[0]}: {p[1]}" for p in props]
        cb_p = _combo(f, p_vals, ""); cb_p.pack(fill="x")
        _lbl(f, "Cliente *").pack(anchor="w", pady=(8,0))
        clis = fetch_reference_list("cliente", label_cols=["nombre"])
        c_vals = [f"{c[0]}: {c[1]}" for c in clis]
        cb_c = _combo(f, c_vals, ""); cb_c.pack(fill="x")
        _lbl(f, "Fecha (YYYY-MM-DD)").pack(anchor="w", pady=(8,0))
        e_f = _entry(f, vals[3] if is_edit else ""); e_f.pack(fill="x")
        _lbl(f, "Monto *").pack(anchor="w", pady=(8,0))
        e_m = _entry(f, vals[4] if is_edit else ""); e_m.pack(fill="x")
        _lbl(f, "Estado *").pack(anchor="w", pady=(8,0))
        cb_est = _combo(f, _enums["oferta"]["estado"], vals[5] if is_edit else "pendiente"); cb_est.pack(fill="x")
        _lbl(f, "Comentarios").pack(anchor="w", pady=(8,0))
        e_co = _entry(f, vals[6] if is_edit else ""); e_co.pack(fill="x")
        if is_edit:
            for ref, cb in ((vals[1], cb_p), (vals[2], cb_c)):
                if ref not in (None,"","None"):
                    match = [v for v in cb.cget("values") if v.startswith(f"{ref}:")]
                    if match: cb.set(match[0])

        def save():
            d = {"inmueble_id": _sel_id(cb_p), "cliente_id": _sel_id(cb_c),
                 "fecha": _str(e_f) or None, "monto": _str(e_m),
                 "estado": cb_est.get(), "comentarios": _str(e_co) or None}
            ok, msg = update_oferta(int(vals[0]), d) if is_edit else insert_oferta(d)
            (messagebox.showinfo if ok else messagebox.showerror)("Resultado", msg)
            if ok: self._after_save("oferta", win)
        _save_btn(f, save).pack(fill="x", pady=(16, 0))

    # Transaccion
    def _form_transaccion(self, vals=None):
        is_edit = vals is not None
        win, f = _form_window(self, "Transacción – " + ("editar" if is_edit else "nueva"), height=640)
        _lbl(f, "inmueble *").pack(anchor="w", pady=(8,0))
        props = fetch_reference_list("inmueble", label_cols=["direccion"])
        p_vals = [f"{p[0]}: {p[1]}" for p in props]
        cb_p = _combo(f, p_vals, ""); cb_p.pack(fill="x")
        _lbl(f, "Cliente *").pack(anchor="w", pady=(8,0))
        clis = fetch_reference_list("cliente", label_cols=["nombre"])
        c_vals = [f"{c[0]}: {c[1]}" for c in clis]
        cb_c = _combo(f, c_vals, ""); cb_c.pack(fill="x")
        _lbl(f, "Oferta vinculada (opcional)").pack(anchor="w", pady=(8,0))
        oferts = fetch_reference_list("oferta", label_cols=["monto"])
        o_vals = [""] + [f"{o[0]}: {o[1]}" for o in oferts]
        cb_o = _combo(f, o_vals, ""); cb_o.pack(fill="x")
        _lbl(f, "Fecha cierre (YYYY-MM-DD) *").pack(anchor="w", pady=(8,0))
        e_fc = _entry(f, vals[3] if is_edit else ""); e_fc.pack(fill="x")
        _lbl(f, "Precio final *").pack(anchor="w", pady=(8,0))
        e_pf = _entry(f, vals[4] if is_edit else ""); e_pf.pack(fill="x")
        _lbl(f, "Tipo transacción *").pack(anchor="w", pady=(8,0))
        cb_tt = _combo(f, _enums["transaccion"]["tipo_transaccion"],
                       vals[5] if is_edit else ""); cb_tt.pack(fill="x")
        _lbl(f, "Estado transacción *").pack(anchor="w", pady=(8,0))
        cb_et = _combo(f, _enums["transaccion"]["estado_transaccion"],
                       vals[6] if is_edit else "cerrada"); cb_et.pack(fill="x")
        if is_edit:
            for ref, cb in ((vals[1], cb_p), (vals[2], cb_c), (vals[7], cb_o)):
                if ref not in (None,"","None"):
                    match = [v for v in cb.cget("values") if v.startswith(f"{ref}:")]
                    if match: cb.set(match[0])

        def save():
            d = {"inmueble_id": _sel_id(cb_p), "cliente_id": _sel_id(cb_c),
                 "oferta_id": _sel_id(cb_o), "fecha_cierre": _str(e_fc) or None,
                 "precio_final": _str(e_pf), "tipo_transaccion": cb_tt.get(),
                 "estado_transaccion": cb_et.get()}
            ok, msg = update_transaccion(int(vals[0]), d) if is_edit else insert_transaccion(d)
            (messagebox.showinfo if ok else messagebox.showerror)("Resultado", msg)
            if ok: self._after_save("transaccion", win)
        _save_btn(f, save).pack(fill="x", pady=(16, 0))

    # Transaccion agente
    def _form_ta(self, vals=None):
        is_edit = vals is not None
        win, f = _form_window(self, "Transacción-Agente – " + ("editar" if is_edit else "nuevo"), height=460)
        _lbl(f, "Transacción *").pack(anchor="w", pady=(8,0))
        trans = fetch_reference_list("transaccion", label_cols=["precio_final"])
        t_vals = [f"{t[0]}: {t[1]}" for t in trans]
        cb_t = _combo(f, t_vals, ""); cb_t.pack(fill="x")
        _lbl(f, "Agente *").pack(anchor="w", pady=(8,0))
        ags = fetch_reference_list("agente", label_cols=["nombre"])
        a_vals = [f"{a[0]}: {a[1]}" for a in ags]
        cb_a = _combo(f, a_vals, ""); cb_a.pack(fill="x")
        _lbl(f, "Comisión monto").pack(anchor="w", pady=(8,0))
        e_m = _entry(f, vals[2] if is_edit else ""); e_m.pack(fill="x")
        _lbl(f, "Comisión porcentaje *").pack(anchor="w", pady=(8,0))
        e_p = _entry(f, vals[3] if is_edit else ""); e_p.pack(fill="x")
        if is_edit:
            for ref, cb in ((vals[0], cb_t), (vals[1], cb_a)):
                if ref not in (None,"","None"):
                    match = [v for v in cb.cget("values") if v.startswith(f"{ref}:")]
                    if match: cb.set(match[0])

        def save():
            d = {"transaccion_id": _sel_id(cb_t), "agente_id": _sel_id(cb_a),
                 "comision_monto": _str(e_m) or None, "comision_porcentaje": _str(e_p) or 0}
            if is_edit:
                ok, msg = update_ta(int(vals[0]), int(vals[1]), d)
            else:
                ok, msg = insert_ta(d)
            (messagebox.showinfo if ok else messagebox.showerror)("Resultado", msg)
            if ok: self._after_save("transaccion_agente", win)
        _save_btn(f, save).pack(fill="x", pady=(16, 0))

    # ── Cola de eventos asíncronos ────────────────────────────
    def _poll_queue(self):
        try:
            while True:
                ev, data = self.ui_queue.get_nowait()
                if ev == "sql_done":
                    ok      = data.get("ok", False)
                    cols    = data.get("columns", [])
                    rows    = data.get("rows", [])
                    errors  = data.get("errors", [])
                    elapsed = data.get("elapsed", 0.0)
                    tr = self.sql_tree
                    tr.delete(*tr.get_children())
                    tr["columns"] = cols
                    tr["show"]    = "headings" if cols else ""
                    for c in cols:
                        tr.heading(c, text=c); tr.column(c, width=160, anchor="w")
                    for r in rows:
                        tr.insert("", "end", values=tuple("" if v is None else str(v) for v in r))
                    if errors:
                        self.sql_status.configure(text=f"Error ({elapsed:.2f}s)", text_color=DANGER)
                        messagebox.showwarning("SQL — error", errors[0])
                    else:
                        self.sql_status.configure(
                            text=f"OK — {len(rows)} filas · {elapsed:.2f}s",
                            text_color=SUCCESS)
        except Exception:
            pass
        finally:
            self.after(100, self._poll_queue)


# ─────────────────────────────────────────────────────────────
# Punto de entrada
# ─────────────────────────────────────────────────────────────

def main():
    if _DRIVER is None:
        root = tk.Tk(); root.withdraw()
        messagebox.showerror(
            "Driver no encontrado",
            "No hay driver MySQL instalado.\n"
            "Ejecuta: pip install mysqlclient  o  pip install PyMySQL"
        )
        return
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()