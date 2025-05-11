# LCP (Local Chat Protocol) - Flujo Detallado

## Índice

- [Arquitectura](#arquitectura)
- [Flujo del Protocolo](#flujo-del-protocolo)
  - [Inicialización](#inicialización)
  - [Autodescubrimiento](#autodescubrimiento)
  - [Envío de Mensajes](#envío-de-mensajes)
  - [Recepción de Mensajes](#recepción-de-mensajes)
  - [Mensajes Broadcast](#mensajes-broadcast)
  - [Transferencia de Archivos](#transferencia-de-archivos)
- [Manejo de Concurrencia](#manejo-de-concurrencia)
- [Sistema de Seguridad](#sistema-de-seguridad)
- [Optimización de Recursos](#optimización-de-recursos)
- [Detalles de Implementación](#detalles-de-implementación)
  - [Formato de Paquetes](#formato-de-paquetes)
  - [Manejo de Errores](#manejo-de-errores)
  - [Persistencia](#persistencia)

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

No hay servidores centrales ni coordinadores, cada peer mantiene su propia lista de pares conocidos y gestiona sus propias comunicaciones de manera autónoma. Esta arquitectura proporciona gran resistencia a fallos ya que no existe un punto único de fallo.

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

El proceso de inicialización incluye los siguientes pasos detallados:

1. **Especificación del ID**: Cada peer recibe un identificador único de hasta 20 caracteres (rellenado con espacios si es más corto)

2. **Detección de recursos disponibles**:
   - **CPU**: Se detecta el número de núcleos lógicos disponibles mediante `multiprocessing.cpu_count()`
   - **Memoria**: Se mide la memoria total y disponible de forma específica para cada sistema operativo
   - **Carga del sistema**: Se obtiene la carga actual para adaptar el uso de recursos

3. **Configuración de sockets**:
   - **Socket UDP**: Configurado en modo broadcast en el puerto 9990 con `setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)`
   - **Socket TCP**: Configurado para escuchar en el puerto 9990 con un backlog de 5 conexiones

4. **Inicialización de estructuras de control**:
   - **Peers**: Diccionario `{user_id: (ip_address, last_seen_datetime)}` para mantener el registro de pares
   - **Locks**: Sistema de locks para controlar concurrencia en recursos compartidos
   - **Colas**: Sistema de colas para mensajes y transferencia de archivos
   - **Callbacks**: Registro de funciones para notificar eventos (mensajes, archivos, descubrimientos, progreso)

5. **Arranque de hilos de servicio**:
   - **UDP Listener**: Escucha continuamente en el puerto UDP 9990
   - **TCP Listener**: Escucha continuamente conexiones TCP en el puerto 9990
   - **Discovery Service**: Envía y procesa mensajes Echo-Reply periódicamente
   - **Message Workers**: Pool de hilos para procesar mensajes entrantes (operación 1)
   - **File Workers**: Pool de hilos para manejar transferencia de archivos (operación 2)

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

El protocolo de autodescubrimiento implementa estos detalles específicos:

1. **Formato exacto del mensaje Echo**:
   - Header de 100 bytes con `OperationCode = 0`
   - `UserIdTo` establecido a `0xFF` repetido 20 veces (broadcast)
   - Los campos `BodyId` y `BodyLength` se ignoran en este tipo de operación
   - Enviado a la dirección broadcast de cada interfaz activa

2. **Procesamiento de respuestas**:
   - Respuestas de exactamente 25 bytes
   - Primer byte = código de estado (0 = OK)
   - Bytes 1-21 = ID del usuario que responde
   - Se utiliza un timeout de 5 segundos para recibir respuestas

3. **Mantenimiento automático de peers**:
   - Cada peer detectado se guarda con su dirección IP y timestamp
   - Se eliminan peers sin actividad después de 90 segundos
   - Se notifica a las aplicaciones de cambios en la lista de peers mediante callbacks

4. **Optimización para respuesta rápida**:
   - Los mensajes ECHO se procesan de forma inmediata (sin encolamiento)
   - Se utiliza un hilo dedicado para el servicio de descubrimiento
   - Las respuestas se envían inmediatamente para minimizar latencia

### Envío de Mensajes

```
     PEER A                                      PEER B
     -------                                     -------
       |                                           |
       |    [1. HEADER (100 bytes)]                |
       +------------------------------------------>|
       |           Operation = 1 (MESSAGE)         |
       |           BodyId = unique_message_id      |
       |           BodyLength = message_size       |
       |                                           |
       |                                          [Verificación de destino]
       |                                          [Verificación de formato]
       |                                           |
       |    [2. RESPONSE OK (25 bytes)]            |
       |<------------------------------------------+
       |                                           |
       |                                           |
       |    [3. BODY (8+N bytes)]                  |
       +------------------------------------------>|
       |     [8 bytes: BodyId]                     |
       |     [N bytes: message_content (UTF-8)]    |
       |                                           |
       |                                          [Verificación de BodyId]
       |                                          [Verificación de tamaño]
       |                                          [Decodificación UTF-8]
       |                                           |
       |    [4. RESPONSE OK (25 bytes)]            |
       |<------------------------------------------+
```

El protocolo de mensajes incluye estos detalles de implementación:

1. **Generación del BodyId**:
   - Se genera un ID único para cada mensaje (0-255) usando `int(time.time() * 1000) % 256`
   - Se verifica que coincida exactamente en cada fase de la comunicación

2. **Estructura del Header (100 bytes)**:
   - Bytes 0-19: ID del remitente (rellenado con espacios)
   - Bytes 20-39: ID del destinatario (rellenado con espacios)
   - Byte 40: Código de operación (1 = MESSAGE)
   - Byte 41: BodyId
   - Bytes 42-49: Tamaño del mensaje en bytes (big-endian)
   - Bytes 50-99: Reservados (rellenos con 0)

3. **Estructura de la respuesta (25 bytes)**:
   - Byte 0: Código de estado (0 = OK, 1 = Bad Request, 2 = Internal Error)
   - Bytes 1-20: ID del usuario que responde
   - Bytes 21-24: Reservados (rellenos con 0)

4. **Estructura del cuerpo del mensaje**:
   - Primeros 8 bytes: BodyId (debe coincidir con el byte 41 del header)
   - Resto de bytes: Contenido del mensaje codificado en UTF-8

5. **Verificaciones estrictas**:
   - Verificación del destinatario correcto
   - Verificación de que el BodyId coincide exactamente
   - Verificación de que el tamaño del mensaje coincide con lo declarado
   - Verificación de que el mensaje puede decodificarse como UTF-8 válido

6. **Control de concurrencia**:
   - Uso de locks específicos por conversación para garantizar orden
   - Socket dedicado para cada operación de mensaje

### Recepción de Mensajes

```
     PEER A                                      PEER B
     -------                                     -------
       |                                           |
       |                       [HEADER]            |
       |<------------------------------------------+
       |                                           |
      [Verificación del destino]                   |
      [Verificación del formato]                   |
       |                                           |
       |                       [RESPONSE OK]       |
       +------------------------------------------>|
       |                                           |
       |                       [BODY]              |
       |<------------------------------------------+
       |                                           |
      [Verificación de BodyId]                     |
      [Verificación de tamaño]                     |
      [Decodificación UTF-8]                       |
      [Notificación a callbacks]                   |
       |                                           |
       |                       [RESPONSE OK]       |
       +------------------------------------------>|
```

La recepción de mensajes implementa los siguientes detalles técnicos:

1. **Procesamiento del header**:
   - Recibido en el puerto UDP 9990
   - Parseado con `_parse_header()` para extraer todos los campos
   - Verificación de destino: comprueba que el mensaje está dirigido a este usuario o es un broadcast
   - Encolamiento en la `message_queue` para procesamiento por workers

2. **Procesamiento del cuerpo en worker**:
   - Se crea un socket dedicado con puerto efímero
   - Se envía respuesta OK (25 bytes) al remitente con `_send_response()`
   - Se espera hasta 5 segundos para recibir el cuerpo del mensaje
   - Se extrae el BodyId de los primeros 8 bytes y se verifica
   - Se verifica que el tamaño coincide con lo especificado en el header
   - Se decodifica el mensaje de UTF-8

3. **Notificación y respuesta final**:
   - Se notifica a los callbacks registrados con `message_callbacks`
   - Se envía respuesta final OK (25 bytes) con `_send_response()`
   - Se libera el socket y recursos asociados

4. **Gestión de errores**:
   - Si el formato es incorrecto: respuesta con `RESPONSE_BAD_REQUEST`
   - Si el destinatario es incorrecto: respuesta con `RESPONSE_BAD_REQUEST`
   - Si hay timeout esperando el cuerpo: respuesta con `RESPONSE_INTERNAL_ERROR`
   - Si hay error de decodificación: respuesta con `RESPONSE_BAD_REQUEST`

### Mensajes Broadcast

```
     PEER A                                        PEERS B, C, D, ...
     -------                                       ------------------
       |                                                   |
       |    [1. HEADER BROADCAST (100 bytes)]              |
       +---------------------------------------------------->
       |            Operation = 1 (MESSAGE)                |
       |            UserIdTo = NULL (Broadcast)            |
       |            BodyId = unique_message_id             |
       |            BodyLength = message_size              |
       |                                                   |
       |                                         [PEER B, C, D procesan el header]
       |                                                   |
       |    [2. BODY BROADCAST (8+N bytes)]                |
       +---------------------------------------------------->
       |     [8 bytes: BodyId]                             |
       |     [N bytes: message_content (UTF-8)]            |
       |                                                   |
       |                                         [PEER B, C, D procesan el mensaje]
       |                                         [Notificación a callbacks]
```

El protocolo de mensajes broadcast tiene las siguientes características:

1. **Diferencia con mensajes punto a punto**:
   - Usa el mismo `OperationCode = 1 (MESSAGE)` que los mensajes regulares
   - Campo `UserIdTo` establecido a `NULL` (rellenado con espacios) para indicar broadcast
   - No requiere respuestas de confirmación de los destinatarios
   - Envía una única transmisión para todos los peers en lugar de transmisiones individuales

2. **Implementación detallada de envío**:
   - Generación de `BodyId` único usando `int(time.time() * 1000) % 256`
   - Envío del header a todas las direcciones de broadcast detectadas mediante `get_network_info()`
   - Codificación del mensaje en UTF-8 antes de la transmisión
   - Protección del socket UDP con `_udp_socket_lock` durante los envíos

3. **Secuencia estricta de envío**:
   - Fase 1: Envío del header broadcast a todas las interfaces de red
   - Fase 2: Envío del cuerpo del mensaje broadcast a las mismas interfaces
   - Serialización completa del proceso para evitar interferencias

4. **Manejo de errores**:
   - Verificación de éxito (`success`) en el envío a al menos una interfaz
   - Captura y registro de excepciones por cada interfaz de broadcast
   - Mantenimiento de consistencia del socket UDP mediante restablecimiento del timeout

5. **Integración con el sistema multi-hilo**:
   - Los receptores procesan el mensaje broadcast en el mismo flujo que los mensajes normales
   - El mensaje broadcast es identificado por el campo `UserIdTo` vacío o nulo
   - Cada receptor encola el mensaje recibido para procesamiento asíncrono
   - Los workers de mensajes manejan tanto mensajes punto a punto como broadcast

6. **Feedback y confirmaciones**:
   - A diferencia de los mensajes punto a punto, el remitente NO recibe confirmaciones de quién recibió el mensaje
   - El remitente no puede saber cuántos o cuáles peers específicos recibieron el mensaje
   - Los receptores simplemente procesan el mensaje y notifican a sus callbacks registrados
   - El remitente solo sabe si el mensaje se envió correctamente a la red, no si algún peer lo recibió

7. **Optimización para redes locales**:
   - Utiliza los mecanismos nativos de broadcast de la red local
   - Evita sobrecarga de red al enviar una única transmisión en lugar de N individuales
   - Permite comunicaciones eficientes uno-a-muchos sin coordinación central

### Transferencia de Archivos

```
     PEER A                                      PEER B
     -------                                     -------
       |                                           |
       | [1. Encolar archivo para envío]           |
       | file_send_queue.put(task)                 |
       |                                           |
       | [2. FileSender toma archivo de la cola]   |
       |                                           |
       |    [3. HEADER UDP (100 bytes)]            |
       +------------------------------------------>|
       |           Operation = 2 (FILE)            |
       |           BodyId = file_id                |
       |           BodyLength = file_size          |
       |                                           |
       |                                          [Verificación del destino]
       |                                          [Almacena file_id esperado]
       |                                           |
       |    [4. RESPONSE OK (25 bytes)]            |
       |<------------------------------------------+
       |                                           |
       |                                           |
       |    [5. TCP CONNECTION                     |
       |        to IP:9990]                        |
       +==========================================>|
       |                                           |
       |    [6. FILE ID (8 bytes)]                 |
       +------------------------------------------>|
       |        [exact BodyId from header]         |
       |                                          [Verifica match con ID esperado]
       |                                           |
       |    [7. FILE DATA (raw bytes)]             |
       +------------------------------------------>|
       |        [Notificación de progreso]         |
       |        [0%, 25%, 50%, 75%, 100%]          |
       |                                          [Guardado en archivo temporal]
       |                                          [Verificación de tamaño]
       |                                           |
       |    [8. RESPONSE OK (25 bytes)]            |
       |<------------------------------------------+
       |                                           |
       |    [9. CLOSE CONNECTION]                  |
       +==========================================X|
       |                                           |
       | [10. FileSender libera recurso]           |
       |    [Notificación de finalización]         |
       |    [Decremento contador transferencias]   |
```

La transferencia de archivos sigue estos detalles específicos:

1. **Encolamiento de archivos**:
   - La aplicación llama a `send_file(user_to, file_path)`
   - La tarea se encola en `file_send_queue`
   - Se verifica previamente que el archivo existe y el destinatario es conocido

2. **Control de transferencias concurrentes**:
   - Se mantiene un contador `active_file_transfers` protegido por `_transfers_lock`
   - Si se alcanza `max_concurrent_transfers`, la tarea se vuelve a encolar
   - El número máximo de transferencias se adapta según los recursos disponibles

3. **Fase de control UDP (específica del protocolo LCP)**:
   - Envío de header (100 bytes) con `Operation = 2 (FILE)`
   - `BodyId` único para identificar la transferencia
   - `BodyLength` con el tamaño exacto del archivo en bytes
   - Recepción de respuesta OK (25 bytes)

4. **Registro de transferencias esperadas** (importante para seguridad):
   - El receptor almacena en `_expected_file_transfers[peer_ip]` la información:

     ```python
     {
       'body_id': expected_file_id,  # ID que debe coincidir en la conexión TCP
       'file_size': file_size,        # Tamaño esperado en bytes
       'user_from': user_from,        # ID del remitente
       'timestamp': time.time()       # Momento en que se registró
     }
     ```

5. **Fase de transferencia TCP**:
   - Conexión TCP al puerto 9990 del destinatario
   - Envío inicial de 8 bytes con el file_id (debe coincidir con el BodyId del header UDP)
   - Verificación en el receptor de que el ID coincide con el esperado en `_expected_file_transfers`
   - Envío del contenido del archivo en chunks de 4096 bytes
   - Notificación de progreso a intervalos regulares (0-100%)

6. **Verificaciones de seguridad**:
   - Verificación de IP de origen
   - Verificación de ID del archivo (debe coincidir UDP y TCP)
   - Verificación de tamaño del archivo
   - Rechazo de transferencias no autorizadas (sin header UDP previo)

7. **Finalización y limpieza**:
   - Verificación final del tamaño del archivo recibido
   - Eliminación de la información de transferencia esperada
   - Notificación a los callbacks registrados
   - Envío de respuesta final OK (25 bytes)
   - Cierre de la conexión TCP
   - Decremento del contador de transferencias activas

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

El diseño de concurrencia incluye estos detalles específicos:

1. **Modelo de hilos específico**:
   - **Threads principales**: UDP-Listener, TCP-Listener, Discovery, Message Workers, File Workers
   - **Threads por demanda**: UDPHandler (para cada mensaje), FileHandler (para cada transferencia)
   - Todos los hilos se crean como `daemon=True` para terminación automática

2. **Sistema de colas**:
   - `message_queue`: Cola para mensajes y solicitudes de archivos (operaciones 1 y 2)
   - `file_send_queue`: Cola específica para envíos de archivos

3. **Sistema de locks precisos**:
   - **_peers_lock**: Protege acceso a la lista `self.peers` y `_expected_file_transfers`
   - **_udp_socket_lock**: Serializa acceso al socket UDP para envío y recepción
   - **_tcp_socket_lock**: Protege socket TCP de escucha
   - **_callback_lock**: Garantiza ejecución exclusiva de callbacks
   - **_conversation_locks**: Diccionario de locks específicos por usuario para ordenar conversaciones
   - **_transfers_lock**: Protege contador de transferencias activas

4. **Diseño de pools dinámicos**:
   - Número de workers para mensajes: ajustado según CPUs y carga del sistema
   - Número de workers para archivos: optimizado para E/S
   - Límite de transferencias concurrentes: adaptativo según recursos disponibles

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

El sistema de seguridad incluye las siguientes implementaciones específicas:

1. **Verificación de identidad en múltiples niveles**:
   - Verificación de IP origen en mensajes UDP y conexiones TCP
   - Verificación de UserID en respuestas
   - Verificación de BodyId entre header y cuerpo
   - Verificación de tamaño y formato

2. **Protecciones específicas para archivos**:
   - Registro explícito de transferencias esperadas con `_expected_file_transfers`
   - Rechazo de conexiones TCP no autorizadas (sin header UDP previo)
   - Verificación obligatoria del ID del archivo (primeros 8 bytes)
   - Verificación de tamaño final del archivo recibido

3. **Protecciones contra ataques de denegación de servicio**:
   - Limitación de transferencias concurrentes basada en recursos
   - Timeouts para todas las operaciones (5 segundos para UDP, adaptativo para TCP)
   - Limpieza automática de peers inactivos y recursos no utilizados

4. **Aislamiento de conversaciones**:
   - Socket dedicado por conversación
   - Puerto aleatorio para recepción de mensajes
   - Lock específico por usuario para garantizar orden y consistencia
   - Conversaciones independientes sin interferencias

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

El sistema de optimización de recursos incluye estas implementaciones específicas:

1. **Detección específica por sistema operativo**:
   - **macOS**: Usa `sysctl` para CPU y `vm_stat` para memoria
   - **Linux**: Lee `/proc/meminfo` y `/proc/loadavg`
   - **Windows**: Usa `ctypes` y `GlobalMemoryStatusEx`

2. **Fórmulas precisas de optimización**:
   - Factor de carga: `max(0.5, min(1.0, 1.0 - (system_load / cpu_count / 2)))`
   - Factor de memoria: `max(0.5, min(1.5, (memory_available / memory_total) * 2))`
   - Workers para mensajes: `max(5, int(cpu_count * load_factor * memory_factor * 3.0))`
   - Workers para archivos: `max(3, int(cpu_count * load_factor * memory_factor * 1.5))`
   - Transferencias concurrentes: `max(4, int(cpu_count * load_factor * memory_factor * 2.0))`

3. **Ajustes específicos por plataforma**:
   - Factor 1.2x para mensajes en macOS
   - Factor 1.1x para archivos en macOS
   - Límites máximos de 40 workers para mensajes, 20 para archivos, 25 transferencias

4. **Monitoreo en tiempo real**:
   - Comando `stats` muestra estado actual de recursos
   - Incluye memoria disponible en GB y porcentaje
   - Muestra número óptimo de workers según la carga actual
   - Muestra uso de colas y transferencias activas

## Detalles de Implementación

### Formato de Paquetes

1. **Header LCP (100 bytes)**:

   ```
   +-------------+--------------+---------------+----------+----------------+--------------+
   | UserIdFrom  | UserIdTo     | OperationCode | BodyId   | BodyLength     | Reserved     |
   | (20 bytes)  | (20 bytes)   | (1 byte)      | (1 byte) | (8 bytes)      | (50 bytes)   |
   +-------------+--------------+---------------+----------+----------------+--------------+
   ```

2. **Respuesta LCP (25 bytes)**:

   ```
   +----------------+----------------+-----------------+
   | ResponseStatus | ResponseId     | Reserved        |
   | (1 byte)       | (20 bytes)     | (4 bytes)       |
   +----------------+----------------+-----------------+
   ```

3. **Mensaje (cuerpo)**:

   ```
   +----------+-----------------------+
   | BodyId   | MessageContent        |
   | (8 bytes)| (BodyLength bytes)    |
   +----------+-----------------------+
   ```

4. **Archivo (TCP)**:

   ```
   +----------+-------------------+
   | FileId   | FileContent       |
   | (8 bytes)| (BodyLength bytes)|
   +----------+-------------------+
   ```

### Manejo de Errores

1. **Códigos de estado específicos**:
   - `RESPONSE_OK = 0`: Operación exitosa
   - `RESPONSE_BAD_REQUEST = 1`: Error en los datos enviados
   - `RESPONSE_INTERNAL_ERROR = 2`: Error interno del receptor

2. **Mecanismos de recuperación**:
   - Timeouts configurados en 5 segundos para operaciones UDP
   - Timeouts adaptables para transferencias TCP
   - Reintentos automáticos para mensajes de descubrimiento
   - Limpieza de recursos en caso de fallo

3. **Logging detallado**:
   - Registro detallado de eventos con niveles de severidad
   - Inclusión de nombre del hilo en logs para facilitar depuración
   - Logs de tiempo de procesamiento para operaciones
   - Registro de progresos de transferencia

### Persistencia

1. **Gestión de archivos temporales**:
   - Formato de nombre: `lcp_file_{timestamp}_{peer_id}.dat`
   - Almacenamiento temporal hasta notificación a la aplicación
   - Verificación de integridad mediante tamaño

2. **Persistencia de peers**:
   - En memoria con formato `{user_id: (ip_address, last_seen_datetime)}`
   - Actualización automática en cada interacción
   - Limpieza automática de peers inactivos (>90 segundos)

3. **Notificaciones a la aplicación**:
   - Sistema de callbacks para mensajes recibidos
   - Sistema de callbacks para archivos recibidos
   - Sistema de callbacks para cambios en peers
   - Sistema de callbacks para progreso de transferencias
