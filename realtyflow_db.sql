-- ================================================================================
-- DDL - Creacion de Base de Datos y Definición de Tablas
-- ================================================================================

-- ====================================================================
-- CREATE DATABASE
-- ====================================================================
CREATE DATABASE IF NOT EXISTS realtyflow_db;
USE realtyflow_db;

-- ====================================================================
-- 1) TABLA: AGENTE
-- ====================================================================
CREATE TABLE agente (
  id INT AUTO_INCREMENT PRIMARY KEY,
  nombre VARCHAR(120) NOT NULL,
  telefono VARCHAR(20),
  correo VARCHAR(200) NOT NULL UNIQUE,
  porcentaje_comision DECIMAL(5,2) DEFAULT 3.00 CHECK (porcentaje_comision >= 0),
  fecha_ingreso DATE,
  activo BOOLEAN DEFAULT TRUE
);

-- ====================================================================
-- 2) TABLA: CLIENTE
-- ====================================================================
CREATE TABLE cliente (
  id INT AUTO_INCREMENT PRIMARY KEY,
  nombre VARCHAR(120) NOT NULL,
  telefono VARCHAR(20),
  correo VARCHAR(200) NOT NULL UNIQUE,
  tipo_cliente ENUM('comprador','arrendatario') NOT NULL,
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
  direccion VARCHAR(200) UNIQUE NOT NULL,
  ciudad VARCHAR(100) NOT NULL,
  area_m2 DECIMAL(10,2) CHECK (area_m2 > 0),
  habitaciones INT CHECK (habitaciones >= 0),
  banos INT CHECK (banos >= 0),
  anio_construccion INT,
  estado ENUM('disponible','en_negociacion','vendida','alquilada','inactiva') DEFAULT 'disponible',
  fecha_publicacion DATE
);

-- ====================================================================
-- 4) TABLA: PROPIEDAD-AGENTE (Co-listing / M:N)
-- ====================================================================
CREATE TABLE propiedad_agente (
  propiedad_id INT NOT NULL,
  agente_id INT NOT NULL,
  tipo_asignacion ENUM('exclusiva','compartida') DEFAULT 'exclusiva',
  fecha_asignacion DATE DEFAULT CURRENT_DATE,
  PRIMARY KEY(propiedad_id, agente_id),
  FOREIGN KEY(propiedad_id) REFERENCES propiedad(id) ON DELETE CASCADE,
  FOREIGN KEY(agente_id) REFERENCES agente(id) ON DELETE CASCADE
);

-- ====================================================================
-- 5) TABLA: HISTORIAL DE PRECIOS
-- ====================================================================
CREATE TABLE precio_propiedad (
  id INT AUTO_INCREMENT PRIMARY KEY,
  propiedad_id INT NOT NULL,
  precio DECIMAL(14,2) NOT NULL CHECK (precio > 0),
  desde TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  hasta TIMESTAMP NULL,
  FOREIGN KEY (propiedad_id) REFERENCES propiedad(id) ON DELETE CASCADE
);

-- ====================================================================
-- 6) TABLA: VISITA
-- ====================================================================
CREATE TABLE visita (
    id INT AUTO_INCREMENT PRIMARY KEY,
    propiedad_id INT NOT NULL,
    cliente_id INT NOT NULL,
    agente_id INT NULL,
    fecha DATE NOT NULL,
    hora TIME NOT NULL,
    estado ENUM('programada','realizada','cancelada') DEFAULT 'programada',
    notas TEXT,
    FOREIGN KEY(propiedad_id) REFERENCES propiedad(id) ON DELETE CASCADE,
    FOREIGN KEY(cliente_id) REFERENCES cliente(id) ON DELETE CASCADE,
    FOREIGN KEY(agente_id) REFERENCES agente(id) ON DELETE SET NULL
);

-- ====================================================================
-- 7) TABLA: OFERTA
-- ====================================================================
CREATE TABLE oferta (
    id INT AUTO_INCREMENT PRIMARY KEY,
    propiedad_id INT NOT NULL,
    cliente_id INT NOT NULL,
    fecha DATE DEFAULT CURRENT_DATE,
    monto DECIMAL(14,2) NOT NULL CHECK (monto > 0),
    estado ENUM('pendiente','aceptada','rechazada') DEFAULT 'pendiente',
    comentarios TEXT,
    FOREIGN KEY(propiedad_id) REFERENCES propiedad(id) ON DELETE CASCADE,
    FOREIGN KEY(cliente_id) REFERENCES cliente(id) ON DELETE CASCADE
);

-- ====================================================================
-- 8) TABLA: TRANSACCION
-- ====================================================================
CREATE TABLE transaccion (
  id INT AUTO_INCREMENT PRIMARY KEY,
  propiedad_id INT NOT NULL,
  fecha_cierre DATE DEFAULT CURRENT_DATE,
  precio_final DECIMAL(14,2) NOT NULL CHECK (precio_final > 0),
  tipo_transaccion ENUM('venta','alquiler') NOT NULL,
  estado_transaccion ENUM('cerrada','cancelada') DEFAULT 'cerrada',
  oferta_id INT NULL,
  FOREIGN KEY(propiedad_id) REFERENCES propiedad(id),
  FOREIGN KEY(oferta_id) REFERENCES oferta(id) ON DELETE SET NULL
);

-- ====================================================================
-- 9) TABLA: TRANSACCION_AGENTE (M:N)
-- ====================================================================
CREATE TABLE transaccion_agente (
  transaccion_id INT NOT NULL,
  agente_id INT NOT NULL,
  comision_monto DECIMAL(14,2) CHECK (comision_monto >= 0),
  comision_porcentaje DECIMAL(5,2) CHECK (comision_porcentaje >= 0 AND comision_porcentaje <= 100),
  PRIMARY KEY(transaccion_id, agente_id),
  FOREIGN KEY(transaccion_id) REFERENCES transaccion(id) ON DELETE CASCADE,
  FOREIGN KEY(agente_id) REFERENCES agente(id) ON DELETE CASCADE
);

-- ================================================================================
-- MDL - Datos de Ejemplo
-- ================================================================================

