#!/usr/bin/env python3
"""
traffic_gen.py — Lab2: Generación de Tráfico

Genera tráfico de prueba mixto (TCP/UDP/ICMP) entre los 4 hosts de la
topología para verificar que los contadores P4 reflejan fielmente el
tráfico inyectado.

Modos de operación:
  --mode scapy    Envía paquetes individuales con Scapy (requiere root).
                  Para pruebas exactas de conteo paquete a paquete.

  --mode iperf    Lanza servidores y clientes iperf3 para tráfico en volumen.
                  Para disparar el umbral de flujo elefante.

  --mode mixed    Se combinan ambos modos.

Dependencias:
  scapy, iperf3
"""

import argparse
import os
import subprocess
import sys
import time

# Se verifica la disponibilidad de Scapy
try:
    from scapy.all import (
        Ether, IP, TCP, UDP, ICMP, Raw,
        sendp, srp, conf, get_if_hwaddr
    )
    SCAPY_OK = True
except ImportError:
    SCAPY_OK = False

#Configuración de la topología, coincidiendo con topology.py
HOSTS = {
    "h1": {"ip": "10.0.0.1", "mac": "00:00:00:00:01:01", "iface": "h1-eth0"},
    "h2": {"ip": "10.0.0.2", "mac": "00:00:00:00:02:02", "iface": "h2-eth0"},
    "h3": {"ip": "10.0.0.3", "mac": "00:00:00:00:03:03", "iface": "h3-eth0"},
    "h4": {"ip": "10.0.0.4", "mac": "00:00:00:00:04:04", "iface": "h4-eth0"},
}

# Puerto de destino genérico para TCP/UDP en las pruebas
TCP_PORT = 5001
UDP_PORT = 5002
IPERF_PORT = 5201



# SECCIÓN SCAPY

def _build_eth(src_mac: str, dst_mac: str):
    """Construye la cabecera Ethernet base."""
    return Ether(src=src_mac, dst=dst_mac)


def send_icmp(iface: str, src_ip: str, dst_ip: str,
              src_mac: str, dst_mac: str, count: int = 5):
    """
    Envía `count` paquetes ICMP Echo Request desde src_ip hacia dst_ip.
    Estos incrementan el contador global ICMP del switch.
    """
    eth = _build_eth(src_mac, dst_mac)
    pkt = eth / IP(src=src_ip, dst=dst_ip) / ICMP()
    print(f"Scapy - Enviando {count} ICMP  {src_ip} → {dst_ip}")
    sendp(pkt, iface=iface, count=count, inter=0.05, verbose=False)


def send_udp(iface: str, src_ip: str, dst_ip: str,
             src_mac: str, dst_mac: str,
             count: int = 10, payload_size: int = 64):
    """
    Envía `count` paquetes UDP con payload de `payload_size` bytes.
    Estos incrementan el contador global UDP y el direct_counter del flujo.
    """
    eth = _build_eth(src_mac, dst_mac)
    payload = Raw(load=b"X" * payload_size)
    pkt = eth / IP(src=src_ip, dst=dst_ip) / UDP(sport=12345, dport=UDP_PORT) / payload
    print(f"Scapy - Enviando {count} UDP   {src_ip} → {dst_ip}  ({payload_size}B payload)")
    sendp(pkt, iface=iface, count=count, inter=0.02, verbose=False)


def send_tcp(iface: str, src_ip: str, dst_ip: str,
             src_mac: str, dst_mac: str,
             count: int = 10, payload_size: int = 100):
    """
    Envía `count` paquetes TCP SYN sin handshake completo.
    """
    eth = _build_eth(src_mac, dst_mac)
    pkt = eth / IP(src=src_ip, dst=dst_ip) / TCP(sport=54321, dport=TCP_PORT, flags="S")
    print(f"Scapy - Enviando {count} TCP   {src_ip} → {dst_ip}  (SYN)")
    sendp(pkt, iface=iface, count=count, inter=0.02, verbose=False)


