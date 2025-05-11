# LCP (Local Chat Protocol) - Flujo Detallado

## Índice

- [Arquitectura](#arquitectura)
- [Flujo del Protocolo](#flujo-del-protocolo)
  - [Inicialización](#inicialización)
  - [Autodescubrimiento](#autodescubrimiento)
  - [Envío de Mensajes](#envío-de-mensajes)
  - [Recepción de Mensajes](#recepción-de-mensajes)
  - [Transferencia de Archivos](#transferencia-de-archivos)
- [Manejo de Concurrencia](#manejo-de-concurrencia)
- [Sistema de Seguridad](#sistema-de-seguridad)
- [Optimización de Recursos](#optimización-de-recursos)

## Arquitectura

```
+-------------------+       +-------------------+
|                   |       |                   |
|    Cliente LCP    |<----->|    Cliente LCP    |
|                   |       |                   |
+-------------------+       +-------------------+
        ^                           ^
        |                           |
        v                           v
+-------------------+       +-------------------+
|   Red Local       |<----->|   Red Local       |
+-------------------+       +-------------------+
```

La arquitectura es completamente descentralizada (P2P). Cada instancia de `LCPPeer` actúa simultáneamente como:

- **Cliente**: Envía mensajes y archivos a otros peers
- **Servidor**: Recibe mensajes y archivos de otros peers

## Flujo del Protocolo

### Inicialización

```
                     +------------------------+
                     |                        |
                     |  Creación de LCPPeer   |
                     |                        |
                     +------------------------+
                                |
                                v
          +-------------------------------------------+
          |                                           |
          |  Detección de recursos del sistema        |
          |  Configuración adaptativa de hilos        |
          |  Configuración de sockets UDP/TCP         |
          |  Inicialización de locks para concurrencia|
          |                                           |
          +-------------------------------------------+
                                |
                                v
          +-------------------------------------------+
          |                                           |
          |  Inicio de hilos:                         |
          |   - UDP Listener                          |
          |   - TCP Listener                          |
          |   - Discovery Service                     |
          |   - N Workers para mensajes               |
          |   - M Workers para archivos               |
          |    (N y M se determinan automáticamente)  |
          |                                           |
          +-------------------------------------------+
```

El proceso de inicialización incluye:

1. Detección de recursos disponibles en el sistema (memoria, carga de CPU)
2. Creación de un ID único para este peer
3. Configuración de sockets UDP para mensajes y control en puerto 9990
4. Configuración de sockets TCP para transferencia de archivos en puerto 9990
5. Inicialización de estructuras para gestionar concurrencia (locks)
6. Creación de colas de trabajo para mensajes y archivos
7. Inicio de hilos de ejecución optimizados para el sistema actual

### Autodescubrimiento

```
          +------------------------+
          |                        |
          |  Discovery Service     |
          |  (Operación 0: ECHO)   |
          |                        |
          +------------------------+
                     |
                     v
          +------------------------+
          |                        |
          |  Envío de Echo         |
          |  (Broadcast)           |
          |  cada 5 segundos       |
          |                        |
          +------------------------+
                     |
                     v
+-----------------------------------------------------+
|                                                     |
|  Procesamiento inmediato de ECHO (sin encolar)      |
|  - Actualización de lista de peers                  |
|  - Respuesta inmediata al emisor                    |
|                                                     |
+-----------------------------------------------------+
                     |
                     v
          +------------------------+
          |                        |
          |  Limpieza de peers     |
          |  inactivos (>90s)      |
          |                        |
          +------------------------+
```

Cada peer envía periódicamente (cada 5 segundos) un mensaje de tipo ECHO (operación 0) a la dirección de broadcast de la red local. A diferencia de otros tipos de mensajes, los ECHOs se procesan inmediatamente sin ponerlos en cola, para garantizar respuestas rápidas. Esto permite:

- Anunciar su presencia a otros peers
- Descubrir nuevos peers que aparecen en la red
- Mantener la lista de peers activos actualizada
- Eliminar peers inactivos automáticamente
- Responder rápidamente a solicitudes de descubrimiento

### Envío de Mensajes

```
     PEER A                                      PEER B
     -------                                     -------
       |                                           |
       |    [1. HEADER (100 bytes)]                |
       +------------------------------------------>|
       |           Operation = 1 (MESSAGE)         |
       |                                           |
       |                                          [Procesamiento del header]
       |                                           |
       |    [2. RESPONSE OK (25 bytes)]            |
       |<------------------------------------------+
       |                                           |
       |                                           |
       |    [3. BODY (mensaje)]                    |
       +------------------------------------------>|
       |                                           |
       |                                          [Procesamiento del mensaje]
       |                                           |
       |    [4. RESPONSE OK (25 bytes)]            |
       |<------------------------------------------+
```

El envío de mensajes sigue un protocolo de tres fases:

1. **Fase de inicialización**:
   - Envío de header (100 bytes) al puerto 9990 del destinatario
   - Header contiene: ID origen, ID destino, tipo operación (1=MESSAGE), ID del mensaje, longitud

2. **Fase de confirmación de header**:
   - Recepción de respuesta (25 bytes) del destinatario
   - Verificación del código de estado (0=OK)
   - Verificación de la identidad del remitente

3. **Fase de transferencia**:
   - Envío del cuerpo del mensaje
   - Recepción de confirmación final
   - Verificación nuevamente de la identidad

### Recepción de Mensajes

```
     PEER A                                      PEER B
     -------                                     -------
       |                                           |
       |                       [HEADER]            |
       |<------------------------------------------+
       |                                           |
      [Verificar header]                           |
       |                                           |
       |                       [RESPONSE OK]       |
       +------------------------------------------>|
       |                                           |
       |                       [BODY]              |
       |<------------------------------------------+
       |                                           |
      [Procesar mensaje]                           |
       |                                           |
       |                       [RESPONSE OK]       |
       +------------------------------------------>|
```

El proceso de recepción de mensajes incluye:

1. **Recepción del header**:
   - El UDP Listener recibe el header en el puerto 9990
   - Se verifica el formato y contenido del header
   - Se crea un socket dedicado para esta conversación con puerto aleatorio

2. **Procesamiento del cuerpo**:
   - Se envía confirmación de header
   - Se recibe el cuerpo del mensaje en el socket dedicado
   - Se verifica que el BodyId coincide con el del header
   - Se notifica a los callbacks registrados

3. **Finalización**:
   - Se envía confirmación final de recepción
   - Se cierra el socket dedicado a esta conversación

### Transferencia de Archivos

```
     PEER A                                      PEER B
     -------                                     -------
       |                                           |
       | [1. Encolar archivo para envío]           |
       |                                           |
       | [2. FileSender toma archivo de la cola]   |
       |                                           |
       |    [3. HEADER (100 bytes)]                |
       +------------------------------------------>|
       |           Operation = 2 (FILE)            |
       |                                           |
       |                                          [Procesamiento del header]
       |                                           |
       |    [4. RESPONSE OK (25 bytes)]            |
       |<------------------------------------------+
       |                                           |
       |                                           |
       |    [5. TCP CONNECTION]                    |
       +==========================================>|
       |                                           |
       |    [6. FILE DATA (TCP Stream)]            |
       +------------------------------------------>|
       |        [Notificación de progreso]         |
       |                                           |
       |                                          [Guardado del archivo]
       |                                           |
       |    [7. RESPONSE OK (25 bytes)]            |
       |<------------------------------------------+
       |                                           |
       |    [8. CLOSE CONNECTION]                  |
       +==========================================X|
       |                                           |
       | [9. FileSender libera recurso]            |
       |    [Notificación de finalización]         |
```

El sistema de transferencia de archivos ahora es totalmente concurrente:

1. **Fase de encolamiento**:
   - El archivo se añade a una cola de transferencias
   - Un worker dedicado (FileSender) toma el archivo cuando hay recursos disponibles
   - Se gestiona un límite máximo de transferencias simultáneas

2. **Fase de control por UDP**:
   - Envío de header (operación 2=FILE) por UDP al puerto 9990
   - Header incluye: ID origen, ID destino, tamaño del archivo
   - Recepción de confirmación

3. **Fase de transferencia por TCP con notificaciones de progreso**:
   - Establecimiento de conexión TCP al puerto 9990
   - Envío de flujo de datos con notificaciones periódicas de progreso (0-100%)
   - El receptor guarda los datos en archivo temporal

4. **Fase de finalización**:
   - Confirmación final por TCP
   - Cierre de la conexión
   - Liberación de recursos
   - Notificación de finalización exitosa o error

## Manejo de Concurrencia

```
                    +------------------------+                    +------------------------+
                    |                        |                    |                        |
                    |   UDP Listener         |                    |   TCP Listener         |
                    |   (Puerto 9990)        |                    |   (Puerto 9990)        |
                    |                        |                    |                        |
                    +------------------------+                    +------------------------+
                               |                                              |
                               v                                              v
          +-------------------+   +-------------------+     +-------------------+   +-------------------+
          |                   |   |                   |     |                   |   |                   |
          |  Cola de Mensajes |   | Mensajes ECHO     |     | Conexiones TCP    |   |  Cola de Archivos |
          |  (Tipo 1)         |   | (Tipo 0)          |     |                   |   |  (Envío)          |
          |                   |   | (Procesamiento    |     |                   |   |                   |
          |                   |   |  inmediato)       |     |                   |   |                   |
          +-------------------+   +-------------------+     +-------------------+   +-------------------+
                   |                        |                        |                        |
                   v                        v                        v                        v
   +------+   +------+   +------+    +-------------+        +-------------+        +------+   +------+
   |      |   |      |   |      |    |             |        |             |        |      |   |      |
   |Msg   |   |Msg   |...|Msg   |    |Process ECHO |        |File         |        |File  |   |File  |...
   |Worker|   |Worker|   |Worker|    |Directo      |        |Handler      |        |Sender|   |Sender|
   |1...N |   |      |   |      |    |             |        |             |        |1...M |   |      |
   +------+   +------+   +------+    +-------------+        +-------------+        +------+   +------+

                                                   +--------+
                                                   |        |
                                                   | System |
                                                   | Stats  |
                                                   |        |
                                                   +--------+
        +-----------------------------------------------------------------------------------+     
        |                                                                                   |
        |                              Sistema de locks                                     |
        |                                                                                   |
        |  - _peers_lock: Protege la lista de peers conocidos                               |
        |  - _udp_socket_lock: Evita envíos UDP simultáneos                                 |
        |  - _tcp_socket_lock: Protege socket TCP de escucha                                |
        |  - _callback_lock: Protege las notificaciones a callbacks                         |
        |  - _conversation_locks: (por usuario) Garantiza orden en conversaciones           |
        |  - _transfers_lock: Controla número máximo de transferencias concurrentes         |
        |                                                                                   |
        +-----------------------------------------------------------------------------------+
```

El sistema mejorado de concurrencia permite:

1. **Procesamiento optimizado según tipo de operación**:
   - Mensajes ECHO (tipo 0): Procesamiento inmediato para respuesta rápida
   - Mensajes (tipo 1): Procesamiento ordenado a través de workers
   - Archivos (tipo 2): Transferencia concurrente con límite adaptativo

2. **Workers dinámicos según recursos del sistema**:
   - El número de workers se ajusta según la capacidad del sistema
   - Se utilizan diferentes pools para mensajes y archivos

3. **Control de carga y recursos**:
   - Límite adaptativo de transferencias simultáneas
   - Cola específica para envío de archivos
   - Monitoreo del progreso en tiempo real

4. **Estadísticas y monitoreo**:
   - Sistema de estadísticas para supervisar el uso de recursos
   - Notificaciones de progreso para archivos

## Sistema de Seguridad

El protocolo implementa varias capas de verificación:

```
+------------------------------------------+
|                                          |
|  Verificación de Origen                  |
|  +----------------------------------+    |
|  |                                  |    |
|  |  1. Dirección IP                 |    |
|  |  2. Puerto                       |    |
|  |  3. ID de Usuario                |    |
|  |  4. BodyId                       |    |
|  |                                  |    |
|  +----------------------------------+    |
|                                          |
+------------------------------------------+
                   |
                   v
+------------------------------------------+
|                                          |
|  Verificación en Múltiples Puntos        |
|  +----------------------------------+    |
|  |                                  |    |
|  |  1. Recepción de header          |    |
|  |  2. Recepción de cuerpo          |    |
|  |  3. Finalización                 |    |
|  |                                  |    |
|  +----------------------------------+    |
|                                          |
+------------------------------------------+
                   |
                   v
+------------------------------------------+
|                                          |
|  Aislamiento de Conversaciones           |
|  +----------------------------------+    |
|  |                                  |    |
|  |  1. Socket dedicado              |    |
|  |  2. Puerto aleatorio             |    |
|  |  3. Timeout de espera            |    |
|  |  4. Lock por usuario             |    |
|  |                                  |    |
|  +----------------------------------+    |
|                                          |
+------------------------------------------+
```

El sistema garantiza que:

1. **Autenticidad**: Las respuestas provienen realmente del usuario al que se envió el mensaje
2. **Integridad**: Los mensajes no son alterados durante la transmisión
3. **Aislamiento**: Las comunicaciones con diferentes peers no interfieren entre sí
4. **Resistencia a ataques**: Dificulta la suplantación de identidad y ataques de denegación de servicio

Este sistema multicapa de verificaciones permite una comunicación segura dentro de redes locales confiables.

## Optimización de Recursos

```
+------------------------+
|                        |
| Detección de Recursos  |
+------------------------+
           |
           v
+-----------------------------------------------------+
|                                                     |
| Parámetros que se ajustan automáticamente:          |
|                                                     |
| - Número de workers para mensajes                   |
| - Número de workers para transferencias             |
| - Límite de transferencias concurrentes             |
| - Tamaño de buffer para transferencias              |
+-----------------------------------------------------+
           |
           v
+-----------------------------------------------------+
|                                                     |
| Factores considerados:                              |
|                                                     |
| - Sistema operativo (macOS/Linux/Windows)           |
| - Memoria total y disponible                        |
| - Número de CPUs                                    |
| - Carga actual del sistema                          |
+-----------------------------------------------------+
           |
           v
+-----------------------------------------------------+
|                                                     |
| Monitoreo en tiempo real:                           |
|                                                     |
| - Comando "stats" muestra recursos actuales         |
| - Progreso de transferencias de archivos            |
| - Recalcula valores óptimos según carga             |
+-----------------------------------------------------+
```

El sistema implementa optimización dinámica de recursos:

1. **Detección automática de recursos**:
   - Al iniciar, detecta características del sistema
   - Ajusta parámetros según la capacidad disponible

2. **Adaptación a condiciones cambiantes**:
   - Recalcula valores óptimos según la carga actual
   - Reajusta el número de workers recomendado

3. **Monitoreo y transparencia**:
   - Comando `stats` permite ver uso actual de recursos
   - Notificaciones de progreso de transferencias

4. **Equilibrio entre rendimiento y uso de recursos**:
   - En sistemas potentes: maximiza el paralelismo
   - En sistemas limitados: conserva recursos
