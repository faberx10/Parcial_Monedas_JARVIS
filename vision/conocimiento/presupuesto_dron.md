# Presupuesto del dron (archivo Dron_Monedas/Presupuesto_Dron_Monedas_v2.xlsx)

Diseño original del dron (version economica v2, con motores 8520 y ESP32-S3 SuperMini). 
Ojo: el dron que se construyo usa ESP32-C3 SuperMini y motores 615; ver ficha_proyecto.md.


## Hoja: Instrucciones

- DRON LOGISTICO DE MONEDAS - VERSION ECONOMICA (v2)
- QUE CAMBIO RESPECTO A LA VERSION 1
- Carga util: de 49.75 g (5 monedas de $1000) a 10.0 g. Este es el cambio que salva el proyecto.
- Sensor de flujo optico PMW3901 ($95.000): ELIMINADO. Era el item mas caro.
- Sensor frontal VL53L1X: reemplazado por un sensor IR de obstaculo FC-51 (de $38.000 a $6.000).
- Sensor de altura VL53L1X -> VL53L0X (mas barato, alcance de 2 m, suficiente para volar a 1.20 m).
- Regulador buck-boost TPS63020 ($35.000) -> modulo elevador MT3608 ($5.000).
- Cargador multipuerto ($45.000) -> modulo TP4056 ($4.000).
- PCB a medida: DESCARTADO. Se usa perfboard, como corresponde a un proyecto de curso.
- Separadores de nylon: se imprimen en 3D. Solo se compran los tornillos M2.
- Balanza de precision: ELIMINADA del presupuesto. Usa la del laboratorio de la universidad.
- CONSECUENCIA TECNICA DE QUITAR EL FLUJO OPTICO
- Sin PMW3901 el dron NO mantiene posicion horizontal por si solo: deriva lentamente.
- Para un trayecto de 1 metro a 1.20 m de altura esto es asumible: el recorrido dura pocos segundos
- y la deriva acumulada es pequena. El piloto o el agente corrige con comandos de avance.
- Lo que NO vas a poder demostrar es un vuelo estacionario largo y quieto sin intervencion.
- Si el profesor pregunta por eso, la respuesta correcta es: 'es una limitacion conocida del diseno,
- se resuelve con un sensor de flujo optico y quedo fuera del alcance por presupuesto'. Eso es
- ingenieria honesta y se defiende mejor que fingir que no existe el problema.
- COMO USAR ESTE ARCHIVO
- Solo edita las celdas AZULES. Lo demas son formulas.
- AZUL = dato que ingresas   |   NEGRO = formula   |   VERDE = viene de otra hoja
- AMARILLO = supuesto critico que hay que verificar midiendo.
- CRITERIO DE DISENO: RELACION EMPUJE / PESO (T/W)
- T/W = empuje total de los motores / peso total del dron con carga.
-    T/W < 1.30        NO DESPEGA
-    1.30 - 1.70       Despega pero sin autoridad de control
-    1.70 - 2.20       ACEPTABLE para transporte lento y estable  <-- objetivo
-    > 2.20            COMODO
- SUPUESTOS Y FUENTES
- Carga util 10 g: definida por el usuario. Equivale a 1 moneda de $1000 o 2 de $500.
- Masa motor 8520 = 5.0 g (ficha de fabricante: 8.5x20 mm, 12000 kV, 53000 rpm sin carga).
- Empuje por motor: ESTIMADO a partir de ensayos publicados de motores 8520 a 1S (3.5-4.2 V).
-    Metodologia de referencia: notblackmagic.com/projects/motor-test-stand
-    Ese banco probo helices de 45, 55 y 75 mm; la de 75 mm (tipo DJI Tello) dio el mayor empuje.
-    Tambien verifico que el empuje contra ciclo util de PWM es MUY LINEAL: facilita el PID.
- Precios COP: estimados de mercado colombiano y de AliExpress. Verificar antes de comprar.
- EJEMPLO DE FILA (formato esperado)
-    Componente: 'Motor coreless 8520' | Cantidad: 4 | Masa unitaria (g): 5.0 | Subtotal: 20.0

## Hoja: Presupuesto_Peso

