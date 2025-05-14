#!/bin/bash
# Script para facilitar la construcción y ejecución de la aplicación LCP en Docker

# Colores para mensajes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # Sin color

# Función de ayuda
show_help() {
    echo -e "${YELLOW}LCP Docker Helper Script${NC}"
    echo ""
    echo "Uso: ./docker-run.sh [OPCIÓN]"
    echo ""
    echo "Opciones:"
    echo "  build       - Construir la imagen Docker"
    echo "  run         - Ejecutar el contenedor con GUI (requiere acceso al servidor X)"
    echo "  run-cli     - Ejecutar el contenedor en modo CLI (sin interfaz gráfica)"
    echo "  run-network - Ejecutar múltiples instancias en una red Docker aislada"
    echo "  clean       - Eliminar contenedores e imágenes LCP"
    echo "  help        - Mostrar este mensaje de ayuda"
    echo ""
}

# Verificar si Docker está instalado
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: Docker no está instalado.${NC}"
    exit 1
fi

# Si no hay argumentos, mostrar ayuda
if [ $# -eq 0 ]; then
    show_help
    exit 0
fi

# Procesar comandos
case "$1" in
    build)
        echo -e "${GREEN}Construyendo imagen Docker para LCP...${NC}"
        docker build -t lcp-chat:latest .
        ;;
    run)
        echo -e "${GREEN}Ejecutando LCP en modo GUI...${NC}"
        # Para macOS
        if [ "$(uname)" == "Darwin" ]; then
            # Asegúrate de tener XQuartz instalado y configurado correctamente
            IP=$(ifconfig en0 | grep inet | awk '$1=="inet" {print $2}')
            xhost + $IP
            docker run -it --rm \
                -e DISPLAY=$IP:0 \
                -v /tmp/.X11-unix:/tmp/.X11-unix \
                --name lcp-chat \
                --network host \
                lcp-chat:latest
        else
            # Para Linux
            xhost +local:docker
            docker run -it --rm \
                -e DISPLAY=$DISPLAY \
                -v /tmp/.X11-unix:/tmp/.X11-unix \
                --name lcp-chat \
                --network host \
                lcp-chat:latest
        fi
        ;;
    run-cli)
        echo -e "${GREEN}Ejecutando LCP en modo línea de comandos...${NC}"
        read -p "Ingresa tu nombre de usuario: " USERNAME
        docker run -it --rm \
            --name lcp-chat-cli \
            --network host \
            lcp-chat:latest \
            python main.py "${USERNAME:-DockerUser}"
        ;;
    run-network)
        echo -e "${GREEN}Creando red Docker para pruebas multi-instancia...${NC}"
        docker network create lcp-network 2>/dev/null || true
        
        # Iniciar 3 instancias con nombres diferentes
        echo -e "${GREEN}Iniciando instancia 1 (Usuario1)...${NC}"
        docker run -d --rm \
            --name lcp-chat-1 \
            --network lcp-network \
            lcp-chat:latest \
            python main.py "Usuario1"
        
        echo -e "${GREEN}Iniciando instancia 2 (Usuario2)...${NC}"
        docker run -d --rm \
            --name lcp-chat-2 \
            --network lcp-network \
            lcp-chat:latest \
            python main.py "Usuario2"
        
        echo -e "${GREEN}Iniciando instancia 3 (Usuario3)...${NC}"
        docker run -it --rm \
            --name lcp-chat-3 \
            --network lcp-network \
            lcp-chat:latest \
            python main.py "Usuario3"
        
        # El último contenedor se ejecuta en modo interactivo
        # Cuando este termine, limpiar los otros contenedores
        echo -e "${GREEN}Limpiando contenedores...${NC}"
        docker stop lcp-chat-1 lcp-chat-2 2>/dev/null || true
        ;;
    clean)
        echo -e "${GREEN}Limpiando contenedores LCP...${NC}"
        docker stop $(docker ps -q --filter "name=lcp-chat") 2>/dev/null || true
        docker rm $(docker ps -a -q --filter "name=lcp-chat") 2>/dev/null || true
        
        echo -e "${GREEN}Eliminando red Docker LCP...${NC}"
        docker network rm lcp-network 2>/dev/null || true
        
        echo -e "${YELLOW}¿Deseas eliminar la imagen Docker de LCP? (y/n)${NC}"
        read -r response
        if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
            docker rmi lcp-chat:latest 2>/dev/null || true
        fi
        ;;
    help|*)
        show_help
        ;;
esac

exit 0
