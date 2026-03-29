from __future__ import annotations

import json
import queue
import threading
import time
from typing import Optional, List, Tuple, Dict

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# ─── Conexión ─────────────────────────────────────────────────
DB_HOST     = "127.0.0.1"
DB_PORT     = 3306
DB_USER     = "root"
DB_PASSWORD = "root"
DB_NAME     = "realtyflow_db"

# ─── Paleta azul/blanco ───────────────────────────────────────
BLUE        = "#185EA4"   # azul principal
BLUE_DARK   = "#134d8a"   # hover / bordes activos
BLUE_LIGHT  = "#D6E8F7"   # fondos suaves
BLUE_MID    = "#E3ECF5"   # texto sobre fondo oscuro / badges

BG_MAIN     = "#F4F7FB"   # fondo de la app
BG_CARD     = "#FFFFFF"   # tarjetas / paneles
BG_SIDEBAR  = "#1A3A5C"   # sidebar oscuro para contraste
SIDEBAR_TXT = "#FFFFFF"
SIDEBAR_MUT = "#8FAEC8"

TEXT_PRIMARY = "#1A2A3A"
TEXT_MUTED   = "#4D6A86"
BORDER       = "#D0DFF0"

DANGER       = "#D93535"
SUCCESS      = "#1A8C4E"
WARNING      = "#C07A00"

# ─── ENUMs ───────────────────────────────────────────────────
DEFAULT_ENUMS: Dict[str, Dict[str, List[str]]] = {
    "cliente": {
        "tipo_publicacion_preferida": ["venta", "alquiler"],
        "tipo_inmueble_preferido":    ["casa", "apartamento", "terreno"],
    },
    "inmueble": {
        "tipo_publicacion": ["venta", "alquiler"],
        "tipo_inmueble":    ["casa", "apartamento", "terreno"],
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
    MySQLdb = _m; _DRIVER = "mysqlclient"
except ImportError:
    pass
if _DRIVER is None:
    try:
        import pymysql as _p  # type: ignore
        pymysql = _p; _DRIVER = "pymysql"
    except ImportError:
        pass


class DbError(Exception):
    pass


# ─────────────────────────────────────────────────────────────
# Capa de base de datos
# ─────────────────────────────────────────────────────────────

def create_connection(database: str = DB_NAME):
    if _DRIVER == "mysqlclient":
        p = {"host": DB_HOST, "user": DB_USER, "passwd": DB_PASSWORD,
             "port": DB_PORT, "charset": "utf8mb4", "use_unicode": True}
        if database: p["db"] = database
        return MySQLdb.connect(**p)  # type: ignore
    if _DRIVER == "pymysql":
        p = {"host": DB_HOST, "user": DB_USER, "password": DB_PASSWORD,
             "port": DB_PORT, "charset": "utf8mb4"}
        if database: p["database"] = database
        return pymysql.connect(**p)  # type: ignore
    raise DbError("Sin driver MySQL. Instala mysqlclient o PyMySQL.")


def execute_sql(sql_text: str) -> Tuple[bool, List[str], List[Tuple], List[str]]:
    stmts = [s.strip() for s in sql_text.split(";") if s.strip()]
    if not stmts:
        return False, [], [], ["Sin sentencias."]
    conn = create_connection(); cur = conn.cursor()
    cols: List[str] = []; rows: List[Tuple] = []; errors: List[str] = []; ok = True
    try:
        for s in stmts:
            try:
                cur.execute(s)
                if s.strip().lower().startswith("select"):
                    rows = list(cur.fetchall())
                    cols = [d[0] for d in (cur.description or [])]
                else:
                    conn.commit()
            except Exception as e:
                errors.append(f"{e} — {s[:100]}"); ok = False
    finally:
        cur.close(); conn.close()
    return ok, cols, rows, errors


def fetch_all(table: str) -> Tuple[List[str], List[Tuple]]:
    conn = create_connection(); cur = conn.cursor()
    cur.execute(f"SELECT * FROM `{table}`")
    rows = list(cur.fetchall())
    cols = [d[0] for d in (cur.description or [])]
    cur.close(); conn.close()
    return cols, rows


def fetch_kpis() -> Dict[str, int]:
    conn = create_connection(); cur = conn.cursor()
    kpis: Dict[str, int] = {}
    qs = {
        "inmuebles":         "SELECT COUNT(*) FROM inmueble",
        "inmuebles_disp":    "SELECT COUNT(*) FROM inmueble WHERE estado='disponible'",
        "clientes":          "SELECT COUNT(*) FROM cliente",
        "agentes":           "SELECT COUNT(*) FROM agente",
        "transacciones":     "SELECT COUNT(*) FROM transaccion WHERE estado_transaccion='cerrada'",
        "ofertas_pend":      "SELECT COUNT(*) FROM oferta WHERE estado='pendiente'",
    }
    for k, q in qs.items():
        try:
            cur.execute(q); r = cur.fetchone()
            kpis[k] = int(r[0]) if r else 0
        except Exception:
            kpis[k] = 0
    cur.close(); conn.close()
    return kpis


def fetch_ref(table: str, label_cols: List[str] = None) -> List[Tuple[int, str]]:
    """[(id, etiqueta)] para combobox FK."""
    cols, rows = fetch_all(table)
    idx = {c: i for i, c in enumerate(cols)}
    result = []
    for r in rows:
        rid = r[idx.get("id", 0)]
        if label_cols:
            label = " – ".join(str(r[idx[c]]) for c in label_cols if c in idx)
        else:
            label = str(r[idx.get("nombre", idx.get("direccion", 1))])
        result.append((rid, label))
    return result


# Cache para resolución de IDs → nombres (se recarga en refresh)
_cache: Dict[str, Dict[int, str]] = {}

def _load_cache():
    """Carga mapas id→nombre para las tablas de referencia usadas en vistas."""
    global _cache
    try:
        for t, lc in [("ciudad", ["nombre"]),
                      ("agente", ["nombre"]),
                      ("cliente", ["nombre"]),
                      ("inmueble", ["direccion"])]:
            items = fetch_ref(t, lc)
            _cache[t] = {rid: label for rid, label in items}
    except Exception:
        pass

def _resolve(table: str, raw_id) -> str:
    """Convierte un id numérico en su etiqueta legible o devuelve el raw si falla."""
    if raw_id in (None, "", "None"):
        return ""
    try:
        return _cache.get(table, {}).get(int(raw_id), str(raw_id))
    except Exception:
        return str(raw_id)


def run_crud(sql: str, params: tuple = ()) -> Tuple[bool, str]:
    try:
        conn = create_connection(); cur = conn.cursor()
        cur.execute(sql, params)
        conn.commit(); cur.close(); conn.close()
        return True, "OK"
    except Exception as e:
        return False, str(e)


# ─────────────────────────────────────────────────────────────
# CRUD — esquema final
# ─────────────────────────────────────────────────────────────

def insert_ciudad(d):
    return run_crud("INSERT INTO ciudad (nombre) VALUES (%s)", (d.get("nombre"),))

def update_ciudad(cid, d):
    return run_crud("UPDATE ciudad SET nombre=%s WHERE id=%s", (d.get("nombre"), cid))

def delete_ciudad(cid):
    return run_crud("DELETE FROM ciudad WHERE id=%s", (cid,))


def insert_agente(d):
    return run_crud(
        "INSERT INTO agente (nombre,telefono,correo,porcentaje_comision,fecha_ingreso,ciudad_id) "
        "VALUES (%s,%s,%s,%s,%s,%s)",
        (d["nombre"], d["telefono"], d["correo"],
         d.get("porcentaje_comision") or 3.0,
         d.get("fecha_ingreso") or None,
         d.get("ciudad_id") or None))

def update_agente(aid, d):
    return run_crud(
        "UPDATE agente SET nombre=%s,telefono=%s,correo=%s,"
        "porcentaje_comision=%s,fecha_ingreso=%s,ciudad_id=%s WHERE id=%s",
        (d["nombre"], d["telefono"], d["correo"],
         d.get("porcentaje_comision") or 3.0,
         d.get("fecha_ingreso") or None,
         d.get("ciudad_id") or None, aid))

def delete_agente(aid):
    return run_crud("DELETE FROM agente WHERE id=%s", (aid,))


def insert_cliente(d):
    return run_crud(
        "INSERT INTO cliente (nombre,telefono,correo,tipo_publicacion_preferida,"
        "tipo_inmueble_preferido,ciudad_id,presupuesto_min,presupuesto_max) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        (d["nombre"], d["telefono"], d["correo"],
         d.get("tipo_publicacion_preferida") or None,
         d.get("tipo_inmueble_preferido") or None,
         d.get("ciudad_id") or None,
         d.get("presupuesto_min") or 0,
         d.get("presupuesto_max") or 0))

def update_cliente(cid, d):
    return run_crud(
        "UPDATE cliente SET nombre=%s,telefono=%s,correo=%s,"
        "tipo_publicacion_preferida=%s,tipo_inmueble_preferido=%s,"
        "ciudad_id=%s,presupuesto_min=%s,presupuesto_max=%s WHERE id=%s",
        (d["nombre"], d["telefono"], d["correo"],
         d.get("tipo_publicacion_preferida") or None,
         d.get("tipo_inmueble_preferido") or None,
         d.get("ciudad_id") or None,
         d.get("presupuesto_min") or 0,
         d.get("presupuesto_max") or 0, cid))

def delete_cliente(cid):
    return run_crud("DELETE FROM cliente WHERE id=%s", (cid,))


def insert_inmueble(d):
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

def update_inmueble(iid, d):
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
         d.get("agente_exclusivo_id") or None, iid))

