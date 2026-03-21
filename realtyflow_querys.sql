USE realtyflow_db;

#1.¿Cuántas propiedades disponibles existen por ciudad?
SELECT ciudad, COUNT(*) AS cantidad_ciudades
FROM propiedad
GROUP BY ciudad
ORDER BY cantidad_ciudades DESC;

#2.¿Cuál es el precio promedio por ciudad y por tipo de transacción (venta/alquiler)?
SELECT p.ciudad, t.tipo_transaccion, ROUND(AVG(t.precio_final), 2) AS promedio
FROM transaccion t
JOIN propiedad p ON t.propiedad_id = p.id
GROUP BY p.ciudad, t.tipo_transaccion
ORDER BY promedio DESC;

#3.¿Cuáles propiedades reciben más visitas y qué porcentaje se convierten en transacción?
WITH visitas_por_propiedad AS (
SELECT p.id, COUNT(v.id) AS cantidad_visitas
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
SELECT tpp.propiedad_id, vpp.cantidad_visitas, tpp.cantidad_transacciones, (tpp.cantidad_transacciones / vpp.cantidad_visitas) * 100.0 AS porcentaje_transacciones
FROM visitas_por_propiedad vpp
JOIN transacciones_por_propiedad tpp ON vpp.id = tpp.propiedad_id
#WHERE vpp.cantidad_visitas >= tpp.cantidad_transacciones
)
SELECT * FROM porcentaje_transacciones_por_visitas ORDER BY porcentaje_transacciones DESC;

