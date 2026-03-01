-- ================================================================================
-- DDL - Creacion de Base de Datos y Definición de Tablas
-- ================================================================================

-- ====================================================================
-- CREAR BASE DE DATOS: REALTYFLOW_DB
-- ====================================================================
CREATE DATABASE IF NOT EXISTS realtyflow_db;
USE realtyflow_db;

-- ====================================================================
-- 1) TABLA: AGENTE
-- ====================================================================
CREATE TABLE agente (
  id INT AUTO_INCREMENT PRIMARY KEY,
  nombre VARCHAR(120) NOT NULL,
  telefono VARCHAR(20) NOT NULL,
  correo VARCHAR(200) NOT NULL UNIQUE,
  porcentaje_comision DECIMAL(5,2) DEFAULT 3.00 CHECK (porcentaje_comision >= 0),
  fecha_ingreso DATE,
  estado BOOLEAN DEFAULT TRUE
);

-- ====================================================================
-- 2) TABLA: CLIENTE
-- ====================================================================
CREATE TABLE cliente (
  id INT AUTO_INCREMENT PRIMARY KEY,
  nombre VARCHAR(120) NOT NULL,
  telefono VARCHAR(20) NOT NULL,
  correo VARCHAR(200) NOT NULL UNIQUE,
  tipo_publicacion_preferida ENUM('venta','alquiler'),
  tipo_propiedad_preferida ENUM('casa','apartamento','terreno'),
  ubicacion_preferida VARCHAR(100),
  presupuesto_min DECIMAL(12,2) CHECK (presupuesto_min >= 0),
  presupuesto_max DECIMAL(12,2) CHECK (presupuesto_max >= 0)
);

-- ====================================================================
-- 3) TABLA: PROPIEDAD
-- ====================================================================
CREATE TABLE propiedad (
  id INT AUTO_INCREMENT PRIMARY KEY,
  tipo_publicacion ENUM('venta','alquiler') NOT NULL,
  tipo_propiedad ENUM('casa','apartamento','terreno') NOT NULL,
  direccion VARCHAR(200) NOT NULL UNIQUE,
  ciudad VARCHAR(100) NOT NULL,
  area_m2 DECIMAL(10,2) NOT NULL CHECK (area_m2 > 0),
  habitaciones INT NOT NULL CHECK (habitaciones >= 0),
  banos INT NOT NULL CHECK (banos >= 0),
  anio_construccion INT NOT NULL,
  estado ENUM('disponible','en_negociacion','vendida','alquilada','inactiva') NOT NULL DEFAULT 'disponible',
  fecha_publicacion DATE,
  agente_esclusivo_id INT NULL,
  FOREIGN KEY (agente_esclusivo_id) REFERENCES agente(id) ON DELETE SET NULL
);

-- ====================================================================
-- 4) TABLA: HISTORIAL DE PRECIOS
-- ====================================================================
CREATE TABLE precio_propiedad (
  id INT AUTO_INCREMENT PRIMARY KEY,
  propiedad_id INT NOT NULL,
  precio DECIMAL(14,2) NOT NULL CHECK (precio > 0),
  desde DATE DEFAULT CURRENT_DATE NOT NULL,
  hasta DATE NULL,
  UNIQUE(propiedad_id, desde),
  FOREIGN KEY (propiedad_id) REFERENCES propiedad(id) ON DELETE CASCADE
);

-- ====================================================================
-- 5) TABLA: VISITA
-- ====================================================================
CREATE TABLE visita (
    id INT AUTO_INCREMENT PRIMARY KEY,
    propiedad_id INT NOT NULL,
    cliente_id INT NOT NULL,
    agente_id INT NULL,
    fecha DATE NOT NULL,
    hora TIME NOT NULL,
    estado ENUM('programada','realizada','cancelada') DEFAULT 'programada' NOT NULL,
    notas TEXT,
    UNIQUE (propiedad_id, cliente_id, fecha, hora),
    FOREIGN KEY(propiedad_id) REFERENCES propiedad(id) ON DELETE CASCADE,
    FOREIGN KEY(cliente_id) REFERENCES cliente(id) ON DELETE CASCADE,
    FOREIGN KEY(agente_id) REFERENCES agente(id) ON DELETE SET NULL
);

-- ====================================================================
-- 6) TABLA: OFERTA
-- ====================================================================
CREATE TABLE oferta (
    id INT AUTO_INCREMENT PRIMARY KEY,
    propiedad_id INT NOT NULL,
    cliente_id INT NOT NULL,
    fecha DATE DEFAULT CURRENT_DATE NOT NULL,
    monto DECIMAL(14,2) NOT NULL CHECK (monto > 0),
    estado ENUM('pendiente','aceptada','rechazada') DEFAULT 'pendiente' NOT NULL,
    comentarios TEXT,
    UNIQUE (propiedad_id, cliente_id, monto),
    FOREIGN KEY(propiedad_id) REFERENCES propiedad(id) ON DELETE CASCADE,
    FOREIGN KEY(cliente_id) REFERENCES cliente(id) ON DELETE CASCADE
);

