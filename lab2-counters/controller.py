#!/usr/bin/env python3
"""
controller.py — Lab 2: Controlador de Contadores P4

  1. Configuración inicial:
       - Instala las entradas en la tabla flow_stats con los flujos a monitorear
         (pares IP_origen → IP_destino entre los 4 hosts).
       - Instala las entradas en la tabla l2_forward para el "bump in the wire"
         (puerto 1-2, 3-4, etc.).

  2. Lectura periódica:
       - Lee los contadores globales de protocolo (TCP/UDP/ICMP/OTROS).
       - Lee el direct_counter de cada flujo instalado.
       - Lee el register de bytes acumulados para detectar flujos elefante.
       - Imprime el resumen en consola con formato legible.

Comunicación con el switch:
    Se usa simple_switch_CLI (el binario de línea de comandos de BMv2) a través
    de subprocess.

Uso:
    sudo /home/p4/src/p4dev-python-venv/bin/python3 controller.py

"""

import argparse
import subprocess
import sys
import time
import re
import ipaddress
from datetime import datetime

#Configuración default
DEFAULT_THRIFT_PORT = 9090
DEFAULT_INTERVAL    = 5 #Intervalo de segundos entre lecturas

#Umbral de bytes para reportar flujo elefante
ELEPHANT_THRESHOLD = 100_000

# Flujos a monitorear: todos los pares (src, dst) entre los 4 hosts.
HOSTS = {
    "h1": "10.0.0.1",
    "h2": "10.0.0.2",
    "h3": "10.0.0.3",
    "h4": "10.0.0.4",
}

# Asignación de índices de flujo en orden determinista para que el flow_index
# que se instala en flow_stats coincida con el que se lee del register.
# Se generan todos los pares (src, dst) con src != dst.
FLOWS = []
_idx = 0
for _src_name, _src_ip in sorted(HOSTS.items()):
    for _dst_name, _dst_ip in sorted(HOSTS.items()):
        if _src_name != _dst_name:
            FLOWS.append({
                "index":    _idx,
                "src_name": _src_name,
                "src_ip":   _src_ip,
                "dst_name": _dst_name,
                "dst_ip":   _dst_ip,
            })
            _idx += 1

#Número de puertos activos en el switch
NUM_PORTS = 4

#Etiquetas de los índices del counter de protocolo
PROTO_LABELS = {0: "TCP", 1: "UDP", 2: "ICMP", 3: "OTROS"}


