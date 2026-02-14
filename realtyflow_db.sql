-- ================================================================================
-- ARCHIVO: realtyflow_db.sql
-- DESCRIPCIÓN: Script de base de datos para RealtyFlow en MySQL
-- CONTENIDO: 
-- Tablas para gestión inmobiliaria (propiedades, agentes, clientes, transacciones, visitas, ofertas y documentos)
-- Datos de ejemplo para pruebas  
-- ================================================================================


-- ================================================================================
-- DDL - Definición de Tablas
-- ================================================================================

-- ============================================
-- 0) CREATE DATABASE: realtyflow_db
-- ============================================
CREATE DATABASE IF NOT EXISTS realtyflow_db;
USE realtyflow_db;

-- ============================================
-- 1) TABLA: AGENTE
-- ============================================
CREATE TABLE agente (
  id INT PRIMARY KEY AUTO_INCREMENT,
  nombre VARCHAR(120) NOT NULL,
  telefono VARCHAR(32),
  email VARCHAR(200),
  porcentaje_comision DECIMAL(5,2) DEFAULT 0,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- 2) TABLA: CLIENTE
-- ============================================
CREATE TABLE cliente (
  id INT PRIMARY KEY AUTO_INCREMENT,
  nombre VARCHAR(120) NOT NULL,
  telefono VARCHAR(32),
  email VARCHAR(200),
  preferencias JSON,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- 3) TABLA: PROPIEDAD
-- ============================================
CREATE TABLE propiedad (
  id INT PRIMARY KEY AUTO_INCREMENT,
  tipo_publicacion ENUM('venta','alquiler') NOT NULL,
  tipo_propiedad ENUM('casa','apartamento','terreno') NOT NULL,
  direccion VARCHAR(200) UNIQUE NOT NULL,
  ciudad VARCHAR(100) NOT NULL,
  area_m2 DECIMAL(10,2),
  habitaciones INT,
  banos INT,
  anio_construccion INT,
  estado ENUM('disponible','en_negociacion','vendida','alquilada','inactiva') DEFAULT 'disponible',
  -- Agente exclusivo (opcional, cumple requisito sin tabla extra)
  agente_exclusivo_id INT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_propiedad_agente_exclusivo
    FOREIGN KEY (agente_exclusivo_id) REFERENCES agente(id)
    ON DELETE SET NULL
);

-- ============================================
-- 4) TABLA: HISTORIAL DE PRECIOS
-- ============================================
CREATE TABLE precio_propiedad (
  id INT PRIMARY KEY AUTO_INCREMENT,
  propiedad_id INT NOT NULL,
  precio DECIMAL(14,2) NOT NULL,
  desde TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  hasta TIMESTAMP NULL,

  CONSTRAINT fk_precio_propiedad
    FOREIGN KEY (propiedad_id) REFERENCES propiedad(id)
    ON DELETE CASCADE
);

-- ============================================
-- 5) TABLA: VISITA
-- ============================================
CREATE TABLE visita (
  id INT PRIMARY KEY AUTO_INCREMENT,
  propiedad_id INT NOT NULL,
  agente_id INT NULL,
  cliente_id INT NULL,
  fecha_hora TIMESTAMP NOT NULL,
  notas TEXT,
  estado ENUM('programada','realizada','cancelada') DEFAULT 'programada',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

  CONSTRAINT fk_visita_propiedad
    FOREIGN KEY (propiedad_id) REFERENCES propiedad(id)
    ON DELETE CASCADE,

  CONSTRAINT fk_visita_agente
    FOREIGN KEY (agente_id) REFERENCES agente(id)
    ON DELETE SET NULL,

  CONSTRAINT fk_visita_cliente
    FOREIGN KEY (cliente_id) REFERENCES cliente(id)
    ON DELETE SET NULL
);

-- ============================================
-- 6) TABLA: OFERTA
-- ============================================
CREATE TABLE oferta (
  id INT PRIMARY KEY AUTO_INCREMENT,
  propiedad_id INT NOT NULL,
  cliente_id INT NOT NULL,
  fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  monto DECIMAL(14,2) NOT NULL,
  estado ENUM('pendiente','aceptada','rechazada') DEFAULT 'pendiente',
  comentarios TEXT,

  CONSTRAINT fk_oferta_propiedad
    FOREIGN KEY (propiedad_id) REFERENCES propiedad(id)
    ON DELETE CASCADE,

  CONSTRAINT fk_oferta_cliente
    FOREIGN KEY (cliente_id) REFERENCES cliente(id)
    ON DELETE CASCADE
);

-- ============================================
-- 7) TABLA: TRANSACCION
-- ============================================
CREATE TABLE transaccion (
  id INT PRIMARY KEY AUTO_INCREMENT,
  propiedad_id INT NOT NULL,
  cliente_id INT NOT NULL,
  oferta_id INT NULL,
  fecha_cierre TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  precio_final DECIMAL(14,2) NOT NULL,
  tipo_transaccion ENUM('venta','alquiler') NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

  CONSTRAINT fk_transaccion_propiedad
    FOREIGN KEY (propiedad_id) REFERENCES propiedad(id),

  CONSTRAINT fk_transaccion_cliente
    FOREIGN KEY (cliente_id) REFERENCES cliente(id),

  CONSTRAINT fk_transaccion_oferta
    FOREIGN KEY (oferta_id) REFERENCES oferta(id)
    ON DELETE SET NULL
);

-- ============================================
-- 8) TABLA: TRANSACCION_AGENTE (muchos a muchos)
-- ============================================
CREATE TABLE transaccion_agente (
  id INT PRIMARY KEY AUTO_INCREMENT,
  transaccion_id INT NOT NULL,
  agente_id INT NOT NULL,
  comision_monto DECIMAL(14,2),
  comision_porcentaje DECIMAL(5,2),

  CONSTRAINT fk_transaccion_agente_transaccion
    FOREIGN KEY (transaccion_id) REFERENCES transaccion(id)
    ON DELETE CASCADE,

  CONSTRAINT fk_transaccion_agente_agente
    FOREIGN KEY (agente_id) REFERENCES agente(id)
    ON DELETE CASCADE
);

-- ============================================
-- 9) TABLA: DOCUMENTO
-- ============================================
CREATE TABLE documento (
  id INT PRIMARY KEY AUTO_INCREMENT,
  transaccion_id INT NOT NULL,
  tipo_documento VARCHAR(64),
  url_archivo TEXT,
  fecha_subida TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

  CONSTRAINT fk_documento_transaccion
    FOREIGN KEY (transaccion_id) REFERENCES transaccion(id)
    ON DELETE CASCADE
);



-- ================================================================================
-- MDL - Datos de Ejemplo
-- ================================================================================

