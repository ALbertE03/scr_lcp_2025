#!/bin/bash
# Script para ejecutar el entorno de prueba LCP con docker-compose

# Colores para mensajes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # Sin color

# Verificar si docker-compose está instalado
if ! command -v docker-compose &> /dev/null; then
    echo -e "${RED}Error: docker-compose no está instalado.${NC}"
    echo -e "Intenta con: 'pip install docker-compose' o instálalo según tu sistema operativo."
    exit 1
fi

# Función para iniciar el entorno
start_environment() {
    echo -e "${GREEN}Creando directorios para archivos recibidos...${NC}"
    mkdir -p received_files_1 received_files_2 received_files_3
    
    echo -e "${GREEN}Construyendo y levantando contenedores...${NC}"
    docker-compose up --build
}

# Función para limpiar el entorno
clean_environment() {
    echo -e "${GREEN}Deteniendo y eliminando contenedores...${NC}"
    docker-compose down
    
    echo -e "${YELLOW}¿Deseas eliminar las imágenes creadas? (y/n)${NC}"
    read -r response
    if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
        docker rmi $(docker images -q lcp_2025_lcp-node-1) 2>/dev/null || true
    fi
    
    echo -e "${YELLOW}¿Deseas eliminar los directorios de archivos recibidos? (y/n)${NC}"
    read -r response
    if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
        rm -rf received_files_1 received_files_2 received_files_3
    fi
}

# Mostrar ayuda
show_help() {
    echo -e "${YELLOW}Docker Compose Helper para LCP${NC}"
    echo ""
    echo "Uso: ./docker-compose-run.sh [OPCIÓN]"
    echo ""
    echo "Opciones:"
    echo "  start   - Inicia el entorno de prueba con 3 nodos"
    echo "  clean   - Detiene y elimina los contenedores y recursos"
    echo "  help    - Muestra este mensaje de ayuda"
}

# Procesar comandos
case "$1" in
    start)
        start_environment
        ;;
    clean)
        clean_environment
        ;;
    help|*)
        show_help
        ;;
esac

exit 0
