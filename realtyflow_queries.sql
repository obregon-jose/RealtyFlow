-- ================================================================================
-- CONTENIDO: Consultas SQL para gestión inmobiliaria
-- ================================================================================

-- Pregunta 1: 
-- Pregunta 2: 
-- Pregunta 3: 
-- Pregunta 4: 
-- Pregunta 5: 
-- Pregunta 6: 
-- Pregunta 7: 
-- Pregunta 8: 
-- Pregunta 9: 
-- Pregunta 10:


CREATE TABLE estado_propiedad (
  id INT PRIMARY KEY AUTO_INCREMENT,
  nombre VARCHAR(50) UNIQUE NOT NULL
);

CREATE TABLE tipo_publicacion (
  id INT PRIMARY KEY AUTO_INCREMENT,
  nombre VARCHAR(50) UNIQUE NOT NULL
);

CREATE TABLE tipo_propiedad (
  id INT PRIMARY KEY AUTO_INCREMENT,
  nombre VARCHAR(50) UNIQUE NOT NULL
);

CREATE TABLE estado_visita (
  id INT PRIMARY KEY AUTO_INCREMENT,
  nombre VARCHAR(50) UNIQUE NOT NULL
);

CREATE TABLE estado_oferta (
  id INT PRIMARY KEY AUTO_INCREMENT,
  nombre VARCHAR(50) UNIQUE NOT NULL
);

CREATE TABLE agente (
  id INT PRIMARY KEY AUTO_INCREMENT,
  nombre VARCHAR(120) NOT NULL,
  telefono VARCHAR(20) UNIQUE,
  correo VARCHAR(200) UNIQUE,
  fecha_ingreso DATE,
  activo BOOLEAN DEFAULT TRUE,
  porcentaje_comision_base DECIMAL(5,2) DEFAULT 3.00,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE cliente (
  id INT PRIMARY KEY AUTO_INCREMENT,
  nombre VARCHAR(120) NOT NULL,
  telefono VARCHAR(20),
  correo VARCHAR(200),
  ciudad VARCHAR(100),
  presupuesto_min DECIMAL(14,2),
  presupuesto_max DECIMAL(14,2),
  fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  canal_adquisicion VARCHAR(100),
  UNIQUE (telefono, correo)
);
CREATE TABLE propiedad (
  id INT PRIMARY KEY AUTO_INCREMENT,
  codigo VARCHAR(50) UNIQUE,
  tipo_publicacion_id INT NOT NULL,
  tipo_propiedad_id INT NOT NULL,
  estado_id INT NOT NULL,
  direccion VARCHAR(200) NOT NULL,
  ciudad VARCHAR(100) NOT NULL,
  area_m2 DECIMAL(10,2),
  habitaciones INT,
  banos INT,
  parqueaderos INT,
  estrato INT,
  anio_construccion INT,
  fecha_publicacion DATE,
  fecha_retiro DATE,
  agente_exclusivo_id INT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

  FOREIGN KEY (tipo_publicacion_id) REFERENCES tipo_publicacion(id),
  FOREIGN KEY (tipo_propiedad_id) REFERENCES tipo_propiedad(id),
  FOREIGN KEY (estado_id) REFERENCES estado_propiedad(id),
  FOREIGN KEY (agente_exclusivo_id) REFERENCES agente(id)
);
CREATE TABLE precio_propiedad (
  id INT PRIMARY KEY AUTO_INCREMENT,
  propiedad_id INT NOT NULL,
  precio DECIMAL(14,2) NOT NULL,
  fecha_inicio TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  fecha_fin TIMESTAMP NULL,
  FOREIGN KEY (propiedad_id) REFERENCES propiedad(id) ON DELETE CASCADE
);
CREATE TABLE visita (
  id INT PRIMARY KEY AUTO_INCREMENT,
  propiedad_id INT NOT NULL,
  agente_id INT,
  cliente_id INT,
  estado_id INT NOT NULL,
  fecha_programada TIMESTAMP,
  fecha_realizada TIMESTAMP NULL,
  duracion_minutos INT,
  calificacion_cliente INT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

  FOREIGN KEY (propiedad_id) REFERENCES propiedad(id) ON DELETE CASCADE,
  FOREIGN KEY (agente_id) REFERENCES agente(id),
  FOREIGN KEY (cliente_id) REFERENCES cliente(id),
  FOREIGN KEY (estado_id) REFERENCES estado_visita(id)
);
CREATE TABLE oferta (
  id INT PRIMARY KEY AUTO_INCREMENT,
  propiedad_id INT NOT NULL,
  cliente_id INT NOT NULL,
  estado_id INT NOT NULL,
  monto DECIMAL(14,2) NOT NULL,
  fecha_oferta TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  fecha_respuesta TIMESTAMP NULL,
  FOREIGN KEY (propiedad_id) REFERENCES propiedad(id) ON DELETE CASCADE,
  FOREIGN KEY (cliente_id) REFERENCES cliente(id),
  FOREIGN KEY (estado_id) REFERENCES estado_oferta(id)
);
CREATE TABLE transaccion (
  id INT PRIMARY KEY AUTO_INCREMENT,
  propiedad_id INT NOT NULL,
  cliente_id INT NOT NULL,
  oferta_id INT NULL,
  fecha_cierre TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  precio_final DECIMAL(14,2) NOT NULL,
  dias_en_mercado INT,
  margen_negociacion DECIMAL(5,2),
  FOREIGN KEY (propiedad_id) REFERENCES propiedad(id),
  FOREIGN KEY (cliente_id) REFERENCES cliente(id),
  FOREIGN KEY (oferta_id) REFERENCES oferta(id)
);
CREATE TABLE transaccion_agente (
  id INT PRIMARY KEY AUTO_INCREMENT,
  transaccion_id INT NOT NULL,
  agente_id INT NOT NULL,
  comision_monto DECIMAL(14,2),
  comision_porcentaje DECIMAL(5,2),
  FOREIGN KEY (transaccion_id) REFERENCES transaccion(id) ON DELETE CASCADE,
  FOREIGN KEY (agente_id) REFERENCES agente(id)
);
