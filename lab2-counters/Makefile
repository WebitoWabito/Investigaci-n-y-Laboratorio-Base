# Uso rápido:
#   make          → compila el P4
#   make run      → levanta Mininet (requiere sudo)
#   make control  → lanza el controlador Python
#   make traffic  → genera tráfico básico con Scapy
#   make elephant → genera un flujo elefante
#   make clean    → borra artefactos de compilación

P4_SRC    = counters.p4
P4_INFO   = counters.p4info.txt
BUILD_DIR = build

.PHONY: all compile run control traffic elephant clean help

## Objetivo por defecto: compilar
all: compile

## Compilar el programa P4 con p4c para BMv2
compile:
	@echo "=== Compilando $(P4_SRC) ==="
	p4c --target bmv2 --arch v1model \
	    --p4runtime-files $(P4_INFO) \
	    -o $(BUILD_DIR) \
	    $(P4_SRC)
	@echo "=== Compilación exitosa ==="
	@ls -lh $(BUILD_DIR)/

## Levantar la topología Mininet (requiere sudo)
run:
	@echo "=== Iniciando topología Mininet ==="
	sudo python3 topology.py

## Lanzar el controlador de contadores
control:
	@echo "=== Iniciando controlador (Ctrl+C para salir) ==="
	python3 controller.py

## Generar tráfico básico mixto con Scapy
traffic:
	@echo "=== Generando tráfico básico ==="
	sudo python3 traffic_gen.py --mode scapy --scenario basic

## Generar flujo elefante entre h1 y h2
elephant:
	@echo "=== Generando flujo elefante h1→h2 ==="
	sudo python3 traffic_gen.py --mode scapy --scenario elephant --src h1 --dst h2

## Verificación exacta: 20 paquetes ICMP
verify:
	@echo "=== Verificación de contadores: 20 paquetes ICMP h1→h2 ==="
	sudo python3 traffic_gen.py --mode scapy --scenario verify \
	    --src h1 --dst h2 --count 20

## Limpiar artefactos de compilación
clean:
	@echo "=== Limpiando artefactos ==="
	rm -rf $(BUILD_DIR) $(P4_INFO)
	@echo "=== Listo ==="

## Ayuda
help:
	@echo ""
	@echo "Targets disponibles:"
	@echo "  make           → compilar counters.p4"
	@echo "  make run       → levantar Mininet (sudo)"
	@echo "  make control   → lanzar controlador Python"
	@echo "  make traffic   → tráfico básico (sudo)"
	@echo "  make elephant  → flujo elefante h1→h2 (sudo)"
	@echo "  make verify    → 20 paquetes ICMP exactos (sudo)"
	@echo "  make clean     → borrar build/ y .p4info"
	@echo ""
