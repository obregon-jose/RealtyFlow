=======================================
-- CONTENIDO: Consultas SQL sobre preguntas de negocio para gestión inmobiliaria
=======================================
USE realtyflow_db;


-- 1. INMUEBLES DISPONIBLES POR CIUDAD

SELECT
    c.nombre AS ciudad,
    COUNT(*) AS cantidad_inmuebles
FROM inmueble p
JOIN ciudad c ON p.ciudad_id = c.id
WHERE p.estado = 'disponible'
GROUP BY c.nombre
ORDER BY cantidad_inmuebles DESC;



-- 2. PRECIO PROMEDIO POR CIUDAD Y TIPO

SELECT 
    c.nombre AS ciudad,
    t.tipo_transaccion,
    ROUND(AVG(t.precio_final), 2) AS promedio
FROM transaccion t
JOIN inmueble p ON t.inmueble_id = p.id
JOIN ciudad c ON p.ciudad_id = c.id
WHERE t.estado_transaccion = 'cerrada'
GROUP BY c.nombre, t.tipo_transaccion
ORDER BY promedio DESC;



-- 3. VISITAS VS TRANSACCIONES

WITH visitas_por_inmueble AS (
    SELECT inmueble_id, COUNT(*) AS cantidad_visitas
    FROM visita
    GROUP BY inmueble_id
),
transacciones_por_inmueble AS (
    SELECT inmueble_id, COUNT(*) AS cantidad_transacciones
    FROM transaccion
    WHERE estado_transaccion = 'cerrada'
    GROUP BY inmueble_id
)
SELECT
    v.inmueble_id,
    v.cantidad_visitas,
    COALESCE(t.cantidad_transacciones, 0) AS cantidad_transacciones,
    ROUND(
        COALESCE(t.cantidad_transacciones, 0) * 100.0 /
        NULLIF(v.cantidad_visitas, 0),
        2
    ) AS porcentaje_conversion
FROM visitas_por_inmueble v
LEFT JOIN transacciones_por_inmueble t 
    ON v.inmueble_id = t.inmueble_id
ORDER BY porcentaje_conversion DESC;



-- 4. % OFERTAS (ACEPTADAS / RECHAZADAS / PENDIENTES)

