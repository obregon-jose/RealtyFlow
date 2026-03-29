-- ================================================================================
-- CONTENIDO: Consultas SQL sobre preguntas de negocio para gestión inmobiliaria
-- ================================================================================

USE realtyflow_db;

-- ¿Cuántas propiedades disponibles existen por ciudad?
SELECT
    ciudad,
    COUNT(*) AS cantidad_propiedades      
FROM propiedad
WHERE estado = 'disponible'               
GROUP BY ciudad
ORDER BY cantidad_propiedades DESC;


-- ¿Cuál es el precio promedio por ciudad y tipo de transacción?
SELECT p.ciudad, t.tipo_transaccion, ROUND(AVG(t.precio_final), 2) AS promedio
FROM transaccion t
JOIN propiedad p ON t.propiedad_id = p.id
GROUP BY p.ciudad, t.tipo_transaccion
ORDER BY promedio DESC;


-- ¿Cuáles propiedades reciben más visitas y qué porcentaje se convierte en transacción?
-- REVISAR NECESIDAD
WITH visitas_por_propiedad AS (
    SELECT
        p.id  AS propiedad_id,            
        COUNT(v.id) AS cantidad_visitas
    FROM propiedad p
    JOIN visita v ON p.id = v.propiedad_id
    GROUP BY p.id
),
transacciones_por_propiedad AS (
    SELECT propiedad_id, COUNT(id) AS cantidad_transacciones
    FROM transaccion
    GROUP BY propiedad_id
),
porcentaje_transacciones_por_visitas AS (
    SELECT
        vpp.propiedad_id,
        vpp.cantidad_visitas,
        COALESCE(tpp.cantidad_transacciones, 0) AS cantidad_transacciones,
        ROUND(
            COALESCE(tpp.cantidad_transacciones, 0) * 100.0
            / vpp.cantidad_visitas,
            2
        ) AS porcentaje_transacciones
    FROM visitas_por_propiedad vpp
    LEFT JOIN transacciones_por_propiedad tpp  
        ON vpp.propiedad_id = tpp.propiedad_id 
)
SELECT * FROM porcentaje_transacciones_por_visitas
ORDER BY porcentaje_transacciones DESC;


