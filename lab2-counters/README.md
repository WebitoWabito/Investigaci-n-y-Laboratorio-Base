# Lab 2 — Contadores y Estadísticas de Tráfico en P4

Sistema de monitoreo de tráfico implementado en el plano de datos usando P4 (BMv2/v1model).


# Estructura de archivos

```
lab2-counters/
  counters.p4           # Programa P4: parsers, tablas, contadores, register
  counters.p4info.txt   # Generado por p4c: info de runtime (tablas/contadores)
  build/
     counters.json      # JSON para BMv2
     counters.p4i       # Salida del preprocesador
  topology.py           # Topología Mininet: 1 switch P4 + 4 hosts
  controller.py         # Controlador Python: instala entradas y lee contadores
  traffic_gen.py        # Generador de tráfico con Scapy e iperf3
  README.md             
```

# Requisitos

* Python  3.8+
* p4c  cualquiera con v1model 
* BMv2 simple_switch  cualquiera
* Mininet  2.3+ 
* Scapy  2.4+ 
* iperf3  3.x 


# Compilar el programa P4

Desde `lab2-counters/`

```bash
p4c --target bmv2 --arch v1model \
    --p4runtime-files counters.p4info.txt \
    -o build \
    counters.p4
```

Verifica que existan `build/counters.json` y `counters.p4info.txt`.

---

# Levantar la topología Mininet

```bash
sudo /home/p4/src/p4dev-python-venv/bin/python3 topology.py
```

Esto arranca:
- 1 switch P4 (`s1`) ejecutando BMv2 con `counters.json`, escuchando en Thrift port 9090.
- 4 hosts:

| Host | IP        | MAC               |
|------|-----------|-------------------|
| h1   | 10.0.0.1  | 00:00:00:00:01:01 |
| h2   | 10.0.0.2  | 00:00:00:00:02:02 |
| h3   | 10.0.0.3  | 00:00:00:00:03:03 |
| h4   | 10.0.0.4  | 00:00:00:00:04:04 |

# Lanzar el controlador

En otra terminal (mientras Mininet está corriendo):

```bash
sudo /home/p4/src/p4dev-python-venv/bin/python3 controller.py
```

El controlador:
1. Instala las entradas en `flow_stats` (todos los pares h1..h4) y en `l2_forward`.
2. Lee los contadores cada 5 segundos e imprime un resumen en consola.

Opciones:
```
--thrift-port 9090    Puerto Thrift del switch (default: 9090)
--interval 5          Segundos entre lecturas (default: 5)
--no-configure        Saltar la configuración inicial
```


# Generar tráfico

# Desde la CLI de Mininet 

mininet> h1 ping h2 -c 5
mininet> h3 ping h4 -c 5
mininet> h1 ping h3 -c 3

mininet> pingall

#Trafico elefante
mininet> h1 ping h2 -c 200 -s 1400

#Tráfico UDP
mininet> h1 python3 -c "import socket; 
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); [s.sendto(b'X'*100,
('10.0.0.2',5001)) for _ in range(50)]"

#Tráfico TCP
mininet> h3 python3 -m http.server 8080 &
mininet> h4 wget -q http://10.0.0.3:8080 -O /dev/null
mininet> h3 pkill -f "http.server"

# Con el script de generación en terminal separada

```bash
# Tráfico básico mixto TCP/UDP/ICMP
sudo python3 traffic_gen.py --mode scapy --scenario basic

# Disparar un flujo elefante (>100 KB) entre h1 y h2
sudo python3 traffic_gen.py --mode scapy --scenario elephant --src h1 --dst h2

# Verificación exacta: 20 paquetes ICMP, compara con controller.py
sudo python3 traffic_gen.py --mode scapy --scenario verify --src h1 --dst h2 --count 20

# Tráfico en volumen con iperf3
sudo python3 traffic_gen.py --mode iperf --scenario elephant --src h1 --dst h2
```


# Salida esperada del controlador

```
──────────────────────────────────────────────────────────────────────
  ESTADÍSTICAS DE TRÁFICO  —  Fecha Hora
──────────────────────────────────────────────────────────────────────

  CONTADORES GLOBALES POR PROTOCOLO
  Protocolo      Paquetes          Bytes
  ---------- ------------ --------------
  TCP                  10          1,400
  UDP                  15          3,750
  ICMP                  8            672
  OTROS                 0              0
  TOTAL                33          5,822

  CONTADORES POR FLUJO  (src → dst)
  Flujo                        Paquetes        Bytes  Estado
  ---------------------------- ---------- ------------  ----------
  h1→h2                               8          672  normal
  h2→h1                               5          700  normal

──────────────────────────────────────────────────────────────────────
```