-- ====================================================================
-- 7) TABLA: TRANSACCION
-- ====================================================================
CREATE TABLE transaccion (
  id INT AUTO_INCREMENT PRIMARY KEY,
  propiedad_id INT NOT NULL,
  fecha_cierre DATE DEFAULT CURRENT_DATE NOT NULL,
  precio_final DECIMAL(14,2) NOT NULL CHECK (precio_final > 0),
  tipo_transaccion ENUM('venta','alquiler') NOT NULL,
  estado_transaccion ENUM('cerrada','cancelada') DEFAULT 'cerrada' NOT NULL,
  oferta_id INT NULL,
  FOREIGN KEY(propiedad_id) REFERENCES propiedad(id) ON DELETE CASCADE,
  FOREIGN KEY(oferta_id) REFERENCES oferta(id) ON DELETE SET NULL
);

-- ====================================================================
-- 8) TABLA: TRANSACCION_AGENTE (M:N)
-- ====================================================================
CREATE TABLE transaccion_agente (
  transaccion_id INT NOT NULL,
  agente_id INT NOT NULL,
  comision_monto DECIMAL(14,2) CHECK (comision_monto >= 0),
  comision_porcentaje DECIMAL(5,2) NOT NULL CHECK (comision_porcentaje >= 0 AND comision_porcentaje <= 100),
  PRIMARY KEY(transaccion_id, agente_id),
  FOREIGN KEY(transaccion_id) REFERENCES transaccion(id) ON DELETE CASCADE,
  FOREIGN KEY(agente_id) REFERENCES agente(id) ON DELETE CASCADE
);

-- ================================================================================
-- MDL - Datos de Ejemplo
-- ================================================================================

-- ====================================================================
-- 1) AGENTES
-- ====================================================================
INSERT INTO agente (nombre, telefono, correo, porcentaje_comision, fecha_ingreso, estado) VALUES
('juan perez','1234567890','juan.perez@email.com',3.0,'2022-01-10',TRUE),
('maria lopez','0987654321','maria.lopez@email.com',4.0,'2021-06-15',TRUE),
('carlos garcia','1122334455','carlos.garcia@email.com',3.5,'2023-03-20',TRUE);

-- ====================================================================
-- 2) CLIENTES
-- ====================================================================
INSERT INTO cliente (nombre, telefono, correo, tipo_publicacion_preferida, tipo_propiedad_preferida, ubicacion_preferida, presupuesto_min, presupuesto_max) VALUES
('ana martinez','5551112233','ana.martinez@email.com','venta','casa','bogota',200000000,500000000),
('luis ramirez','5552223344','luis.ramirez@email.com','alquiler','apartamento','medellin',1000000,3000000),
('carolina suarez','5553334455','carolina.suarez@email.com','venta','terreno','cali',150000000,400000000);

-- ====================================================================
-- 3) PROPIEDADES
-- ====================================================================
INSERT INTO propiedad (tipo_publicacion, tipo_propiedad, direccion, ciudad, area_m2, habitaciones, banos, anio_construccion, estado, fecha_publicacion, agente_esclusivo_id) VALUES
('venta','casa','calle 10 #45-67','bogota',120.5,3,2,2015,'disponible','2023-01-05',NULL),
('alquiler','apartamento','carrera 20 #30-50','medellin',85.0,2,1,2018,'disponible','2023-02-10',2),
('venta','terreno','vereda el rosal','cali',500.0,0,0,NULL,'disponible','2023-03-01',3);

-- ====================================================================
-- 4) HISTORIAL DE PRECIOS
-- ====================================================================
INSERT INTO precio_propiedad (propiedad_id, precio, desde) VALUES
(1,450000000,'2023-01-05'),
(2,1500000,'2023-02-10'),
(3,350000000,'2023-03-01');

-- ====================================================================
-- 5) VISITAS
-- ====================================================================
INSERT INTO visita (propiedad_id, cliente_id, agente_id, fecha, hora, estado, notas) VALUES
(1,1,1,'2023-01-15','10:00:00','realizada','cliente interesado en compra inmediata'),
(2,2,2,'2023-02-15','15:00:00','realizada','cliente requiere contrato de 12 meses'),
(3,3,3,'2023-03-10','09:30:00','programada','cliente quiere verificar linderos del terreno');

-- ====================================================================
-- 6) OFERTAS
-- ====================================================================
INSERT INTO oferta (propiedad_id, cliente_id, fecha, monto, estado, comentarios) VALUES
(1,1,'2023-01-20',440000000,'aceptada','oferta cercana al precio solicitado'),
(2,2,'2023-02-20',1400000,'pendiente','oferta inicial para apartamento'),
(3,3,'2023-03-15',360000000,'pendiente','oferta sobre terreno con planos incluidos');

-- ====================================================================
-- 7) TRANSACCIONES
-- ====================================================================
INSERT INTO transaccion (propiedad_id, fecha_cierre, precio_final, tipo_transaccion, estado_transaccion, oferta_id) VALUES
(1,'2023-01-25',440000000,'venta','cerrada',1);

-- ====================================================================
-- 8) TRANSACCION_AGENTE (M:N)
-- ====================================================================
INSERT INTO transaccion_agente (transaccion_id, agente_id, comision_monto, comision_porcentaje) VALUES
(1,1,13200000,3.0);