--¿Qué porcentaje de ofertas son aceptadas vs rechazadas vs pendientes?
SELECT
    ROUND(SUM(CASE WHEN estado = 'aceptada'  THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS porcentaje_aceptadas,
    ROUND(SUM(CASE WHEN estado = 'rechazada' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS porcentaje_rechazadas,
    ROUND(SUM(CASE WHEN estado = 'pendiente' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS porcentaje_pendientes
FROM oferta;


-- ¿Qué ciudades tienen mayor volumen de transacciones finalizadas?
SELECT p.ciudad, COUNT(t.id) AS cantidad_transacciones_finalizadas
FROM transaccion t
JOIN propiedad p ON t.propiedad_id = p.id
WHERE t.estado_transaccion = 'cerrada'
GROUP BY p.ciudad
ORDER BY cantidad_transacciones_finalizadas DESC
LIMIT 5;


-- #6. ¿Qué rango de precios concentra la mayor cantidad de ofertas?
SELECT
    CASE
        WHEN monto <  100000000  THEN 'Menos de $100M'
        WHEN monto <  200000000  THEN '$100M – $200M'
        WHEN monto <  350000000  THEN '$200M – $350M'
        WHEN monto <  500000000  THEN '$350M – $500M'
        WHEN monto <  750000000  THEN '$500M – $750M'
        ELSE                          'Más de $750M'
    END                          AS rango_precio,
    COUNT(*)                     AS cantidad_ofertas,
    ROUND(AVG(monto) / 1000000, 1) AS promedio_M
FROM oferta
GROUP BY rango_precio
ORDER BY MIN(monto);


-- ¿Qué tipo de inmueble tiene mayor demanda según visitas y ofertas?
WITH cantidad_visitas AS (
    SELECT p.tipo_propiedad, COUNT(v.id) AS cantidad_visitas
    FROM propiedad p
    JOIN visita v ON p.id = v.propiedad_id
    GROUP BY p.tipo_propiedad
),
cantidad_ofertas AS (
    SELECT p.tipo_propiedad, COUNT(o.id) AS cantidad_ofertas
    FROM oferta o
    JOIN propiedad p ON o.propiedad_id = p.id
    GROUP BY p.tipo_propiedad
)
SELECT cv.tipo_propiedad, cv.cantidad_visitas, co.cantidad_ofertas
FROM cantidad_visitas cv
JOIN cantidad_ofertas co ON cv.tipo_propiedad = co.tipo_propiedad
ORDER BY cantidad_visitas DESC, cantidad_ofertas DESC;


-- ¿Cuál es el agente con mayor volumen de ventas?
SELECT a.id, a.nombre, COUNT(t.id) AS cantidad_transacciones
FROM agente a
JOIN transaccion_agente ta ON a.id = ta.agente_id
JOIN transaccion t ON ta.transaccion_id = t.id
WHERE t.estado_transaccion = 'cerrada'
GROUP BY a.id, a.nombre
ORDER BY cantidad_transacciones DESC
LIMIT 10;


-- ¿Cuántas propiedades se encuentran disponibles actualmente?
SELECT COUNT(*) AS cantidad_propiedades_disponibles
FROM propiedad
WHERE estado = 'disponible';


-- ¿Qué tipo de propiedad se vende con mayor frecuencia?
SELECT tipo_propiedad, COUNT(t.id) AS cantidad_ventas
FROM propiedad p
JOIN transaccion t ON p.id = t.propiedad_id
WHERE t.estado_transaccion = 'cerrada'
  AND t.tipo_transaccion   = 'venta'   -- corregido: solo ventas
GROUP BY tipo_propiedad
ORDER BY cantidad_ventas DESC;


-- ¿Cuál es el precio promedio por tipo de propiedad?
SELECT
    p.tipo_propiedad,
    t.tipo_transaccion,
    ROUND(AVG(t.precio_final), 0) AS promedio_precio,
    COUNT(t.id)                   AS cantidad_cierres
FROM propiedad p
JOIN transaccion t ON p.id = t.propiedad_id
WHERE t.estado_transaccion = 'cerrada'
GROUP BY p.tipo_propiedad, t.tipo_transaccion
ORDER BY p.tipo_propiedad, t.tipo_transaccion;


-- ¿Cuántas ofertas recibe en promedio cada propiedad?
SELECT ROUND(AVG(cantidad_ofertas), 2) AS promedio_ofertas_por_propiedad
FROM (
    SELECT p.id, COUNT(o.id) AS cantidad_ofertas
    FROM propiedad p
    LEFT JOIN oferta o ON p.id = o.propiedad_id  
    GROUP BY p.id
) AS ofertas_por_propiedad;

-- Detalle por propiedad:
SELECT p.id, p.ciudad, p.tipo_propiedad, COUNT(o.id) AS cantidad_ofertas
FROM propiedad p
LEFT JOIN oferta o ON p.id = o.propiedad_id
GROUP BY p.id, p.ciudad, p.tipo_propiedad
ORDER BY cantidad_ofertas DESC;

-- ¿Qué zona presenta mayor volumen de transacciones?
SELECT ciudad, COUNT(t.id) AS cantidad_transacciones
FROM propiedad p
JOIN transaccion t ON p.id = t.propiedad_id
GROUP BY ciudad
ORDER BY cantidad_transacciones DESC;


-- ¿Qué agentes han cerrado más transacciones y cuánto ingreso han generado en comisiones?
SELECT
    a.nombre,
    COUNT(ta.transaccion_id)         AS cantidad_transacciones,
    ROUND(SUM(ta.comision_monto), 0) AS comision_total
FROM agente a
JOIN transaccion_agente ta ON a.id = ta.agente_id
JOIN transaccion t ON ta.transaccion_id = t.id
WHERE t.estado_transaccion = 'cerrada'   
GROUP BY a.id, a.nombre
ORDER BY comision_total DESC
LIMIT 10;


-- #15. ¿Cuánto tarda en promedio una propiedad en venderse desde  su publicación hasta el cierre de la transacción?
SELECT ROUND(AVG(diferencia_dias), 1) AS dias_promedio_hasta_cierre
FROM (
    SELECT DATEDIFF(t.fecha_cierre, p.fecha_publicacion) AS diferencia_dias
    --             
    FROM propiedad p
    JOIN transaccion t ON p.id = t.propiedad_id
    WHERE t.estado_transaccion = 'cerrada'
      AND t.fecha_cierre >= p.fecha_publicacion
) AS tiempos;

-- Desglose por ciudad y tipo de propiedad:
SELECT
    p.ciudad,
    p.tipo_propiedad,
    ROUND(AVG(DATEDIFF(t.fecha_cierre, p.fecha_publicacion)), 0) AS dias_promedio
FROM propiedad p
JOIN transaccion t ON p.id = t.propiedad_id
WHERE t.estado_transaccion = 'cerrada'
  AND t.fecha_cierre >= p.fecha_publicacion
GROUP BY p.ciudad, p.tipo_propiedad
ORDER BY dias_promedio ASC;


-- Qué propiedades reciben más visitas y cuál es la tasa de conversión de visitas a transacciones cerradas?
SELECT
    p.id,
    p.ciudad,
    p.tipo_propiedad,
    COUNT(DISTINCT v.id)  AS cantidad_visitas,
    COUNT(DISTINCT CASE WHEN t.estado_transaccion = 'cerrada'
                        THEN t.id END) AS transacciones_cerradas,
    ROUND(
        COUNT(DISTINCT CASE WHEN t.estado_transaccion = 'cerrada'
                            THEN t.id END)
        / NULLIF(COUNT(DISTINCT v.id), 0) * 100,   
        2
    ) AS tasa_conversion_pct
FROM propiedad p
LEFT JOIN visita      v ON p.id = v.propiedad_id
LEFT JOIN transaccion t ON p.id = t.propiedad_id
GROUP BY p.id, p.ciudad, p.tipo_propiedad
HAVING cantidad_visitas > 0                       
ORDER BY cantidad_visitas DESC
LIMIT 20;


-- #17. ¿Qué ciudades tienen el precio promedio más alto?
WITH ranking_precios AS (
    SELECT propiedad_id, precio,
           RANK() OVER (PARTITION BY propiedad_id ORDER BY precio DESC) AS ranking_precio
    FROM precio_propiedad
)
SELECT p.ciudad, ROUND(AVG(rp.precio), 0) AS precio_promedio
FROM propiedad p
JOIN ranking_precios rp ON p.id = rp.propiedad_id
WHERE rp.ranking_precio = 1
GROUP BY p.ciudad
ORDER BY precio_promedio DESC
LIMIT 5;


-- ¿Qué porcentaje de propiedades publicadas termina en una transacción exitosa?
SELECT
    COUNT(DISTINCT p.id)            AS total_propiedades,
    COUNT(DISTINCT t.propiedad_id)  AS propiedades_con_cierre,
    ROUND(
        COUNT(DISTINCT t.propiedad_id) * 100.0
        / COUNT(DISTINCT p.id),         
        2
    )                               AS porcentaje_exitosas
FROM propiedad p
LEFT JOIN transaccion t              
    ON p.id = t.propiedad_id
    AND t.estado_transaccion = 'cerrada';



-- ¿Cuál es el tiempo promedio que tarda cada agente en cerrar una venta?
SELECT
    a.nombre,
    COUNT(t.id)  AS cierres,
    ROUND(AVG(DATEDIFF(t.fecha_cierre, p.fecha_publicacion)), 0) AS dias_promedio_cierre
FROM agente a
JOIN transaccion_agente ta ON a.id  = ta.agente_id
JOIN transaccion t         ON ta.transaccion_id = t.id
JOIN propiedad p           ON t.propiedad_id    = p.id
WHERE t.estado_transaccion  = 'cerrada'
  AND t.fecha_cierre        >= p.fecha_publicacion
GROUP BY a.id, a.nombre
HAVING cierres >= 2           
ORDER BY dias_promedio_cierre ASC
LIMIT 15;


-- ¿Qué propiedades llevan más tiempo disponibles sin recibir ofertas?
SELECT
    p.id,
    p.ciudad,
    p.tipo_propiedad,
    p.tipo_publicacion,
    p.fecha_publicacion,
    DATEDIFF(CURDATE(), p.fecha_publicacion) AS dias_sin_oferta
FROM propiedad p
LEFT JOIN oferta o ON p.id = o.propiedad_id
WHERE p.estado = 'disponible'    
  AND o.id IS NULL               
ORDER BY dias_sin_oferta DESC    
LIMIT 20;


-- Resumen por rango de precio (muestra la tendencia):
SELECT
    CASE
        WHEN pp.precio <  100000000  THEN 'Menos de $100M'
        WHEN pp.precio <  200000000  THEN '$100M – $200M'
        WHEN pp.precio <  350000000  THEN '$200M – $350M'
        WHEN pp.precio <  500000000  THEN '$350M – $500M'
        WHEN pp.precio <  750000000  THEN '$500M – $750M'
        ELSE                              'Más de $750M'
    END                                AS rango_precio,
    COUNT(DISTINCT p.id)               AS cantidad_propiedades,
    ROUND(AVG(COALESCE(sub.visitas, 0)), 1) AS visitas_promedio
FROM propiedad p
JOIN precio_propiedad pp
    ON p.id = pp.propiedad_id
    AND pp.hasta IS NULL               -- solo precio vigente actual
LEFT JOIN (
    SELECT propiedad_id, COUNT(*) AS visitas
    FROM visita
    GROUP BY propiedad_id
) sub ON p.id = sub.propiedad_id
GROUP BY rango_precio
ORDER BY MIN(pp.precio);

-- Detalle por propiedad (para análisis granular):
SELECT
    p.id,
    p.ciudad,
    p.tipo_propiedad,
    pp.precio                       AS precio_vigente,
    ROUND(pp.precio / 1000000, 1)   AS precio_M,
    COALESCE(sub.visitas, 0)        AS cantidad_visitas
FROM propiedad p
JOIN precio_propiedad pp
    ON p.id = pp.propiedad_id
    AND pp.hasta IS NULL
LEFT JOIN (
    SELECT propiedad_id, COUNT(*) AS visitas
    FROM visita
    GROUP BY propiedad_id
) sub ON p.id = sub.propiedad_id
ORDER BY pp.precio ASC;