- PRESUPUESTO DE PESO - VERSION ECONOMICA
- Ajusta la columna azul cuando peses las piezas reales en la balanza del laboratorio.
- # | Componente | Cantidad | Masa unitaria (g) | Subtotal (g)
- SECCION A - MASA BASE
- 1 | Chasis impreso en PLA (placa + 4 brazos) | 1 | 20 | 20
- 2 | Cuna porta-monedas impresa en PLA | 1 | 3 | 3
- 3 | Tarjeta ESP32-S3 SuperMini (sin headers) | 1 | 4 | 4
- 4 | IMU MPU6050 (modulo GY-521) | 1 | 2 | 2
- 5 | VL53L0X ToF - altura (mirando abajo) | 1 | 1.5 | 1.5
- 6 | Sensor IR de obstaculo FC-51 (frontal) | 1 | 3 | 3
- 7 | Modulo elevador MT3608 (3.7 -> 5 V) | 1 | 1.5 | 1.5
- 8 | Perfboard con los 4 MOSFET y diodos | 1 | 4 | 4
- 9 | Bateria LiPo 1S 450 mAh | 1 | 11 | 11
- 10 | Cableado, conectores JST 1.25, termoencogible | 1 | 4 | 4
- 11 | Tornilleria M2 (separadores impresos en 3D) | 1 | 2 | 2
- SUBTOTAL MASA BASE (g) | 56
- SECCION B - MASA POR CANAL DE PROPULSION (x 4 motores)
- 1 | Motor coreless 8520 (8.5 x 20 mm) | 1 | 5 | 5
- 2 | Helice 75 mm | 1 | 0.7 | 0.7
- 3 | MOSFET AO3400 + diodo 1N5819 + resistencias | 1 | 0.6 | 0.6
- SUBTOTAL POR CANAL (g) | 6.3
- SECCION C - CARGA UTIL
- Carga util objetivo (g) | 10
- Masa de una moneda de $1000 COP (g) | 9.95
- Masa de una moneda de $500 COP (g) | 7.14
- Los 10 g equivalen a 1 moneda de $1000, o a 2 monedas de $200/$500 segun denominacion.
- Pesa las monedas en la balanza del laboratorio para confirmar los valores de catalogo.

## Hoja: Empuje_y_TW

- EMPUJE Y RELACION EMPUJE/PESO (T/W)
- Tres variantes con 4 motores 8520. Misma carga de 10 g.
- T/W objetivo | 2
- Variante | A: helice 65 mm | B: helice 75 mm (RECOMENDADA) | C: helice 75 mm + HC-SR04 (ultra-low-cost)
- Ajuste de masa base (g) | 0 | 0 | 7 | El HC-SR04 pesa 8.5 g contra 1.5 g del VL53L0X
- MASAS
- Masa base (g) | 56 | 56 | 63
- Masa por canal (g) | 6.3 | 6.3 | 6.3
- PESO SECO (g) | 81.2 | 81.2 | 88.2
- Carga util (g) | 10 | 10 | 10
- PESO TOTAL EN VUELO - AUW (g) | 91.2 | 91.2 | 98.2
- EMPUJE
- Empuje por motor a 4.2 V (g)  <-- ESTIMADO | 42 | 52 | 52 | VERIFICAR EN BANCO. Ver hoja Ensayo_de_Banco.
- EMPUJE TOTAL, 4 motores (g) | 168 | 208 | 208
- RESULTADO
- RELACION T/W | 1.84 | 2.28 | 2.12
- VEREDICTO | ACEPTABLE | COMODO | ACEPTABLE
- MARGEN DISPONIBLE
- Carga maxima al T/W objetivo (g) | 2.8 | 22.8 | 15.8
- Monedas de $1000 que podria llevar | 0 | 2 | 1
- LECTURA
- Con 10 g de carga las tres variantes vuelan. Ya no hay problema de empuje.
- La variante B (helice de 75 mm) da T/W = 2.28: margen comodo y el controlador tendra autoridad de sobra.
- La fila 'Carga maxima' muestra que la variante B soporta hasta ~22 g manteniendo T/W = 2.0.
- Es decir: pediste 10 g y el diseno te da mas del doble de margen. Eso es lo que buscabas.
- La variante C existe solo por si no consigues el VL53L0X: el HC-SR04 cuesta menos pero pesa 8.5 g
- y es sensible al ruido acustico de las helices. Es el plan de respaldo, no la primera opcion.

## Hoja: Presupuesto_Costos