#Función auxiliar para ejecutar un bloque de comandos en simple_switch_CLI
def _cli(thrift_port: int, commands: list[str]) -> str:
    """
    Ejecuta una lista de comandos en simple_switch_CLI y devuelve la salida.
    Lanza RuntimeError si el proceso termina con código distinto de 0.
    """
    cmd_str = "\n".join(commands) + "\n"
    result = subprocess.run(
        ["simple_switch_CLI", "--thrift-port", str(thrift_port)],
        input=cmd_str,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if "Error" in result.stdout or result.returncode != 0:
        combined = result.stdout + result.stderr
        #Ignorar errores de "entry already exists" al reinstalar entradas
        non_trivial = [
            ln for ln in combined.splitlines()
            if "Error" in ln and "ALREADY_EXISTS" not in ln
        ]
        if non_trivial:
            raise RuntimeError(
                f"simple_switch_CLI error:\n" + "\n".join(non_trivial)
            )
    return result.stdout


#Configuración inicial del switch
def configure_switch(thrift_port: int):
    """
    Instala entradas estáticas en flow_stats y l2_forward.
    """
    commands = []
    time.sleep(3)

    #Tabla l2_forward: MAC destino - puerto de salida
    mac_to_port = {
        "00:00:00:00:01:01": 1,
        "00:00:00:00:02:02": 2,
        "00:00:00:00:03:03": 3,
        "00:00:00:00:04:04": 4,
    }
    for mac, port in mac_to_port.items():
        commands.append(
            f"table_add l2_forward forward {mac} => {port}"
        )

    #Tabla flow_stats con un flujo por cada par (src_ip, dst_ip)
    for flow in FLOWS:
        commands.append(
            f"table_add flow_stats count_flow "
            f"{flow['src_ip']} {flow['dst_ip']} => {flow['index']}"
        )

    try:
        _cli(thrift_port, commands)
        print(f"Switch configurado: {len(FLOWS)} flujos instalados, "
              f"{NUM_PORTS} entradas de reenvío.")
    except RuntimeError as exc:
        print(f"Configuración parcial: {exc}", file=sys.stderr)


#Lectura de contadores de protocolo
def read_protocol_counters(thrift_port: int) -> dict:
    commands = [
        f"counter_read protocol_counter {idx}"
        for idx in range(len(PROTO_LABELS))
    ]
    output = _cli(thrift_port, commands)

    # Formato BMv2, protocol_counter[0]= (1234 bytes, 56 packets)
    pattern = re.compile(r"protocol_counter\[\d+\]=\s*\((\d+) bytes,\s*(\d+) packets\)")
    matches = pattern.findall(output)

    result = {}
    for idx, (bts, pkts) in enumerate(matches):
        label = PROTO_LABELS.get(idx, f"IDX_{idx}")
        result[label] = {"packets": int(pkts), "bytes": int(bts)}
    return result


#Lectura del direct_counter de flujos
def read_flow_counters(thrift_port: int) -> list[dict]:
    commands = [
        f"counter_read flow_counter {flow['index']}"
        for flow in FLOWS
    ]
    output = _cli(thrift_port, commands)

    #Formato BMv2, direct counter flow_counter[0]= (1234 bytes, 56 packets)
    pattern = re.compile(r"flow_counter\[\d+\]=\s*\((\d+) bytes,\s*(\d+) packets\)")
    matches = pattern.findall(output)

    result = []
    for flow, (bts, pkts) in zip(FLOWS, matches):
        result.append({
            **flow,
            "packets": int(pkts),
            "bytes":   int(bts),
        })
    return result


#Lectura del register de bytes acumulados (detección de elefante)
def read_elephant_register(thrift_port: int) -> list[dict]:
    """
    Lee el register flow_byte_accum para cada flujo conocido.
    Devuelve lista de dicts: {index, src_ip, dst_ip, accum_bytes, is_elephant}.
    """
    commands = [
        f"register_read flow_byte_accum {flow['index']}"
        for flow in FLOWS
    ]
    output = _cli(thrift_port, commands)

    # Salida esperada: "flow_byte_accum[0]= 0"
    pattern = re.compile(r"flow_byte_accum\[\d+\]=\s*(\d+)")
    matches = [int(v) for v in pattern.findall(output)]

    result = []
    for flow, accum in zip(FLOWS, matches):
        result.append({
            "index":       flow["index"],
            "src_ip":      flow["src_ip"],
            "dst_ip":      flow["dst_ip"],
            "src_name":    flow["src_name"],
            "dst_name":    flow["dst_name"],
            "accum_bytes": accum,
            "is_elephant": accum > ELEPHANT_THRESHOLD,
        })
    return result


#Impresión en consola
def print_stats(proto_counters: dict,
                flow_counters: list[dict],
                elephant_data: list[dict]):
    """Imprime las estadísticas en un formato legible"""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sep = "─" * 70

    print(f"\n{sep}")
    print(f" ESTADÍSTICAS DE TRÁFICO — {ts}")
    print(sep)

    #Contadores globales por protocolo 
    print("\n  CONTADORES GLOBALES POR PROTOCOLO")
    print(f"  {'Protocolo':<10} {'Paquetes':>12} {'Bytes':>14}")
    print(f"  {'-'*10} {'-'*12} {'-'*14}")
    total_pkts = total_bytes = 0
    for proto, vals in proto_counters.items():
        p, b = vals["packets"], vals["bytes"]
        print(f"  {proto:<10} {p:>12,} {b:>14,}")
        total_pkts  += p
        total_bytes += b
    print(f"  {'TOTAL':<10} {total_pkts:>12,} {total_bytes:>14,}")

    #Contadores por flujo
    print("\n  CONTADORES POR FLUJO  (src → dst)")
    print(f"  {'Flujo':<28} {'Paquetes':>10} {'Bytes':>12}  Estado")
    print(f"  {'-'*28} {'-'*10} {'-'*12}  {'-'*10}")

    #Crear mapa de bytes acumulados del register para cada flujo
    eleph_map = {(e["src_ip"], e["dst_ip"]): e for e in elephant_data}

    active_flows = [f for f in flow_counters if f["packets"] > 0]
    if not active_flows:
        print("  (sin tráfico aún)")
    else:
        for f in active_flows:
            label  = f"{f['src_name']}→{f['dst_name']}"
            edata  = eleph_map.get((f["src_ip"], f["dst_ip"]), {})
            accum  = edata.get("accum_bytes", f["bytes"])
            status = "ELEFANTE" if edata.get("is_elephant") else "normal"
            print(f"  {label:<28} {f['packets']:>10,} {f['bytes']:>12,}  {status}")

    #Flujos elefante
    elephants = [e for e in elephant_data if e["is_elephant"]]
    if elephants:
        print(f"\n FLUJOS ELEFANTE  (> {ELEPHANT_THRESHOLD:,} bytes acumulados)")
        print(f"  {'Flujo':<28} {'Bytes acum.':>14}")
        print(f"  {'-'*28} {'-'*14}")
        for e in elephants:
            label = f"{e['src_name']}({e['src_ip']}) → {e['dst_name']}({e['dst_ip']})"
            print(f"  {label:<40} {e['accum_bytes']:>14,}")

    print(f"\n{sep}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Controlador de contadores P4 — Lab 2"
    )
    parser.add_argument(
        "--thrift-port", type=int, default=DEFAULT_THRIFT_PORT,
        help=f"Puerto Thrift del switch BMv2 (default: {DEFAULT_THRIFT_PORT})"
    )
    parser.add_argument(
        "--interval", type=float, default=DEFAULT_INTERVAL,
        help=f"Intervalo de lectura en segundos (default: {DEFAULT_INTERVAL})"
    )
    parser.add_argument(
        "--no-configure", action="store_true",
        help="Omitir la configuración inicial si instalada"
    )
    args = parser.parse_args()

    print("=" * 70)
    print("  Controlador P4 — Lab 2: Contadores y Estadísticas de Tráfico")
    print("=" * 70)
    print(f"  Thrift port : {args.thrift_port}")
    print(f"  Intervalo   : {args.interval}s")
    print(f"  Flujos mon. : {len(FLOWS)}")
    print(f"  Umbral elef.: {ELEPHANT_THRESHOLD:,} bytes")
    print("=" * 70)

    #Configuración inicial
    if not args.no_configure:
        print("\nInstalando entradas en el switch...")
        configure_switch(args.thrift_port)

    #Lectura periódica
    print(f"\nIniciando lectura periódica cada {args.interval}s "
          f"(Ctrl+C para salir)\n")
    try:
        while True:
            try:
                proto    = read_protocol_counters(args.thrift_port)
                flows    = read_flow_counters(args.thrift_port)
                elephants = read_elephant_register(args.thrift_port)
                print_stats(proto, flows, elephants)
            except RuntimeError as exc:
                print(f"Error - No se pudo leer del switch: {exc}",
                      file=sys.stderr)
            except FileNotFoundError:
                sys.exit(
                    "Error - simple_switch_CLI no encontrado en PATH.\n"
                    "Verificar que BMv2 esté instalado correctamente."
                )
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nControlador detenido por el usuario.")


if __name__ == "__main__":
    main()
