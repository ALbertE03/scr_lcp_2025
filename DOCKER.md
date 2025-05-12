# LCP Chat en Docker

Este documento explica cómo ejecutar la aplicación de Local Chat Protocol (LCP) en Docker, lo que facilita las pruebas y la implementación en cualquier plataforma.

## Requisitos previos

- Docker instalado en su sistema
- Para el modo GUI: servidor X (XQuartz en macOS, X11 en Linux)
- Opcional: Docker Compose para pruebas multi-instancia

## Métodos de ejecución

Hay dos scripts disponibles para ejecutar la aplicación:

1. `docker-run.sh` - Para ejecución individual y opciones avanzadas
2. `docker-compose-run.sh` - Para pruebas multi-instancia con 3 nodos

## Opciones del script `docker-run.sh`

```
./docker-run.sh [OPCIÓN]
```

Opciones disponibles:
- `build` - Construir la imagen Docker
- `run` - Ejecutar en modo GUI (requiere configuración X11)
- `run-cli` - Ejecutar en modo consola
- `run-network` - Crear una red de prueba con 3 instancias
- `clean` - Limpiar contenedores e imágenes
- `help` - Mostrar mensaje de ayuda

## Uso con Docker Compose

Para iniciar un entorno de prueba con 3 instancias:

```
./docker-compose-run.sh start
```

Para detener y limpiar:

```
./docker-compose-run.sh clean
```

## Notas técnicas

### Puertos utilizados
- UDP/9990 - Para control y descubrimiento
- TCP/9990 - Para transferencia de archivos

### Broadcast en Docker
La implementación por defecto soporta broadcast en el puerto 9990. Al usar redes Docker personalizadas con `docker-compose`, las instancias podrán descubrirse automáticamente.

## Solución de problemas

### GUI no aparece
Para usar la interfaz gráfica, necesita configurar correctamente el servidor X:

- **En Linux**: Ejecute `xhost +local:docker` antes de iniciar el contenedor
- **En macOS**: Instale XQuartz, configure "Allow connections from network clients" y reinicie XQuartz

### Descubrimiento no funciona
- Asegúrese de que los contenedores estén en la misma red Docker
- El puerto UDP 9990 debe estar abierto entre los contenedores
- Al usar la opción `--network host`, verifique que su firewall no bloquee el puerto 9990

### Archivos no se reciben
Los archivos recibidos se guardan en `/app/received_files` dentro del contenedor. Use volúmenes para acceder a ellos desde su sistema host.