def delete_inmueble(iid):
    return run_crud("DELETE FROM inmueble WHERE id=%s", (iid,))


def insert_precio(d):
    return run_crud(
        "INSERT INTO precio (inmueble_id,precio,desde,hasta) VALUES (%s,%s,%s,%s)",
        (d.get("inmueble_id"), d.get("precio"), d.get("desde"), d.get("hasta") or None))

def update_precio(pid, d):
    return run_crud(
        "UPDATE precio SET inmueble_id=%s,precio=%s,desde=%s,hasta=%s WHERE id=%s",
        (d.get("inmueble_id"), d.get("precio"), d.get("desde"), d.get("hasta") or None, pid))

def delete_precio(pid):
    return run_crud("DELETE FROM precio WHERE id=%s", (pid,))


def insert_visita(d):
    return run_crud(
        "INSERT INTO visita (inmueble_id,cliente_id,agente_id,fecha,hora,estado,notas) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s)",
        (d.get("inmueble_id"), d.get("cliente_id"), d.get("agente_id") or None,
         d.get("fecha"), d.get("hora"), d.get("estado"), d.get("notas")))

def update_visita(vid, d):
    return run_crud(
        "UPDATE visita SET inmueble_id=%s,cliente_id=%s,agente_id=%s,"
        "fecha=%s,hora=%s,estado=%s,notas=%s WHERE id=%s",
        (d.get("inmueble_id"), d.get("cliente_id"), d.get("agente_id") or None,
         d.get("fecha"), d.get("hora"), d.get("estado"), d.get("notas"), vid))

def delete_visita(vid):
    return run_crud("DELETE FROM visita WHERE id=%s", (vid,))


def insert_oferta(d):
    return run_crud(
        "INSERT INTO oferta (inmueble_id,cliente_id,fecha,monto,estado,comentarios) "
        "VALUES (%s,%s,%s,%s,%s,%s)",
        (d.get("inmueble_id"), d.get("cliente_id"),
         d.get("fecha") or None, d.get("monto"),
         d.get("estado"), d.get("comentarios")))

def update_oferta(oid, d):
    return run_crud(
        "UPDATE oferta SET inmueble_id=%s,cliente_id=%s,fecha=%s,"
        "monto=%s,estado=%s,comentarios=%s WHERE id=%s",
        (d.get("inmueble_id"), d.get("cliente_id"),
         d.get("fecha") or None, d.get("monto"),
         d.get("estado"), d.get("comentarios"), oid))

def delete_oferta(oid):
    return run_crud("DELETE FROM oferta WHERE id=%s", (oid,))


def insert_transaccion(d):
    return run_crud(
        "INSERT INTO transaccion (inmueble_id,cliente_id,fecha_cierre,precio_final,"
        "tipo_transaccion,estado_transaccion,oferta_id) VALUES (%s,%s,%s,%s,%s,%s,%s)",
        (d.get("inmueble_id"), d.get("cliente_id"),
         d.get("fecha_cierre") or None, d.get("precio_final"),
         d.get("tipo_transaccion"), d.get("estado_transaccion"),
         d.get("oferta_id") or None))

def update_transaccion(tid, d):
    return run_crud(
        "UPDATE transaccion SET inmueble_id=%s,cliente_id=%s,fecha_cierre=%s,"
        "precio_final=%s,tipo_transaccion=%s,estado_transaccion=%s,oferta_id=%s WHERE id=%s",
        (d.get("inmueble_id"), d.get("cliente_id"),
         d.get("fecha_cierre") or None, d.get("precio_final"),
         d.get("tipo_transaccion"), d.get("estado_transaccion"),
         d.get("oferta_id") or None, tid))

def delete_transaccion(tid):
    return run_crud("DELETE FROM transaccion WHERE id=%s", (tid,))


def insert_ta(d):
    return run_crud(
        "INSERT INTO transaccion_agente (transaccion_id,agente_id,comision_monto,comision_porcentaje) "
        "VALUES (%s,%s,%s,%s)",
        (d.get("transaccion_id"), d.get("agente_id"),
         d.get("comision_monto") or None, d.get("comision_porcentaje") or 0))

def update_ta(tid, aid, d):
    return run_crud(
        "UPDATE transaccion_agente SET comision_monto=%s,comision_porcentaje=%s "
        "WHERE transaccion_id=%s AND agente_id=%s",
        (d.get("comision_monto") or None, d.get("comision_porcentaje") or 0, tid, aid))

def delete_ta(tid, aid):
    return run_crud(
        "DELETE FROM transaccion_agente WHERE transaccion_id=%s AND agente_id=%s",
        (tid, aid))


# ─────────────────────────────────────────────────────────────
# Worker SQL asíncrono
# ─────────────────────────────────────────────────────────────

class SqlWorker(threading.Thread):
    def __init__(self, sql: str, q: queue.Queue):
        super().__init__(daemon=True)
        self.sql = sql; self.q = q

    def run(self):
        t0 = time.time()
        try:
            ok, cols, rows, errors = execute_sql(self.sql)
            self.q.put(("sql_done", {"ok": ok, "columns": cols, "rows": rows,
                                      "errors": errors, "elapsed": time.time()-t0}))
        except Exception as e:
            self.q.put(("sql_done", {"ok": False, "columns": [], "rows": [],
                                      "errors": [str(e)], "elapsed": time.time()-t0}))


# ─────────────────────────────────────────────────────────────
# Utilidades de formulario
# ─────────────────────────────────────────────────────────────

def _sel_id(w) -> Optional[int]:
    v = w.get() if hasattr(w, "get") else ""
    if v:
        try: return int(str(v).split(":")[0].strip())
        except ValueError: pass
    return None

def _str(w, default="") -> str:
    return w.get().strip() if hasattr(w, "get") else default