- PRESUPUESTO DE COSTOS - SOLO EL DRON (COP)
- Dos escenarios de compra. La columna 'Plan mixto' es la recomendada para cumplir el tope de $200.000.
- # | Item | Cant. | Precio local (COP c/u) | Precio AliExpress (COP c/u) | Fuente recomendada | Subtotal plan mixto (COP)
- 1 | Tarjeta ESP32-S3 SuperMini | 1 | 45000 | 18000 | AliExpress | 18000
- 2 | Set 4 motores coreless 8520 + 4 helices | 1 | 40000 | 24000 | AliExpress | 24000
- 3 | Helices de repuesto 65 y 75 mm (set 8) | 1 | 12000 | 10000 | AliExpress | 10000
- 4 | Bateria LiPo 1S 450 mAh | 2 | 16000 | 16000 | Local (Bogota) | 32000
- 5 | Modulo cargador TP4056 con proteccion | 1 | 4000 | 2500 | AliExpress | 2500
- 6 | IMU MPU6050 (modulo GY-521) | 1 | 10000 | 6000 | AliExpress | 6000
- 7 | Sensor ToF VL53L0X (altura) | 1 | 28000 | 14000 | AliExpress | 14000
- 8 | Sensor IR de obstaculo FC-51 (frontal) | 1 | 6000 | 4000 | AliExpress | 4000
- 9 | Modulo elevador MT3608 (3.7 -> 5 V) | 1 | 5000 | 3500 | AliExpress | 3500
- 10 | MOSFET AO3400 canal N nivel logico (10 und) | 1 | 9000 | 6000 | AliExpress | 6000
- 11 | Diodo Schottky 1N5819 (10 und) | 1 | 5000 | 4000 | AliExpress | 4000
- 12 | Perfboard 5 x 7 cm | 1 | 4000 | 3000 | Local (Bogota) | 4000
- 13 | Cable AWG 28 + conectores JST 1.25 | 1 | 10000 | 8000 | Local (Bogota) | 10000
- 14 | Filamento PLA (~60 g del rollo) | 1 | 5000 | 5000 | Local (Bogota) | 5000
- 15 | Tornilleria M2 (separadores impresos en 3D) | 1 | 5000 | 5000 | Local (Bogota) | 5000
- 16 | Resistencias y condensadores | 1 | 0 | 0 | Local (Bogota) | 0
- SUBTOTAL - TODO LOCAL | 220000
- SUBTOTAL - PLAN MIXTO (recomendado) | 148000
- Contingencia y repuestos | 0.15 | 33000 | 22200
- TOTAL DRON | 253000 | 170200
- Presupuesto tope | 200000
- MARGEN RESTANTE (plan mixto) | 29800
- VEREDICTO | CABE EN PRESUPUESTO
- NOTAS DE COMPRA
- 1. LAS BATERIAS LIPO SE COMPRAN LOCALMENTE. Hay restricciones de envio aereo internacional
-    para celdas de litio; pedirlas a AliExpress suele terminar en cancelacion o retencion.
- 2. Lo importado tarda de 3 a 5 semanas. Haz el pedido ESTA SEMANA o el plan mixto no sirve
-    y tendras que comprar todo local, lo cual se pasa del tope.
- 3. Compra motores y helices de repuesto desde el principio. En las pruebas se rompen, siempre.
- 4. Las resistencias y condensadores van en cero porque ya los tienen del laboratorio de sensores.
-    Si no, presupuesta $8.000 adicionales.
- 5. Este total cubre UNICAMENTE el dron. El resto del sistema de embalaje va aparte.
- SI AUN ASI HAY QUE RECORTAR MAS - palancas en orden de menor dano
- Recorte | Ahorro (COP) | Que se pierde
- Comprar 1 sola bateria en vez de 2 | 16000 | Esperas 40 min de carga entre pruebas. Molesto pero viable.
- VL53L0X -> HC-SR04 ultrasonico | 20000 | Altura mas ruidosa (+7 g). Ver variante C en la hoja de empuje.
- Reutilizar una ESP32 que ya tengan | 45000 | Ninguna, SI es una S3. Una ESP32 clasica tambien sirve para volar.
- Quitar el sensor IR frontal | 4000 | Pierdes la deteccion de obstaculos: es un requisito del proyecto. NO recomendado.
- El ultimo recorte esta listado por completitud, no como recomendacion.

## Hoja: Ensayo_de_Banco

- ENSAYO DE BANCO - MEDICION DE EMPUJE REAL
- Usa la balanza del laboratorio. Este ensayo convierte las estimaciones en datos reales.
- PROCEDIMIENTO
- 1. Sujeta un motor con su helice a un brazo rigido apoyado en la balanza, con la helice EMPUJANDO HACIA ABAJO.
- 2. Enciende la balanza sin el motor girando y pon TARA (cero).
- 3. Alimenta el motor desde fuente de laboratorio a voltaje fijo. Lo que marque la balanza es el empuje.
- 4. Repite a 3.5 V, 3.7 V, 4.0 V y 4.2 V (rango real de una LiPo 1S de vacia a llena).
- 5. Repite con helice de 65 mm y con helice de 75 mm.
- 6. Mide tambien la CORRIENTE: define el MOSFET, el calibre del cable y la autonomia.
- 7. Lleva el valor de 4.2 V a Empuje_y_TW, fila 'Empuje por motor'. Todo se recalcula solo.
- SEGURIDAD: usa gafas. Una helice suelta a 50.000 rpm es un proyectil. Sujeta bien el motor antes de energizar.
- Motor / helice | 3.5 V (g) | 3.7 V (g) | 4.0 V (g) | 4.2 V (g) | Corriente 4.2 V (A)
- 8520 + helice 65 mm
- 8520 + helice 75 mm
- (repuesto / otro)
- Fila de ejemplo con el formato esperado (borrala al usar la hoja):
- 8520 + helice 65 mm | 33.5 | 36.2 | 39.8 | 42.1 | 1.85
- QUE HACER CON LOS RESULTADOS
- Si el empuje medido es menor al estimado, la hoja Empuje_y_TW te dice de inmediato si aun cumples.
- La corriente x 4 define el MOSFET y el cable. El AO3400 aguanta 5.7 A, asi que va sobrado;
- el cable AWG 28 sirve hasta ~2 A por motor. Si mides mas, sube a AWG 24 en el tramo de bateria.
- Autonomia aproximada = capacidad de la bateria (mAh) / corriente total en vuelo (mA) x 60 minutos.
- Con 450 mAh y ~4 motores al 60% espera entre 4 y 6 minutos de vuelo. Suficiente para la demostracion.
