FROM python:3.11-slim

# Etiquetas con información del mantenedor
LABEL maintainer="LCP Development Team"
LABEL description="Local Chat Protocol (LCP) Application Container"
LABEL version="1.0"

# Establecer variables de entorno
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Directorio de trabajo
WORKDIR /app

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    net-tools \
    iputils-ping \
    iproute2 \
    && rm -rf /var/lib/apt/lists/*

# Copiar los archivos del proyecto
COPY . /app/

# Crear un volumen para archivos recibidos
VOLUME /app/received_files

# Puerto UDP para el chat (control)
EXPOSE 9990/udp
# Puerto TCP para transferencias de archivos
EXPOSE 9990/tcp

# Comando para ejecutar la aplicación en modo GUI
#ENTRYPOINT ["python", "gui.py"]

# Comando para modo CLI
# Usaremos CMD para permitir que docker-compose lo sobrescriba
ENTRYPOINT ["python"]
CMD ["main.py"]