SELECT
    ROUND(SUM(CASE WHEN estado = 'aceptada' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS aceptadas,
    ROUND(SUM(CASE WHEN estado = 'rechazada' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS rechazadas,
    ROUND(SUM(CASE WHEN estado = 'pendiente' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS pendientes
FROM oferta;



-- 5. TOP CIUDADES POR TRANSACCIONES

SELECT 
    c.nombre AS ciudad,
    COUNT(t.id) AS total
FROM transaccion t
JOIN inmueble p ON t.inmueble_id = p.id
JOIN ciudad c ON p.ciudad_id = c.id
WHERE t.estado_transaccion = 'cerrada'
GROUP BY c.nombre
ORDER BY total DESC
LIMIT 5;



-- 6. RANGO DE PRECIOS DE OFERTAS

SELECT
    CASE
        WHEN monto < 100000000 THEN 'Menos de 100M'
        WHEN monto < 200000000 THEN '100M - 200M'
        WHEN monto < 350000000 THEN '200M - 350M'
        WHEN monto < 500000000 THEN '350M - 500M'
        WHEN monto < 750000000 THEN '500M - 750M'
        ELSE 'Más de 750M'
    END AS rango,
    COUNT(*) AS cantidad
FROM oferta
GROUP BY rango
ORDER BY MIN(monto);



-- 7. DEMANDA POR TIPO DE INMUEBLE

WITH visitas AS (
    SELECT p.tipo_inmueble, COUNT(v.id) AS total_visitas
    FROM inmueble p
    JOIN visita v ON p.id = v.inmueble_id
    GROUP BY p.tipo_inmueble
),
ofertas AS (
    SELECT p.tipo_inmueble, COUNT(o.id) AS total_ofertas
    FROM inmueble p
    JOIN oferta o ON p.id = o.inmueble_id
    GROUP BY p.tipo_inmueble
)
SELECT v.tipo_inmueble, v.total_visitas, o.total_ofertas
FROM visitas v
JOIN ofertas o ON v.tipo_inmueble = o.tipo_inmueble
ORDER BY total_visitas DESC;



-- 8. TOP AGENTES POR TRANSACCIONES

SELECT
    a.nombre,
    COUNT(t.id) AS total
FROM agente a
JOIN transaccion_agente ta ON a.id = ta.agente_id
JOIN transaccion t ON ta.transaccion_id = t.id
WHERE t.estado_transaccion = 'cerrada'
GROUP BY a.id, a.nombre
ORDER BY total DESC
LIMIT 10;



-- 9. TOTAL INMUEBLES DISPONIBLES

SELECT COUNT(*) AS total
FROM inmueble
WHERE estado = 'disponible';



-- 10. TIPO DE INMUEBLE MÁS VENDIDO

SELECT
    p.tipo_inmueble,
    COUNT(*) AS total
FROM inmueble p
JOIN transaccion t ON p.id = t.inmueble_id
WHERE t.estado_transaccion = 'cerrada'
  AND t.tipo_transaccion = 'venta'
GROUP BY p.tipo_inmueble
ORDER BY total DESC;



-- 11. PRECIO PROMEDIO POR TIPO

SELECT
    p.tipo_inmueble,
    t.tipo_transaccion,
    ROUND(AVG(t.precio_final), 0) AS promedio
FROM inmueble p
JOIN transaccion t ON p.id = t.inmueble_id
WHERE t.estado_transaccion = 'cerrada'
GROUP BY p.tipo_inmueble, t.tipo_transaccion;



-- 12. PROMEDIO DE OFERTAS POR INMUEBLE

SELECT ROUND(AVG(total_ofertas), 2)
FROM (
    SELECT inmueble_id, COUNT(*) AS total_ofertas
    FROM oferta
    GROUP BY inmueble_id
) t;



-- 13. TRANSACCIONES POR CIUDAD

SELECT
    c.nombre AS ciudad,
    COUNT(t.id) AS total
FROM inmueble p
JOIN ciudad c ON p.ciudad_id = c.id
JOIN transaccion t ON p.id = t.inmueble_id
WHERE t.estado_transaccion = 'cerrada'
GROUP BY c.nombre
ORDER BY total DESC;



-- 14. COMISIONES POR AGENTE

SELECT
    a.nombre,
    COUNT(*) AS transacciones,
    SUM(ta.comision_monto) AS comision_total
FROM agente a
JOIN transaccion_agente ta ON a.id = ta.agente_id
JOIN transaccion t ON ta.transaccion_id = t.id
WHERE t.estado_transaccion = 'cerrada'
GROUP BY a.id, a.nombre
ORDER BY comision_total DESC;



-- 15. TIEMPO PROMEDIO DE VENTA

SELECT
    ROUND(AVG(DATEDIFF(t.fecha_cierre, p.fecha_publicacion)), 1) AS dias
FROM inmueble p
JOIN transaccion t ON p.id = t.inmueble_id
WHERE t.estado_transaccion = 'cerrada'
  AND t.fecha_cierre >= p.fecha_publicacion;



-- 16. CONVERSION VISITAS → VENTAS

SELECT
    p.id,
    COUNT(DISTINCT v.id) AS visitas,
    COUNT(DISTINCT t.id) AS ventas,
    ROUND(
        COUNT(DISTINCT t.id) /
        NULLIF(COUNT(DISTINCT v.id), 0) * 100,
        2
    ) AS conversion
FROM inmueble p
LEFT JOIN visita v ON p.id = v.inmueble_id
LEFT JOIN transaccion t 
    ON p.id = t.inmueble_id
    AND t.estado_transaccion = 'cerrada'
GROUP BY p.id
HAVING visitas > 0
ORDER BY conversion DESC;



-- 17. CIUDADES CON PRECIOS MÁS ALTOS

SELECT
    c.nombre,
    ROUND(AVG(pp.precio), 0) AS promedio
FROM inmueble p
JOIN ciudad c ON p.ciudad_id = c.id
JOIN precio pp ON p.id = pp.inmueble_id
WHERE pp.hasta IS NULL
GROUP BY c.nombre
ORDER BY promedio DESC
LIMIT 5;



-- 18. % INMUEBLES CON TRANSACCION

SELECT
    COUNT(*) AS total,
    COUNT(DISTINCT t.inmueble_id) AS vendidos,
    ROUND(COUNT(DISTINCT t.inmueble_id) * 100.0 / COUNT(*), 2) AS porcentaje
FROM inmueble p
LEFT JOIN transaccion t 
    ON p.id = t.inmueble_id
    AND t.estado_transaccion = 'cerrada';



-- 19. TIEMPO PROMEDIO POR AGENTE

SELECT
    a.nombre,
    ROUND(AVG(DATEDIFF(t.fecha_cierre, p.fecha_publicacion)), 0) AS dias
FROM agente a
JOIN transaccion_agente ta ON a.id = ta.agente_id
JOIN transaccion t ON ta.transaccion_id = t.id
JOIN inmueble p ON t.inmueble_id = p.id
WHERE t.estado_transaccion = 'cerrada'
GROUP BY a.id, a.nombre
ORDER BY dias ASC;



-- 20. INMUEBLES SIN OFERTAS

SELECT
    p.id,
    DATEDIFF(CURDATE(), p.fecha_publicacion) AS dias
FROM inmueble p
LEFT JOIN oferta o ON p.id = o.inmueble_id
WHERE o.id IS NULL
  AND p.estado = 'disponible'
ORDER BY dias DESC;