def send_elephant_flow(iface: str, src_ip: str, dst_ip: str,
                       src_mac: str, dst_mac: str,
                       total_bytes: int = 200_000):
    """
    Envía suficientes paquetes UDP para superar el umbral de flujo elefante
    (100 000 bytes por defecto en counters.p4). Se usan paquetes de 1400 B
    para minimizar el overhead de cabeceras.
    """
    pkt_size  = 1400
    num_pkts  = (total_bytes // pkt_size) + 1
    eth = _build_eth(src_mac, dst_mac)
    payload = Raw(load=b"E" * pkt_size)
    pkt = eth / IP(src=src_ip, dst=dst_ip) / UDP(sport=9999, dport=UDP_PORT) / payload
    print(f"Scapy - Enviando flujo elefante: {num_pkts} pkts × {pkt_size}B "
          f"≈ {total_bytes:,} B  {src_ip} → {dst_ip}")
    sendp(pkt, iface=iface, count=num_pkts, inter=0.001, verbose=False)
    print(f"Scapy - Flujo elefante completado.")


# ── Escenario básico: tráfico mixto entre todos los pares ────────────────────
def scenario_basic_scapy(args):
    src_name = args.src
    dst_name = args.dst
    src = HOSTS[src_name]
    dst = HOSTS[dst_name]
    iface = src["iface"]
    print(f"\n--- {src_name} → {dst_name} ---")
    send_icmp(iface, src["ip"], dst["ip"], src["mac"], dst["mac"], count=5)
    send_udp (iface, src["ip"], dst["ip"], src["mac"], dst["mac"], count=10)
    send_tcp (iface, src["ip"], dst["ip"], src["mac"], dst["mac"], count=10)
    print("\nTráfico básico completado.")


# ── Escenario elefante ────────────────────────────────────────────────────────
def scenario_elephant_scapy(src_name: str, dst_name: str):
    """Genera un flujo elefante entre src y dst."""
    if not SCAPY_OK:
        sys.exit("Error - Scapy no disponible.")
    src = HOSTS.get(src_name)
    dst = HOSTS.get(dst_name)
    if not src or not dst:
        sys.exit(f"Error - Host desconocido: {src_name} o {dst_name}")
    send_elephant_flow(
        src["iface"], src["ip"], dst["ip"], src["mac"], dst["mac"],
        total_bytes=200_000   # doble del umbral - seguro de activar
    )


#Escenario verify, paquetes exactos
def scenario_verify_scapy(src_name: str, dst_name: str, count: int):
    """
    Envía exactamente `count` paquetes ICMP y muestra el número esperado
    en los contadores para que el usuario lo compare con la salida del
    controlador.
    """
    if not SCAPY_OK:
        sys.exit("Error - Scapy no disponible.")
    src = HOSTS.get(src_name)
    dst = HOSTS.get(dst_name)
    if not src or not dst:
        sys.exit(f"Error - Host desconocido.")

    print(f"Verify - Enviando exactamente {count} paquetes ICMP "
          f"{src_name}→{dst_name}")
    send_icmp(src["iface"], src["ip"], dst["ip"],
              src["mac"], dst["mac"], count=count)
    print(f"Verify - Esperado en controller.py:")
    print(f"  Protocolo ICMP - paquetes += {count}")
    print(f"  Flujo {src_name}→{dst_name}  - paquetes += {count}")


# SECCIÓN IPERF

def _iperf_server(host_ip: str):
    """Lanza un servidor iperf3 en background."""
    proc = subprocess.Popen(
        ["iperf3", "-s", "-B", host_ip, "-p", str(IPERF_PORT),
         "--one-off", "--forking"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    return proc


def _iperf_client(src_ip: str, dst_ip: str,
                  duration: int = 5, udp: bool = False):
    """Lanza un cliente iperf3 y devuelve el resultado."""
    cmd = ["iperf3", "-c", dst_ip, "-p", str(IPERF_PORT),
           "-t", str(duration), "-B", src_ip]
    if udp:
        cmd += ["-u", "-b", "10M"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return result.stdout


def scenario_iperf(src_name: str, dst_name: str, udp: bool = False):
    """
    Genera tráfico en volumen con iperf3.
    Para provocar flujos elefante sin Scapy.
    """
    src = HOSTS.get(src_name)
    dst = HOSTS.get(dst_name)
    if not src or not dst:
        sys.exit(f"Error - Host desconocido.")

    proto = "UDP" if udp else "TCP"
    print(f"iperf - Iniciando servidor iperf3 {proto} en {dst_name} ({dst['ip']})...")
    srv = _iperf_server(dst["ip"])
    time.sleep(1)

    print(f"iperf - Cliente {src_name}→{dst_name} durante 5s ({proto})...")
    output = _iperf_client(src["ip"], dst["ip"], duration=5, udp=udp)
    srv.terminate()
    print(output)
    print(f"Prueba iperf {proto} completada.")


def main():
    parser = argparse.ArgumentParser(
        description="Generador de tráfico — Lab 2 Contadores P4"
    )
    parser.add_argument(
        "--mode", choices=["scapy", "iperf", "mixed"], default="mixed",
        help="Modo de generación de tráfico (default: mixed)"
    )
    parser.add_argument(
        "--scenario",
        choices=["basic", "elephant", "verify"],
        default="basic",
        help="Escenario de prueba (default: basic)"
    )
    parser.add_argument(
        "--src", default="h1",
        help="Host origen (nombre: h1..h4 o IP)"
    )
    parser.add_argument(
        "--dst", default="h2",
        help="Host destino (nombre: h1..h4 o IP)"
    )
    parser.add_argument(
        "--count", type=int, default=20,
        help="Número de paquetes para el escenario 'verify' (default: 20)"
    )
    args = parser.parse_args()

    #Se noormaliza src/dst a nombre de host
    ip_to_name = {v["ip"]: k for k, v in HOSTS.items()}
    src = ip_to_name.get(args.src, args.src)
    dst = ip_to_name.get(args.dst, args.dst)

    print("=" * 60)
    print("  Generador de Tráfico — Lab 2 Contadores P4")
    print("=" * 60)
    print(f"  Modo     : {args.mode}")
    print(f"  Escenario: {args.scenario}")
    print(f"  Src      : {src}")
    print(f"  Dst      : {dst}")
    print("=" * 60 + "\n")

    #Modo Scapy
    if args.mode in ("scapy", "mixed"):
        if args.scenario == "basic":
            scenario_basic_scapy(args)
        elif args.scenario == "elephant":
            scenario_elephant_scapy(src, dst)
        elif args.scenario == "verify":
            scenario_verify_scapy(src, dst, args.count)

    #Modo iperf
    if args.mode in ("iperf", "mixed"):
        if args.scenario in ("basic", "elephant"):
            print("\n--- iperf3 TCP ---")
            scenario_iperf(src, dst, udp=False)
            print("\n--- iperf3 UDP ---")
            scenario_iperf(src, dst, udp=True)


if __name__ == "__main__":
    main()