#4. ¿Qué porcentaje de ofertas son aceptadas vs rechazadas?
SELECT
  ROUND(SUM(CASE WHEN estado = 'aceptada' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS porcentaje_aceptadas,
  ROUND(SUM(CASE WHEN estado = 'rechazada' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS porcentaje_rechazadas
FROM oferta;

#5.¿Qué ciudades tienen mayor volumen de transacciones finalizadas?
SELECT p.ciudad, COUNT(t.id) AS cantidad_transacciones_finalizadas
FROM transaccion t
JOIN propiedad p ON t.propiedad_id = p.id
WHERE t.estado_transaccion = 'cerrada'
GROUP BY p.ciudad ORDER BY cantidad_transacciones_finalizadas DESC LIMIT 5;

#6. ¿Qué rango de precios concentra la mayor cantidad de ofertas?
#Definir rangos de precios por alta variación de los mismos

#7. ¿Qué tipo de inmueble tiene mayor demanda según visitas y ofertas?
WITH cantidad_visitas AS (
	SELECT tipo_propiedad, COUNT(v.id) AS cantidad_visitas
    FROM propiedad p
    JOIN visita v ON p.id = v.propiedad_id
    GROUP BY tipo_propiedad
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

#8.¿Cuál es el agente con mayor volumen de ventas?
SELECT a.id,a.nombre, COUNT(t.id) AS cantidad_transacciones
FROM agente a
JOIN transaccion_agente ta ON a.id = ta.agente_id
JOIN transaccion t ON ta.transaccion_id = t.id
WHERE t.estado_transaccion = 'cerrada'
GROUP BY a.id ORDER BY cantidad_transacciones DESC LIMIT 1;

#9. ¿Cuántas propiedades se encuentran disponibles actualmente?
SELECT COUNT(*) AS cantidad_propiedades_disponibles FROM propiedad WHERE estado = 'disponible';

#10. ¿Qué tipo de propiedad se vende con mayor frecuencia?
SELECT tipo_propiedad, COUNT(t.id) AS cantidad_ventas
FROM propiedad p
JOIN transaccion t ON p.id = t.propiedad_id
WHERE t.estado_transaccion = 'cerrada'
GROUP BY tipo_propiedad
ORDER BY cantidad_ventas DESC LIMIT 1;

#11.¿Cuál es el precio promedio por tipo de propiedad?
SELECT tipo_propiedad, AVG(t.precio_final) AS promedio_precio
FROM propiedad p
JOIN transaccion t ON p.id = t.propiedad_id
WHERE t.estado_transaccion = 'cerrada'
GROUP BY tipo_propiedad;

#12.¿Cuántas ofertas recibe en promedio cada propiedad?
WITH ofertas_por_propiedad AS (
SELECT p.id, COUNT(o.id) AS cantidad_ofertas
FROM propiedad p
JOIN oferta o ON p.id = o.propiedad_id 
GROUP BY p.id
)
SELECT * FROM ofertas_por_propiedad;

#13.¿Qué zona presenta mayor volumen de transacciones?
SELECT ciudad, COUNT(t.id) AS cantidad_transacciones
FROM propiedad p
JOIN transaccion t ON p.id = t.propiedad_id
GROUP BY ciudad 
ORDER BY cantidad_transacciones DESC
LIMIT 1;

#14. ¿Qué agentes han cerrado más transacciones y cuánto ingreso han generado en comisiones?
SELECT a.nombre, COUNT(ta.transaccion_id) AS cantidad_transacciones, SUM(comision_monto) AS comision_total
FROM agente a
JOIN transaccion_agente ta ON a.id = ta.agente_id
GROUP BY a.nombre ORDER BY cantidad_transacciones DESC LIMIT 5;

#15. ¿Cuál es el tiempo promedio que tarda una propiedad en venderse desde su publicación hasta el cierre de la transacción?
WITH diferencia_tiempo AS (
SELECT DATEDIFF(t.fecha_cierre, p.fecha_publicacion) AS diferencia_tiempo
#SELECT DATEDIFF(p.fecha_publicacion, t.fecha_cierre) AS diferencia_tiempo
FROM propiedad p								  
JOIN transaccion t ON p.id = t.propiedad_id
),
promedio_tiempo_venta AS (
SELECT AVG(diferencia_tiempo) AS tiempo_promedio FROM diferencia_tiempo
)
SELECT * FROM promedio_tiempo_venta;

SELECT AVG(diferencia_dias) AS dias_promedio FROM (
SELECT DATEDIFF(p.fecha_publicacion, t.fecha_cierre) AS diferencia_dias
FROM propiedad p								  
JOIN transaccion t ON p.id = t.propiedad_id
) AS diferencia_tiempo;

#16. ¿Qué propiedades reciben más visitas y cuál es la tasa de conversión de visitas a transacciones cerradas?
WITH cantidad_visitas_transacciones AS (
SELECT p.id,
       (SELECT COUNT(*) FROM visita v WHERE v.propiedad_id = p.id) AS cantidad_visitas,
       (SELECT COUNT(*) FROM transaccion t WHERE t.propiedad_id = p.id AND t.estado_transaccion = 'cerrada') AS cantidad_transacciones
FROM propiedad p
ORDER BY cantidad_visitas DESC),
tasa_conversion_transacciones_cerradas AS (
SELECT id, cantidad_visitas, cantidad_transacciones, ROUND(cantidad_transacciones / cantidad_visitas, 2) AS tasa_conversion
FROM cantidad_visitas_transacciones
)
SELECT * FROM tasa_conversion_transacciones_cerradas LIMIT 10;

#17. ¿Qué ciudades tienen el precio promedio más alto de propiedades?
WITH ranking_precios AS (
	SELECT  propiedad_id, precio, RANK() OVER (PARTITION BY propiedad_id ORDER BY precio DESC) AS ranking_precio 
    FROM precio_propiedad
),
precio_promedio_ciudades AS (
SELECT p.ciudad, ROUND(AVG(rp.precio), 2) AS precio_promedio
FROM propiedad p
JOIN ranking_precios rp ON p.id = rp.propiedad_id
WHERE ranking_precio = 1
GROUP BY p.ciudad
ORDER BY precio_promedio DESC
)
SELECT * FROM precio_promedio_ciudades LIMIT 5;

#18. ¿Qué porcentaje de propiedades publicadas termina en una transacción exitosa?
SELECT ROUND(COUNT(DISTINCT p.id) / COUNT(t.id) * 100, 2) AS porcentaje_exitosas
FROM propiedad p
JOIN transaccion t 
ON p.id = t.propiedad_id AND t.estado_transaccion = 'cerrada';

  #19. ¿Cuál es el tiempo promedio que tarda cada agente en cerrar una venta?
 #Datos insuficientes
 
 #20. ¿Qué propiedades llevan más tiempo disponibles sin recibir ofertas?
SELECT p.id, o.id AS oferta_id, o.fecha
FROM propiedad p
LEFT JOIN oferta o ON p.id = o.propiedad_id
ORDER BY fecha LIMIT 208;


#21. ¿Existe relación entre el precio de una propiedad y la cantidad de visitas que recibe?
#Mucha propiedades no tienen precios variantes

#tablero, 2 enfoques, 2 paginas, y una pagina de nevegacion, graficas filtros estilo presentacion, 2 tablero presentacion, 