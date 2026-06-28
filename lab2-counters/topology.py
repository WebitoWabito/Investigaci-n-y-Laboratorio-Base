#!/usr/bin/env python3
"""
topology.py — Lab 2: Contadores y Estadísticas de Tráfico

Levanta una topología Mininet con:
  - 1 switch P4 (BMv2 simple_switch) corriendo counters.p4
  - 4 hosts (h1..h4) conectados al switch
Esquema de red:
    h1 (10.0.0.1/24) port 1 
    h2 (10.0.0.2/24) port 2 
                            S1 (BMv2 simple_switch)
    h3 (10.0.0.3/24) port 3 
    h4 (10.0.0.4/24) port 4
 
El switch actúa como monitor pasivo "bump in the wire": reenvía paquetes
entre puertos según la tabla l2_forward instalada por el controlador.
 
Uso:
    sudo /home/p4/src/p4dev-python-venv/bin/python3 topology.py
"""
 
import os
import sys
import json
import subprocess
import time
 
from mininet.net import Mininet
from mininet.node import Node, Host
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel, info
 
#Rutas
SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
P4_JSON     = os.path.join(SCRIPT_DIR, "build", "counters.json")
THRIFT_PORT = 9090
LOG_DIR     = "/tmp/lab2-logs"
 
 
class P4Switch(Node):
    """
    Nodo Mininet que lanza BMv2 simple_switch directamente.
    Implementa la interfaz mínima que Mininet necesita de un switch.
    """
 
    def __init__(self, name, json_path, thrift_port=9090, **kwargs):
        kwargs['inNamespace'] = False# el switch se encuentra en el namespace raíz
        super().__init__(name, **kwargs)
        self.json_path   = json_path
        self.thrift_port = thrift_port
        self.sw_proc     = None
 
    def start(self, controllers=None):
        """Lanza simple_switch con las interfaces conectadas."""
        os.makedirs(LOG_DIR, exist_ok=True)
        log_file = os.path.join(LOG_DIR, f"{self.name}.log")
 
        # Construir lista -i <port>@<iface> en orden
        iface_args = []
        for port, intf in sorted(self.intfs.items()):
            if port == 0:
                continue
            iface_args += ["-i", f"{port}@{intf.name}"]
 
        cmd = (
            ["simple_switch",
             "--thrift-port", str(self.thrift_port),
             "--log-console"]
            + iface_args
            + [self.json_path]
        )
 
        info(f"{self.name}: {' '.join(cmd)}\n")
        self.sw_proc = subprocess.Popen(
            cmd,
            stdout=open(log_file, "w"),
            stderr=subprocess.STDOUT,
        )
        time.sleep(2) #se espera a que abra el socket Thrift
        if self.sw_proc.poll() is not None:
            sys.exit(f"Error - simple_switch terminó prematuramente. "
                     f"Revisar {log_file}")
 
    def stop(self, deleteIntfs=True):
        if self.sw_proc:
            self.sw_proc.terminate()
            self.sw_proc.wait()
        super().stop(deleteIntfs=deleteIntfs)
 
    # Mininet llama a estos métodos en switches
    def attach(self, intf): pass
    def detach(self, intf): pass
 
 
def run():
    if not os.path.isfile(P4_JSON):
        sys.exit(
            f"Error - No se encontró {P4_JSON}.\n"
            "Compilar primero con:  make"
        )
 
    setLogLevel("info")
 
    net = Mininet(controller=None, link=TCLink, autoSetMacs=True)
 
    info("Creando switch P4\n")
    s1 = net.addSwitch("s1", cls=P4Switch,
                       json_path=P4_JSON,
                       thrift_port=THRIFT_PORT)
 
    #Hosts
    hosts_cfg = [
        ("h1", "10.0.0.1/24", "00:00:00:00:01:01"),
        ("h2", "10.0.0.2/24", "00:00:00:00:02:02"),
        ("h3", "10.0.0.3/24", "00:00:00:00:03:03"),
        ("h4", "10.0.0.4/24", "00:00:00:00:04:04"),
    ]
 
    info("Creando hosts\n")
    hosts = []
    for name, ip, mac in hosts_cfg:
        h = net.addHost(name, ip=ip, mac=mac)
        hosts.append(h)
 
    info("Creando enlaces host - switch\n")
    for i, h in enumerate(hosts):
        net.addLink(h, s1, port2=i + 1)
 
    info("Iniciando red\n")
    net.start()

    # ARP estático para evitar broadcasts (el switch P4 no hace flooding)
    info("Configurando ARP estático en los hosts\n")
    arp_map = {
        "h1": [("10.0.0.2","00:00:00:00:02:02"), ("10.0.0.3","00:00:00:00:03:03"), ("10.0.0.4","00:00:00:00:04:04")],
        "h2": [("10.0.0.1","00:00:00:00:01:01"), ("10.0.0.3","00:00:00:00:03:03"), ("10.0.0.4","00:00:00:00:04:04")],
        "h3": [("10.0.0.1","00:00:00:00:01:01"), ("10.0.0.2","00:00:00:00:02:02"), ("10.0.0.4","00:00:00:00:04:04")],
        "h4": [("10.0.0.1","00:00:00:00:01:01"), ("10.0.0.2","00:00:00:00:02:02"), ("10.0.0.3","00:00:00:00:03:03")],
    }
    for host in net.hosts:
        for ip, mac in arp_map[host.name]:
            host.cmd(f"arp -s {ip} {mac}")
 
    #Guarda el mapa de puertos para el controlador
    os.makedirs(LOG_DIR, exist_ok=True)
    port_map = {h.name: i + 1 for i, h in enumerate(hosts)}
    with open(os.path.join(LOG_DIR, "port_map.json"), "w") as f:
        json.dump(port_map, f, indent=2)
 
    info("\n--Topología lista--\n")
    for name, ip, mac in hosts_cfg:
        info(f"  {name}  {ip}  {mac}\n")
    info(f"\n  Switch Thrift: localhost:{THRIFT_PORT}\n")
    info("  Controlador:   python3 controller.py\n\n")
 
    CLI(net)
 
    info("Deteniendo red\n")
    net.stop()
 
 
if __name__ == "__main__":
    run()