def _lbl(p, text: str) -> ctk.CTkLabel:
    return ctk.CTkLabel(p, text=text, anchor="w",
                        text_color=TEXT_MUTED, font=("", 12))

def _entry(p, value="") -> ctk.CTkEntry:
    e = ctk.CTkEntry(p, height=36, fg_color=BG_CARD,
                     border_color=BORDER, text_color=TEXT_PRIMARY,
                     placeholder_text_color=TEXT_MUTED)
    e.insert(0, str(value) if value not in (None, "None", "") else "")
    return e

def _combo(p, values: list, value="") -> ctk.CTkComboBox:
    cb = ctk.CTkComboBox(p, values=values, height=36,
                         fg_color=BG_CARD, border_color=BORDER,
                         button_color=BLUE, dropdown_fg_color=BG_CARD,
                         text_color=TEXT_PRIMARY, dropdown_text_color=TEXT_PRIMARY,
                         hover=True)
    if value and str(value) not in ("None", ""):
        cb.set(str(value))
    return cb

def _cities_combo(p, selected_id=None) -> ctk.CTkComboBox:
    items = fetch_ref("ciudad")
    vals  = [f"{c[0]}: {c[1]}" for c in items]
    cb    = _combo(p, vals)
    if selected_id:
        m = [v for v in vals if v.startswith(f"{selected_id}:")]
        if m: cb.set(m[0])
    return cb

def _form_win(master, title: str, w=500, h=580
              ) -> Tuple[ctk.CTkToplevel, ctk.CTkScrollableFrame]:
    win = ctk.CTkToplevel(master)
    win.title(title); win.geometry(f"{w}x{h}")
    win.configure(fg_color=BG_MAIN); win.grab_set()
    hdr = ctk.CTkFrame(win, fg_color=BLUE, corner_radius=0, height=48)
    hdr.pack(fill="x")
    ctk.CTkLabel(hdr, text=title, font=("", 14, "bold"),
                 text_color="white").pack(side="left", padx=16, pady=10)
    fr = ctk.CTkScrollableFrame(win, fg_color=BG_MAIN,
                                scrollbar_button_color=BLUE_LIGHT,
                                scrollbar_button_hover_color=BLUE)
    fr.pack(fill="both", expand=True, padx=16, pady=12)
    return win, fr

def _save_btn(p, cmd) -> ctk.CTkButton:
    return ctk.CTkButton(p, text="  Guardar", height=42,
                         fg_color=BLUE, hover_color=BLUE_DARK,
                         text_color="white", font=("", 14, "bold"),
                         command=cmd)

def _field(parent, label: str, widget) -> None:
    """Coloca etiqueta + widget con espaciado consistente."""
    _lbl(parent, label).pack(anchor="w", pady=(10, 1))
    widget.pack(fill="x")


# ─────────────────────────────────────────────────────────────
# Vistas enriquecidas — filas con nombres en lugar de IDs
# ─────────────────────────────────────────────────────────────

# Columnas de display (cabeceras en MAYÚSCULAS)
DISPLAY_COLS: Dict[str, List[str]] = {
    "ciudad":             ["ID", "NOMBRE"],
    "agente":             ["ID", "NOMBRE", "TELÉFONO", "CORREO", "COMISIÓN %", "INGRESO", "CIUDAD"],
    "cliente":            ["ID", "NOMBRE", "TELÉFONO", "CORREO", "PUB. PREF.", "INMUEBLE PREF.", "CIUDAD", "PRESUP. MIN", "PRESUP. MAX"],
    "inmueble":           ["ID", "PUBLICACIÓN", "TIPO", "DIRECCIÓN", "CIUDAD", "ÁREA m²", "HAB.", "BAÑOS", "AÑO", "ESTADO", "PUBLICADO", "AGENTE"],
    "precio":             ["ID", "INMUEBLE", "PRECIO", "DESDE", "HASTA"],
    "visita":             ["ID", "INMUEBLE", "CLIENTE", "AGENTE", "FECHA", "HORA", "ESTADO", "NOTAS"],
    "oferta":             ["ID", "INMUEBLE", "CLIENTE", "FECHA", "MONTO", "ESTADO", "COMENTARIOS"],
    "transaccion":        ["ID", "INMUEBLE", "CLIENTE", "FECHA CIERRE", "PRECIO FINAL", "TIPO", "ESTADO", "OFERTA ID"],
    "transaccion_agente": ["TRANSACCIÓN", "AGENTE", "COMISIÓN MONTO", "COMISIÓN %"],
}

# Mapa de qué columna raw (por índice) se resuelve con qué tabla de cache
RESOLVE_MAP: Dict[str, Dict[int, str]] = {
    "agente":             {6: "ciudad"},
    "cliente":            {6: "ciudad"},
    "inmueble":           {4: "ciudad", 11: "agente"},
    "precio":             {1: "inmueble"},
    "visita":             {1: "inmueble", 2: "cliente", 3: "agente"},
    "oferta":             {1: "inmueble", 2: "cliente"},
    "transaccion":        {1: "inmueble", 2: "cliente"},
    "transaccion_agente": {0: "transaccion", 1: "agente"},
}

def _enrich_rows(table: str, raw_rows: List[Tuple]) -> List[tuple]:
    """Sustituye IDs foráneos por nombres legibles según RESOLVE_MAP."""
    rmap = RESOLVE_MAP.get(table, {})
    if not rmap:
        return raw_rows
    result = []
    for r in raw_rows:
        row = list(r)
        for idx, ref_table in rmap.items():
            if idx < len(row):
                row[idx] = _resolve(ref_table, row[idx])
        result.append(tuple(row))
    return result


# ─────────────────────────────────────────────────────────────
# Aplicación principal
# ─────────────────────────────────────────────────────────────

class App(ctk.CTk):

    TABLE_COLS_RAW: Dict[str, List[str]] = {
        "ciudad":             ["id","nombre"],
        "agente":             ["id","nombre","telefono","correo","porcentaje_comision","fecha_ingreso","ciudad_id"],
        "cliente":            ["id","nombre","telefono","correo","tipo_publicacion_preferida","tipo_inmueble_preferido","ciudad_id","presupuesto_min","presupuesto_max"],
        "inmueble":           ["id","tipo_publicacion","tipo_inmueble","direccion","ciudad_id","area_m2","habitaciones","banos","anio_construccion","estado","fecha_publicacion","agente_exclusivo_id"],
        "precio":             ["id","inmueble_id","precio","desde","hasta"],
        "visita":             ["id","inmueble_id","cliente_id","agente_id","fecha","hora","estado","notas"],
        "oferta":             ["id","inmueble_id","cliente_id","fecha","monto","estado","comentarios"],
        "transaccion":        ["id","inmueble_id","cliente_id","fecha_cierre","precio_final","tipo_transaccion","estado_transaccion","oferta_id"],
        "transaccion_agente": ["transaccion_id","agente_id","comision_monto","comision_porcentaje"],
    }

    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")
        self.title("RealtyCore — Gestor Administrativo")
        self.geometry("1300x800")
        self.configure(fg_color=BG_MAIN)
        self.ui_queue: queue.Queue = queue.Queue()
        self._trees: Dict[str, ttk.Treeview] = {}
        _load_cache()
        self._build_ui()
        self._poll_queue()

    # ── Estilos ttk ──────────────────────────────────────────
    def _apply_tree_style(self):
        s = ttk.Style()
        s.theme_use("clam")
        s.configure("RF.Treeview",
                    background=BG_CARD, fieldbackground=BG_CARD,
                    foreground=TEXT_PRIMARY, rowheight=30,
                    font=("", 12), borderwidth=0)
        s.configure("RF.Treeview.Heading",
                    background=BLUE, foreground="white",
                    font=("", 12, "bold"), relief="flat",
                    padding=(8, 6))
        s.map("RF.Treeview",
              background=[("selected", BLUE_LIGHT)],
              foreground=[("selected", BLUE_DARK)])
        s.configure("Mini.Treeview",
                    background=BG_CARD, fieldbackground=BG_CARD,
                    foreground=TEXT_PRIMARY, rowheight=26,
                    font=("", 11), borderwidth=0)
        s.configure("Mini.Treeview.Heading",
                    background=BLUE, foreground="white",
                    font=("", 11, "bold"), relief="flat")
        s.map("Mini.Treeview",
              background=[("selected", BLUE_LIGHT)],
              foreground=[("selected", BLUE_DARK)])

    # ── Layout principal ──────────────────────────────────────
    def _build_ui(self):
        self._apply_tree_style()

        # Sidebar
        sidebar = ctk.CTkFrame(self, width=210, fg_color=BG_SIDEBAR, corner_radius=0)
        sidebar.pack(side="left", fill="y"); sidebar.pack_propagate(False)

        # Logo
        logo_fr = ctk.CTkFrame(sidebar, fg_color="transparent")
        logo_fr.pack(fill="x", padx=16, pady=(28, 20))
        ctk.CTkLabel(logo_fr, text="RealtyCore",
                     font=("", 22, "bold"), text_color="white").pack(anchor="w")
        ctk.CTkLabel(logo_fr, text="Sistema de gestión",
                     font=("", 11), text_color=SIDEBAR_MUT).pack(anchor="w")

        # Separador
        ctk.CTkFrame(sidebar, height=1, fg_color=SIDEBAR_MUT).pack(fill="x", padx=16, pady=(0, 12))

        self._tab_view = ctk.CTkTabview(self, fg_color=BG_MAIN,
                                        segmented_button_fg_color=BG_CARD,
                                        segmented_button_selected_color=BLUE,
                                        segmented_button_selected_hover_color=BLUE_DARK,
                                        segmented_button_unselected_color=BG_CARD,
                                        segmented_button_unselected_hover_color=BLUE_LIGHT,
                                        text_color=TEXT_PRIMARY,
                                        text_color_disabled=TEXT_MUTED)
        self._tab_view.pack(side="left", fill="both", expand=True)

        tabs = [("Inicio", "Inicio"), ("Terminal SQL", "Terminal SQL")] + \
               [(t, t) for t in self.TABLE_COLS_RAW]
        self._tab_view.add("Inicio")
        self._tab_view.add("Terminal SQL")
        for t in self.TABLE_COLS_RAW:
            self._tab_view.add(t)

        # Sección Navegación sidebar
        ctk.CTkLabel(sidebar, text="NAVEGACIÓN", font=("", 10, "bold"),
                     text_color=SIDEBAR_MUT).pack(anchor="w", padx=18, pady=(0, 6))

        icons = {"Inicio":"⌂", "Terminal SQL":"⌨",
                 "ciudad":"🏙", "agente":"👤", "cliente":"👥",
                 "inmueble":"🏠", "precio":"💲", "visita":"📅",
                 "oferta":"📄", "transaccion":"💼", "transaccion_agente":"🤝"}

        for label, tab_name in tabs:
            icon = icons.get(label, "•")
            b = ctk.CTkButton(sidebar, text=f"  {icon}  {label}",
                              height=38, anchor="w",
                              fg_color="transparent",
                              hover_color="#2A4F72",
                              text_color=SIDEBAR_TXT,
                              font=("", 12),
                              command=lambda n=tab_name: self._tab_view.set(n))
            b.pack(fill="x", padx=8, pady=1)

        # Construir contenido
        self._build_dashboard(self._tab_view.tab("Inicio"))
        self._build_sql_tab(self._tab_view.tab("Terminal SQL"))
        for t in self.TABLE_COLS_RAW:
            self._build_table_tab(t, self._tab_view.tab(t))

    # ── Dashboard ─────────────────────────────────────────────
    def _build_dashboard(self, parent):
        parent.configure(fg_color=BG_MAIN)

        # Header
        hdr = ctk.CTkFrame(parent, fg_color="transparent")
        hdr.pack(fill="x", padx=24, pady=(20, 8))
        ctk.CTkLabel(hdr, text="Panel de control",
                     font=("", 22, "bold"), text_color=TEXT_PRIMARY).pack(side="left")
        self._dash_ts = ctk.CTkLabel(hdr, text="", text_color=TEXT_MUTED, font=("", 11))
        self._dash_ts.pack(side="right")
        ctk.CTkButton(hdr, text="↻  Actualizar", width=120, height=34,
                      fg_color=BLUE, hover_color=BLUE_DARK,
                      text_color="white", font=("", 12),
                      command=self.refresh_dashboard).pack(side="right", padx=8)

        # KPIs
        kpi_frame = ctk.CTkFrame(parent, fg_color="transparent")
        kpi_frame.pack(fill="x", padx=24, pady=4)

        kpi_defs = [
            ("inmuebles",      "Inmuebles",          "en portafolio total",      BLUE,    "inmueble"),
            ("inmuebles_disp", "Disponibles",         "listos para negociar",     SUCCESS, "inmueble"),
            ("clientes",       "Clientes",            "registrados",              "#7C4DFF","cliente"),
            ("agentes",        "Agentes",             "en todas las sedes",       "#00838F","agente"),
            ("transacciones",  "Cierres",             "transacciones cerradas",   WARNING, "transaccion"),
            ("ofertas_pend",   "Ofertas pendientes",  "sin respuesta",            DANGER,  "oferta"),
        ]

        self._kpi_lbl: Dict[str, ctk.CTkLabel] = {}

        for ci, (key, title, sub, color, nav) in enumerate(kpi_defs):
            card = ctk.CTkFrame(kpi_frame, fg_color=BG_CARD,
                                corner_radius=12,
                                border_width=1, border_color=color)
            card.grid(row=0, column=ci, padx=6, sticky="nsew")
            kpi_frame.grid_columnconfigure(ci, weight=1)

            inner = ctk.CTkFrame(card, fg_color="transparent")
            inner.pack(fill="x", padx=14, pady=(10, 4))

            ctk.CTkLabel(inner, text=title, font=("", 12, "bold"),
                         text_color=TEXT_MUTED).pack(anchor="w")

            val = ctk.CTkLabel(inner, text="—",
                               font=("", 34, "bold"), text_color=color)
            val.pack(anchor="w", pady=(2, 0))
            self._kpi_lbl[key] = val

            ctk.CTkLabel(inner, text=sub, font=("", 11),
                         text_color=TEXT_MUTED).pack(anchor="w", pady=(0, 4))

            ctk.CTkButton(card, text="Gestionar ", height=32,
                          fg_color="transparent",
                          hover_color=BLUE_LIGHT,
                          text_color=color,
                          font=("", 11, "bold"),
                          border_width=1, border_color=color,
                          command=lambda t=nav: self._tab_view.set(t)
                          ).pack(fill="x", padx=12, pady=(0, 12))

        # Tablas inferiores
        bot = ctk.CTkFrame(parent, fg_color="transparent")
        bot.pack(fill="both", expand=True, padx=24, pady=10)
        bot.grid_columnconfigure(0, weight=3)
        bot.grid_columnconfigure(1, weight=2)
        bot.grid_rowconfigure(0, weight=1)

        # Inmuebles disponibles
        lc = ctk.CTkFrame(bot, fg_color=BG_CARD, corner_radius=12,
                           border_width=1, border_color=BORDER)
        lc.grid(row=0, column=0, padx=(0, 8), sticky="nsew")
        hdr2 = ctk.CTkFrame(lc, fg_color=BLUE, corner_radius=8, height=38)
        hdr2.pack(fill="x")
        ctk.CTkLabel(hdr2, text="  Inmuebles disponibles",
                     font=("", 13, "bold"), text_color="white").pack(side="left", padx=8, pady=8)
        self._disp_tree = self._mini_tree(
            lc, ["ID", "TIPO", "CIUDAD", "ÁREA m²", "AÑO"])

        # Agentes por ciudad
        rc = ctk.CTkFrame(bot, fg_color=BG_CARD, corner_radius=12,
                           border_width=1, border_color=BORDER)
        rc.grid(row=0, column=1, padx=(8, 0), sticky="nsew")
        hdr3 = ctk.CTkFrame(rc, fg_color=BLUE, corner_radius=8, height=38)
        hdr3.pack(fill="x")
        ctk.CTkLabel(hdr3, text="  Agentes por ciudad",
                     font=("", 13, "bold"), text_color="white").pack(side="left", padx=8, pady=8)
        self._ag_tree = self._mini_tree(rc, ["CIUDAD", "AGENTES"])

        self.refresh_dashboard()

    def _mini_tree(self, parent, cols: List[str]) -> ttk.Treeview:
        tr = ttk.Treeview(parent, columns=cols, show="headings",
                          style="Mini.Treeview", height=9)
        for c in cols:
            tr.heading(c, text=c)
            w = 180 if c in ("CIUDAD", "TIPO", "DIRECCIÓN") else 80
            tr.column(c, width=w, anchor="w")
        tr.pack(fill="both", expand=True, padx=10, pady=10)
        return tr

    def refresh_dashboard(self):
        _load_cache()
        try:
            kpis = fetch_kpis()
            for k, lbl in self._kpi_lbl.items():
                lbl.configure(text=f"{kpis.get(k, 0):,}")

            # Inmuebles disponibles
            cols, rows = fetch_all("inmueble")
            ci = {c: i for i, c in enumerate(cols)}
            disp = [r for r in rows if str(r[ci["estado"]]) == "disponible"][-100:]
            self._disp_tree.delete(*self._disp_tree.get_children())
            for r in reversed(disp):
                self._disp_tree.insert("", "end", values=(
                    r[ci["id"]],
                    r[ci["tipo_inmueble"]],
                    _resolve("ciudad", r[ci["ciudad_id"]]),
                    r[ci["area_m2"]],
                    r[ci["anio_construccion"]],
                ))

            # Agentes por ciudad
            ok, _, rows_a, _ = execute_sql(
                "SELECT c.nombre, COUNT(a.id) FROM agente a "
                "JOIN ciudad c ON a.ciudad_id=c.id "
                "GROUP BY c.nombre ORDER BY 2 DESC")
            self._ag_tree.delete(*self._ag_tree.get_children())
            if ok:
                for r in rows_a:
                    self._ag_tree.insert("", "end", values=r)

            self._dash_ts.configure(
                text=f"Actualizado {time.strftime('%H:%M:%S')}", text_color=TEXT_MUTED)
        except Exception as e:
            self._dash_ts.configure(text=f"Error: {e}", text_color=DANGER)

    # ── Terminal SQL ──────────────────────────────────────────
    def _build_sql_tab(self, parent):
        parent.configure(fg_color=BG_MAIN)
        parent.grid_rowconfigure(1, weight=1)
        parent.grid_rowconfigure(3, weight=2)
        parent.grid_columnconfigure(0, weight=1)

        # Header
        hdr = ctk.CTkFrame(parent, fg_color=BLUE, corner_radius=0, height=46)
        hdr.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(hdr, text="  Terminal SQL",
                     font=("", 15, "bold"), text_color="white").pack(side="left", pady=10)

        # Editor
        editor_fr = ctk.CTkFrame(parent, fg_color=BG_CARD,
                                  corner_radius=8, border_width=1, border_color=BORDER)
        editor_fr.grid(row=1, column=0, sticky="nsew", padx=16, pady=(12, 0))
        editor_fr.grid_rowconfigure(0, weight=1)
        editor_fr.grid_columnconfigure(0, weight=1)

        self.sql_text = tk.Text(editor_fr, wrap="none",
                                bg=BG_CARD, fg=TEXT_PRIMARY,
                                insertbackground=BLUE,
                                font=("Courier New", 12),
                                relief="flat", padx=10, pady=8,
                                selectbackground=BLUE_LIGHT,
                                selectforeground=BLUE_DARK)
        self.sql_text.grid(row=0, column=0, sticky="nsew")
        sb_e = ttk.Scrollbar(editor_fr, orient="vertical", command=self.sql_text.yview)
        sb_e.grid(row=0, column=1, sticky="ns")
        self.sql_text.configure(yscrollcommand=sb_e.set)

        # Barra de botones
        bar = ctk.CTkFrame(parent, fg_color="transparent")
        bar.grid(row=2, column=0, sticky="ew", padx=16, pady=8)

        ctk.CTkButton(bar, text="📂  Abrir .sql", width=130, height=36,
                      fg_color=BG_CARD, hover_color=BLUE_LIGHT,
                      text_color=BLUE, border_width=1, border_color=BORDER,
                      font=("", 12),
                      command=self._open_sql).grid(row=0, column=0, padx=4)
        ctk.CTkButton(bar, text="▶  Ejecutar", width=130, height=36,
                      fg_color=BLUE, hover_color=BLUE_DARK,
                      text_color="white", font=("", 12, "bold"),
                      command=self._run_sql).grid(row=0, column=1, padx=4)
        ctk.CTkButton(bar, text="Cargar ENUMs (.json)", width=190, height=36,
                      fg_color=BG_CARD, hover_color=BLUE_LIGHT,
                      text_color=BLUE, border_width=1, border_color=BORDER,
                      font=("", 12),
                      command=self._load_enums).grid(row=0, column=2, padx=4)
        self.sql_status = ctk.CTkLabel(bar, text="Listo",
                                        text_color=TEXT_MUTED, font=("", 12))
        self.sql_status.grid(row=0, column=3, padx=14, sticky="w")

        # Resultado
        res_fr = ctk.CTkFrame(parent, fg_color=BG_CARD,
                               corner_radius=8, border_width=1, border_color=BORDER)
        res_fr.grid(row=3, column=0, sticky="nsew", padx=16, pady=(0, 12))
        res_fr.grid_rowconfigure(0, weight=1); res_fr.grid_columnconfigure(0, weight=1)

        self.sql_tree = ttk.Treeview(res_fr, style="Mini.Treeview")
        self.sql_tree.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        sb_r = ttk.Scrollbar(res_fr, orient="vertical", command=self.sql_tree.yview)
        sb_r.grid(row=0, column=1, sticky="ns")
        self.sql_tree.configure(yscrollcommand=sb_r.set)

    def _open_sql(self):
        p = filedialog.askopenfilename(filetypes=[("SQL","*.sql"),("Todos","*.*")])
        if p:
            with open(p, encoding="utf-8", errors="replace") as f:
                self.sql_text.delete("1.0","end")
                self.sql_text.insert("1.0", f.read())

    def _run_sql(self):
        sql = self.sql_text.get("1.0","end").strip()
        if not sql: return
        self.sql_status.configure(text="Ejecutando…", text_color=WARNING)
        SqlWorker(sql, self.ui_queue).start()

    def _load_enums(self):
        p = filedialog.askopenfilename(filetypes=[("JSON","*.json"),("Todos","*.*")])
        if p:
            with open(p, encoding="utf-8") as f:
                global _enums; _enums = json.load(f)
            messagebox.showinfo("ENUMs", "Valores actualizados correctamente.")

    # ── Tab por tabla ─────────────────────────────────────────
    def _build_table_tab(self, table: str, parent):
        parent.configure(fg_color=BG_MAIN)
        parent.grid_rowconfigure(1, weight=1)
        parent.grid_columnconfigure(0, weight=1)

        # Header con color
        hdr = ctk.CTkFrame(parent, fg_color=BLUE, corner_radius=0, height=46)
        hdr.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(hdr, text=f"  Gestión de {table.capitalize()}",
                     font=("", 15, "bold"), text_color="white").pack(side="left", pady=10)

        # Tabla
        disp_cols = DISPLAY_COLS.get(table, [c.upper() for c in self.TABLE_COLS_RAW[table]])
        fr = ctk.CTkFrame(parent, fg_color=BG_CARD,
                           corner_radius=8, border_width=1, border_color=BORDER)
        fr.grid(row=1, column=0, sticky="nsew", padx=16, pady=(10, 0))
        fr.grid_rowconfigure(0, weight=1); fr.grid_columnconfigure(0, weight=1)

        tree = ttk.Treeview(fr, columns=disp_cols, show="headings", style="RF.Treeview")
        for c in disp_cols:
            tree.heading(c, text=c)
            w = 180 if c in ("NOMBRE","DIRECCIÓN","CORREO","INMUEBLE","CLIENTE") else 110
            tree.column(c, width=w, anchor="w")
        tree.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)

        sb = ttk.Scrollbar(fr, orient="vertical", command=tree.yview)
        sb.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=sb.set)

        sb_h = ttk.Scrollbar(fr, orient="horizontal", command=tree.xview)
        sb_h.grid(row=1, column=0, sticky="ew")
        tree.configure(xscrollcommand=sb_h.set)

        self._trees[table] = tree

        # Botones
        btn_row = ctk.CTkFrame(parent, fg_color="transparent")
        btn_row.grid(row=2, column=0, sticky="ew", padx=16, pady=10)

        for txt, fn, fg, tc in [
            ("+ Nuevo",     lambda t=table: self._on_new(t),    BLUE,    "white"),
            ("✎ Editar",    lambda t=table: self._on_edit(t),   BG_CARD, BLUE),
            ("✕ Eliminar",  lambda t=table: self._on_delete(t), BG_CARD, DANGER),
            ("↻ Refrescar", lambda t=table: self._reload(t),    BG_CARD, TEXT_MUTED),
        ]:
            bw = 1 if fg == BG_CARD else 0
            ctk.CTkButton(btn_row, text=txt, height=38, width=130,
                          fg_color=fg, hover_color=BLUE_LIGHT if fg==BG_CARD else BLUE_DARK,
                          text_color=tc, border_width=bw, border_color=BORDER,
                          font=("", 12),
                          command=fn).pack(side="left", padx=5)

        self._reload(table)

    def _reload(self, table: str):
        _load_cache()
        tree = self._trees.get(table)
        if not tree: return
        try:
            _, rows = fetch_all(table)
            enriched = _enrich_rows(table, rows)
            tree.delete(*tree.get_children())
            for r in enriched:
                tree.insert("", "end",
                            values=tuple("" if v is None else str(v) for v in r))
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo cargar {table}:\n{e}")

    def _sel(self, table: str) -> Optional[tuple]:
        """Devuelve los valores RAW (con IDs) del registro seleccionado."""
        tree = self._trees.get(table)
        sel  = tree.selection() if tree else []
        if not sel: return None
        # Los valores del treeview son los enriquecidos, pero para editar
        # necesitamos los raw. Hacemos fetch por id.
        display_vals = tree.item(sel[0], "values")
        if not display_vals: return None
        # El primer campo siempre es ID (numérico) excepto transaccion_agente
        try:
            if table == "transaccion_agente":
                # No podemos resolver fácilmente — devolver display
                return display_vals
            raw_id = int(str(display_vals[0]))
            cols, rows = fetch_all(table)
            ci = {c: i for i, c in enumerate(cols)}
            for r in rows:
                if r[ci.get("id", 0)] == raw_id:
                    return r
        except Exception:
            pass
        return display_vals

    # ── CRUD handlers ─────────────────────────────────────────
    def _on_new(self, t):    self._open_form(t, None)
    def _on_edit(self, t):
        v = self._sel(t)
        if not v: messagebox.showinfo("Info","Selecciona un registro."); return
        self._open_form(t, v)
    def _on_delete(self, t):
        v = self._sel(t)
        if not v: messagebox.showinfo("Info","Selecciona un registro."); return
        if not messagebox.askyesno("Confirmar",f"¿Eliminar el registro seleccionado de {t}?"): return
        fn_map = {
            "ciudad": lambda: delete_ciudad(int(v[0])),
            "agente": lambda: delete_agente(int(v[0])),
            "cliente": lambda: delete_cliente(int(v[0])),
            "inmueble": lambda: delete_inmueble(int(v[0])),
            "precio": lambda: delete_precio(int(v[0])),
            "visita": lambda: delete_visita(int(v[0])),
            "oferta": lambda: delete_oferta(int(v[0])),
            "transaccion": lambda: delete_transaccion(int(v[0])),
            "transaccion_agente": lambda: delete_ta(int(v[0]), int(v[1])),
        }
        fn = fn_map.get(t)
        if fn:
            ok, msg = fn()
            (messagebox.showinfo if ok else messagebox.showerror)("Resultado", msg)
            if ok: self._reload(t)

    def _after_save(self, t, win):
        self._reload(t); self.refresh_dashboard(); win.destroy()

    def _open_form(self, t, vals):
        {
            "ciudad":             self._f_ciudad,
            "agente":             self._f_agente,
            "cliente":            self._f_cliente,
            "inmueble":           self._f_inmueble,
            "precio":             self._f_precio,
            "visita":             self._f_visita,
            "oferta":             self._f_oferta,
            "transaccion":        self._f_transaccion,
            "transaccion_agente": self._f_ta,
        }.get(t, lambda v: messagebox.showinfo("Info",f"Sin formulario para {t}."))(vals)

    # ── Formularios ───────────────────────────────────────────
    def _f_ciudad(self, v=None):
        ie = v is not None
        win, f = _form_win(self, ("Editar" if ie else "Nueva") + " ciudad", h=280)
        _field(f, "Nombre  *", e_n := _entry(f, v[1] if ie else ""))
        def save():
            if not _str(e_n): messagebox.showerror("Error","Nombre obligatorio."); return
            ok, msg = (update_ciudad(int(v[0]),{"nombre":_str(e_n)}) if ie
                       else insert_ciudad({"nombre":_str(e_n)}))
            (messagebox.showinfo if ok else messagebox.showerror)("Resultado",msg)
            if ok: self._after_save("ciudad", win)
        _save_btn(f, save).pack(fill="x", pady=(16,0))

    def _f_agente(self, v=None):
        ie = v is not None
        win, f = _form_win(self, ("Editar" if ie else "Nuevo") + " agente", h=520)
        _field(f, "Nombre  *",        e_n  := _entry(f, v[1] if ie else ""))
        _field(f, "Teléfono  *",      e_t  := _entry(f, v[2] if ie else ""))
        _field(f, "Correo  *",        e_m  := _entry(f, v[3] if ie else ""))
        _field(f, "Comisión %",       e_p  := _entry(f, v[4] if ie else "3.0"))
        _field(f, "Fecha ingreso",    e_fi := _entry(f, v[5] if ie else ""))
        _field(f, "Ciudad  *",        cb_c := _cities_combo(f, v[6] if ie else None))
        def save():
            if not _str(e_n) or not _str(e_t) or not _str(e_m):
                messagebox.showerror("Error","Nombre, teléfono y correo son obligatorios."); return
            d = {"nombre":_str(e_n),"telefono":_str(e_t),"correo":_str(e_m),
                 "porcentaje_comision":_str(e_p) or 3.0,
                 "fecha_ingreso":_str(e_fi) or None,"ciudad_id":_sel_id(cb_c)}
            ok, msg = update_agente(int(v[0]),d) if ie else insert_agente(d)
            (messagebox.showinfo if ok else messagebox.showerror)("Resultado",msg)
            if ok: self._after_save("agente", win)
        _save_btn(f, save).pack(fill="x", pady=(16,0))

    def _f_cliente(self, v=None):
        ie = v is not None
        win, f = _form_win(self, ("Editar" if ie else "Nuevo") + " cliente", h=660)
        _field(f, "Nombre  *",               e_n   := _entry(f, v[1] if ie else ""))
        _field(f, "Teléfono  *",             e_t   := _entry(f, v[2] if ie else ""))
        _field(f, "Correo  *",               e_m   := _entry(f, v[3] if ie else ""))
        _field(f, "Tipo publicación pref.",  cb_tp := _combo(f, _enums["cliente"]["tipo_publicacion_preferida"], v[4] if ie else ""))
        _field(f, "Tipo inmueble preferido", cb_ti := _combo(f, _enums["cliente"]["tipo_inmueble_preferido"], v[5] if ie else ""))
        _field(f, "Ciudad",                  cb_ci := _cities_combo(f, v[6] if ie else None))
        _field(f, "Presupuesto mínimo",      e_mn  := _entry(f, v[7] if ie else ""))
        _field(f, "Presupuesto máximo",      e_mx  := _entry(f, v[8] if ie else ""))
        def save():
            if not _str(e_n) or not _str(e_t) or not _str(e_m):
                messagebox.showerror("Error","Nombre, teléfono y correo son obligatorios."); return
            d = {"nombre":_str(e_n),"telefono":_str(e_t),"correo":_str(e_m),
                 "tipo_publicacion_preferida":cb_tp.get() or None,
                 "tipo_inmueble_preferido":cb_ti.get() or None,
                 "ciudad_id":_sel_id(cb_ci),
                 "presupuesto_min":_str(e_mn) or 0,"presupuesto_max":_str(e_mx) or 0}
            ok, msg = update_cliente(int(v[0]),d) if ie else insert_cliente(d)
            (messagebox.showinfo if ok else messagebox.showerror)("Resultado",msg)
            if ok: self._after_save("cliente", win)
        _save_btn(f, save).pack(fill="x", pady=(16,0))

    def _f_inmueble(self, v=None):
        ie = v is not None
        win, f = _form_win(self, ("Editar" if ie else "Nuevo") + " inmueble", h=740)
        _field(f, "Tipo publicación  *",  cb_tp  := _combo(f, _enums["inmueble"]["tipo_publicacion"], v[1] if ie else ""))
        _field(f, "Tipo inmueble  *",     cb_ti  := _combo(f, _enums["inmueble"]["tipo_inmueble"], v[2] if ie else ""))
        _field(f, "Dirección  *",         e_dir  := _entry(f, v[3] if ie else ""))
        _field(f, "Ciudad  *",            cb_ci  := _cities_combo(f, v[4] if ie else None))
        _field(f, "Área m²",              e_ar   := _entry(f, v[5] if ie else ""))
        _field(f, "Habitaciones",         e_hab  := _entry(f, v[6] if ie else "0"))
        _field(f, "Baños",                e_ban  := _entry(f, v[7] if ie else "0"))
        _field(f, "Año construcción",     e_an   := _entry(f, v[8] if ie else ""))
        _field(f, "Estado  *",            cb_est := _combo(f, _enums["inmueble"]["estado"], v[9] if ie else "disponible"))
        _field(f, "Fecha publicación",    e_fp   := _entry(f, v[10] if ie else ""))
        ags = fetch_ref("agente", ["nombre"])
        ag_vals = [""] + [f"{a[0]}: {a[1]}" for a in ags]
        _field(f, "Agente exclusivo (opcional)", cb_ag := _combo(f, ag_vals, ""))
        if ie and v[11] not in (None,"","None"):
            m = [x for x in ag_vals if x.startswith(f"{v[11]}:")]
            if m: cb_ag.set(m[0])
        def save():
            if not _str(e_dir) or not cb_tp.get() or not cb_ti.get():
                messagebox.showerror("Error","Tipo publicación, tipo y dirección son obligatorios."); return
            d = {"tipo_publicacion":cb_tp.get(),"tipo_inmueble":cb_ti.get(),
                 "direccion":_str(e_dir),"ciudad_id":_sel_id(cb_ci),
                 "area_m2":_str(e_ar) or None,"habitaciones":_str(e_hab) or 0,
                 "banos":_str(e_ban) or 0,"anio_construccion":_str(e_an) or None,
                 "estado":cb_est.get() or "disponible","fecha_publicacion":_str(e_fp) or None,
                 "agente_exclusivo_id":_sel_id(cb_ag)}
            ok, msg = update_inmueble(int(v[0]),d) if ie else insert_inmueble(d)
            (messagebox.showinfo if ok else messagebox.showerror)("Resultado",msg)
            if ok: self._after_save("inmueble", win)
        _save_btn(f, save).pack(fill="x", pady=(16,0))

    def _f_precio(self, v=None):
        ie = v is not None
        win, f = _form_win(self, ("Editar" if ie else "Nuevo") + " precio", h=420)
        inms = fetch_ref("inmueble", ["direccion"])
        i_vals = [f"{i[0]}: {i[1]}" for i in inms]
        _field(f, "Inmueble  *", cb_i := _combo(f, i_vals, ""))
        if ie and v[1] not in (None,"","None"):
            m = [x for x in i_vals if x.startswith(f"{v[1]}:")]
            if m: cb_i.set(m[0])
        _field(f, "Precio  *",        e_pr := _entry(f, v[2] if ie else ""))
        _field(f, "Desde (YYYY-MM-DD)  *", e_de := _entry(f, v[3] if ie else ""))
        _field(f, "Hasta (vacío = vigente)", e_ha := _entry(f, v[4] if ie else ""))
        def save():
            d = {"inmueble_id":_sel_id(cb_i),"precio":_str(e_pr),
                 "desde":_str(e_de) or None,"hasta":_str(e_ha) or None}
            ok, msg = update_precio(int(v[0]),d) if ie else insert_precio(d)
            (messagebox.showinfo if ok else messagebox.showerror)("Resultado",msg)
            if ok: self._after_save("precio", win)
        _save_btn(f, save).pack(fill="x", pady=(16,0))

    def _f_visita(self, v=None):
        ie = v is not None
        win, f = _form_win(self, ("Editar" if ie else "Nueva") + " visita", h=620)
        inms = fetch_ref("inmueble", ["direccion"]); i_vals = [f"{i[0]}: {i[1]}" for i in inms]
        clis = fetch_ref("cliente", ["nombre"]);     c_vals = [f"{c[0]}: {c[1]}" for c in clis]
        ags  = fetch_ref("agente", ["nombre"]);      a_vals = [""] + [f"{a[0]}: {a[1]}" for a in ags]
        _field(f, "Inmueble  *",    cb_i := _combo(f, i_vals, ""))
        _field(f, "Cliente  *",     cb_c := _combo(f, c_vals, ""))
        _field(f, "Agente (opcional)", cb_a := _combo(f, a_vals, ""))
        _field(f, "Fecha  *",       e_fe := _entry(f, v[4] if ie else ""))
        _field(f, "Hora  *",        e_ho := _entry(f, v[5] if ie else ""))
        _field(f, "Estado  *",      cb_est := _combo(f, _enums["visita"]["estado"], v[6] if ie else "programada"))
        _field(f, "Notas",          e_no := _entry(f, v[7] if ie else ""))
        if ie:
            for ref, cb in ((v[1],cb_i),(v[2],cb_c),(v[3],cb_a)):
                if ref not in (None,"","None"):
                    m = [x for x in cb.cget("values") if x.startswith(f"{ref}:")]
                    if m: cb.set(m[0])
        def save():
            d = {"inmueble_id":_sel_id(cb_i),"cliente_id":_sel_id(cb_c),
                 "agente_id":_sel_id(cb_a),"fecha":_str(e_fe) or None,
                 "hora":_str(e_ho) or None,"estado":cb_est.get(),"notas":_str(e_no) or None}
            ok, msg = update_visita(int(v[0]),d) if ie else insert_visita(d)
            (messagebox.showinfo if ok else messagebox.showerror)("Resultado",msg)
            if ok: self._after_save("visita", win)
        _save_btn(f, save).pack(fill="x", pady=(16,0))

    def _f_oferta(self, v=None):
        ie = v is not None
        win, f = _form_win(self, ("Editar" if ie else "Nueva") + " oferta", h=560)
        inms = fetch_ref("inmueble", ["direccion"]); i_vals = [f"{i[0]}: {i[1]}" for i in inms]
        clis = fetch_ref("cliente", ["nombre"]);     c_vals = [f"{c[0]}: {c[1]}" for c in clis]
        _field(f, "Inmueble  *",   cb_i := _combo(f, i_vals, ""))
        _field(f, "Cliente  *",    cb_c := _combo(f, c_vals, ""))
        _field(f, "Fecha",         e_fe := _entry(f, v[3] if ie else ""))
        _field(f, "Monto  *",      e_mo := _entry(f, v[4] if ie else ""))
        _field(f, "Estado  *",     cb_est := _combo(f, _enums["oferta"]["estado"], v[5] if ie else "pendiente"))
        _field(f, "Comentarios",   e_co := _entry(f, v[6] if ie else ""))
        if ie:
            for ref, cb in ((v[1],cb_i),(v[2],cb_c)):
                if ref not in (None,"","None"):
                    m = [x for x in cb.cget("values") if x.startswith(f"{ref}:")]
                    if m: cb.set(m[0])
        def save():
            d = {"inmueble_id":_sel_id(cb_i),"cliente_id":_sel_id(cb_c),
                 "fecha":_str(e_fe) or None,"monto":_str(e_mo),
                 "estado":cb_est.get(),"comentarios":_str(e_co) or None}
            ok, msg = update_oferta(int(v[0]),d) if ie else insert_oferta(d)
            (messagebox.showinfo if ok else messagebox.showerror)("Resultado",msg)
            if ok: self._after_save("oferta", win)
        _save_btn(f, save).pack(fill="x", pady=(16,0))

    def _f_transaccion(self, v=None):
        ie = v is not None
        win, f = _form_win(self, ("Editar" if ie else "Nueva") + " transacción", h=660)
        inms  = fetch_ref("inmueble", ["direccion"]);  i_vals = [f"{i[0]}: {i[1]}" for i in inms]
        clis  = fetch_ref("cliente", ["nombre"]);      c_vals = [f"{c[0]}: {c[1]}" for c in clis]
        ofts  = fetch_ref("oferta", ["monto"]);        o_vals = [""] + [f"{o[0]}: {o[1]}" for o in ofts]
        _field(f, "Inmueble  *",          cb_i  := _combo(f, i_vals, ""))
        _field(f, "Cliente  *",           cb_c  := _combo(f, c_vals, ""))
        _field(f, "Oferta (opcional)",    cb_o  := _combo(f, o_vals, ""))
        _field(f, "Fecha cierre  *",      e_fc  := _entry(f, v[3] if ie else ""))
        _field(f, "Precio final  *",      e_pf  := _entry(f, v[4] if ie else ""))
        _field(f, "Tipo transacción  *",  cb_tt := _combo(f, _enums["transaccion"]["tipo_transaccion"], v[5] if ie else ""))
        _field(f, "Estado transacción  *",cb_et := _combo(f, _enums["transaccion"]["estado_transaccion"], v[6] if ie else "cerrada"))
        if ie:
            for ref, cb in ((v[1],cb_i),(v[2],cb_c),(v[7],cb_o)):
                if ref not in (None,"","None"):
                    m = [x for x in cb.cget("values") if x.startswith(f"{ref}:")]
                    if m: cb.set(m[0])
        def save():
            d = {"inmueble_id":_sel_id(cb_i),"cliente_id":_sel_id(cb_c),
                 "oferta_id":_sel_id(cb_o),"fecha_cierre":_str(e_fc) or None,
                 "precio_final":_str(e_pf),"tipo_transaccion":cb_tt.get(),
                 "estado_transaccion":cb_et.get()}
            ok, msg = update_transaccion(int(v[0]),d) if ie else insert_transaccion(d)
            (messagebox.showinfo if ok else messagebox.showerror)("Resultado",msg)
            if ok: self._after_save("transaccion", win)
        _save_btn(f, save).pack(fill="x", pady=(16,0))

    def _f_ta(self, v=None):
        ie = v is not None
        win, f = _form_win(self, ("Editar" if ie else "Nueva") + " comisión", h=460)
        trans = fetch_ref("transaccion", ["precio_final"]); t_vals = [f"{t[0]}: {t[1]}" for t in trans]
        ags   = fetch_ref("agente", ["nombre"]);             a_vals = [f"{a[0]}: {a[1]}" for a in ags]
        _field(f, "Transacción  *",    cb_t := _combo(f, t_vals, ""))
        _field(f, "Agente  *",         cb_a := _combo(f, a_vals, ""))
        _field(f, "Comisión monto",    e_mo := _entry(f, v[2] if ie else ""))
        _field(f, "Comisión %  *",     e_pc := _entry(f, v[3] if ie else ""))
        if ie:
            for ref, cb in ((v[0],cb_t),(v[1],cb_a)):
                if ref not in (None,"","None"):
                    m = [x for x in cb.cget("values") if x.startswith(f"{ref}:")]
                    if m: cb.set(m[0])
        def save():
            d = {"transaccion_id":_sel_id(cb_t),"agente_id":_sel_id(cb_a),
                 "comision_monto":_str(e_mo) or None,"comision_porcentaje":_str(e_pc) or 0}
            ok, msg = (update_ta(int(v[0]),int(v[1]),d) if ie else insert_ta(d))
            (messagebox.showinfo if ok else messagebox.showerror)("Resultado",msg)
            if ok: self._after_save("transaccion_agente", win)
        _save_btn(f, save).pack(fill="x", pady=(16,0))

    # ── Cola asíncrona ────────────────────────────────────────
    def _poll_queue(self):
        try:
            while True:
                ev, data = self.ui_queue.get_nowait()
                if ev == "sql_done":
                    ok = data["ok"]; cols = data["columns"]
                    rows = data["rows"]; errors = data["errors"]
                    elapsed = data["elapsed"]
                    tr = self.sql_tree
                    tr.delete(*tr.get_children())
                    tr["columns"] = cols
                    tr["show"]    = "headings" if cols else ""
                    for c in cols:
                        tr.heading(c, text=c.upper())
                        tr.column(c, width=160, anchor="w")
                    for r in rows:
                        tr.insert("","end", values=tuple("" if x is None else str(x) for x in r))
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
# Entrada
# ─────────────────────────────────────────────────────────────

def main():
    if _DRIVER is None:
        root = tk.Tk(); root.withdraw()
        messagebox.showerror("Sin driver",
            "No hay driver MySQL instalado.\n"
            "Ejecuta: pip install mysqlclient  o  pip install PyMySQL")
        return
    App().mainloop()

if __name__ == "__main__":
    main()