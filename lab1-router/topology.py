#!/usr/bin/env python3
r"""
topology.py — Lab 1 Router IPv4 Estático

Levanta una topología Mininet con:
  - 3 routers P4 ejecutando el mismo programa router.p4 en BMv2 simple_switch.
  - 4 hosts ubicados en subredes IPv4 distintas.

Esquema lógico:

    h1 -- s1 -- s2 -- h2
           \   /
            s3 -- h3
             |
             h4

Cada switch P4 actúa como router IPv4. Las rutas LPM se instalan desde
controller.py mediante simple_switch_CLI.

Uso:
    sudo python3 topology.py
    sudo python3 topology.py --auto-test
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

from mininet.cli import CLI
from mininet.link import TCLink
from mininet.log import info, setLogLevel
from mininet.net import Mininet
from mininet.node import Node


SCRIPT_DIR = Path(__file__).resolve().parent
P4_JSON = SCRIPT_DIR / "build" / "router.json"
LOG_DIR = "/tmp/lab1-router-logs"


# Puertos Thrift de cada router P4.
THRIFT_PORTS = {
    "s1": 9090,
    "s2": 9091,
    "s3": 9092,
}

# IDs de dispositivo para cada router P4.
DEVICE_IDS = {
    "s1": 0,
    "s2": 1,
    "s3": 2,
}


class P4Switch(Node):
    """
    Nodo Mininet que ejecuta BMv2 simple_switch directamente.
    Es similar al usado en Lab 2, pero permite crear varios switches P4.
    """

    def __init__(self, name, json_path, thrift_port, device_id, **kwargs):
        kwargs["inNamespace"] = False
        super().__init__(name, **kwargs)

        self.json_path = str(json_path)
        self.thrift_port = thrift_port
        self.device_id = device_id
        self.sw_proc = None

    def start(self, controllers=None):
        """
        Lanza simple_switch usando las interfaces asignadas por Mininet.
        """
        os.makedirs(LOG_DIR, exist_ok=True)
        log_file = os.path.join(LOG_DIR, f"{self.name}.log")

        iface_args = []

        for port, intf in sorted(self.intfs.items()):
            if port == 0:
                continue

            iface_args += ["-i", f"{port}@{intf.name}"]

        cmd = (
            [
                "simple_switch",
                "--device-id",
                str(self.device_id),
                "--thrift-port",
                str(self.thrift_port),
                "--log-console",
            ]
            + iface_args
            + [self.json_path]
        )

        info(f"{self.name}: {' '.join(cmd)}\n")

        self.sw_proc = subprocess.Popen(
            cmd,
            stdout=open(log_file, "w"),
            stderr=subprocess.STDOUT,
        )

        time.sleep(2)

        if self.sw_proc.poll() is not None:
            sys.exit(
                f"Error - {self.name} terminó prematuramente. "
                f"Revise el log: {log_file}"
            )

    def stop(self, deleteIntfs=True):
        """
        Detiene el proceso simple_switch asociado al nodo.
        """
        if self.sw_proc:
            self.sw_proc.terminate()
            self.sw_proc.wait()

        super().stop(deleteIntfs=deleteIntfs)

    # Métodos requeridos por Mininet para nodos tipo switch.
    def attach(self, intf):
        pass

    def detach(self, intf):
        pass

# Configuración de hosts
HOSTS = {
    "h1": {
        "ip": "10.0.1.1/24",
        "mac": "08:00:00:00:01:11",
        "gw": "10.0.1.10",
        "gw_mac": "08:00:00:00:01:00",
    },
    "h2": {
        "ip": "10.0.2.2/24",
        "mac": "08:00:00:00:02:22",
        "gw": "10.0.2.20",
        "gw_mac": "08:00:00:00:02:00",
    },
    "h3": {
        "ip": "10.0.3.3/24",
        "mac": "08:00:00:00:03:33",
        "gw": "10.0.3.30",
        "gw_mac": "08:00:00:00:03:00",
    },
    "h4": {
        "ip": "10.0.4.4/24",
        "mac": "08:00:00:00:04:44",
        "gw": "10.0.4.40",
        "gw_mac": "08:00:00:00:04:00",
    },
}


def configure_hosts(net: Mininet):
    """
    Configura gateway por defecto y ARP estático en cada host.
    """
    info("Configurando rutas y ARP estático en hosts\n")

    for name, cfg in HOSTS.items():
        host = net.get(name)
        iface = f"{name}-eth0"

        host.cmd(f"ip route add default via {cfg['gw']} dev {iface}")
        host.cmd(f"arp -i {iface} -s {cfg['gw']} {cfg['gw_mac']}")


def create_topology() -> Mininet:
    """
    Construye la topología Mininet del laboratorio.
    """
    net = Mininet(controller=None, link=TCLink, autoSetMacs=False)

    info("Creando routers P4\n")

    s1 = net.addSwitch(
        "s1",
        cls=P4Switch,
        json_path=P4_JSON,
        thrift_port=THRIFT_PORTS["s1"],
        device_id=DEVICE_IDS["s1"],
    )

    s2 = net.addSwitch(
        "s2",
        cls=P4Switch,
        json_path=P4_JSON,
        thrift_port=THRIFT_PORTS["s2"],
        device_id=DEVICE_IDS["s2"],
    )

    s3 = net.addSwitch(
        "s3",
        cls=P4Switch,
        json_path=P4_JSON,
        thrift_port=THRIFT_PORTS["s3"],
        device_id=DEVICE_IDS["s3"],
    )

    info("Creando hosts\n")

    h1 = net.addHost("h1", ip=HOSTS["h1"]["ip"], mac=HOSTS["h1"]["mac"])
    h2 = net.addHost("h2", ip=HOSTS["h2"]["ip"], mac=HOSTS["h2"]["mac"])
    h3 = net.addHost("h3", ip=HOSTS["h3"]["ip"], mac=HOSTS["h3"]["mac"])
    h4 = net.addHost("h4", ip=HOSTS["h4"]["ip"], mac=HOSTS["h4"]["mac"])

    info("Creando enlaces\n")

    net.addLink(h1, s1, port2=1)
    net.addLink(s1, s2, port1=2, port2=2)
    net.addLink(s1, s3, port1=3, port2=2)
    net.addLink(s3, s2, port1=3, port2=3)
    net.addLink(h2, s2, port2=1)
    net.addLink(h3, s3, port2=1)
    net.addLink(h4, s3, port2=4)

    return net


def run(auto_test: bool = False):
    """
    Inicia la red. Si auto_test=True, instala reglas y ejecuta pruebas.
    Si auto_test=False, abre la consola interactiva de Mininet.
    """
    if not P4_JSON.exists():
        sys.exit(
            f"Error - No se encontró {P4_JSON}.\n"
            "Compile primero con: make"
        )

    setLogLevel("info")

    net = create_topology()

    try:
        info("Iniciando red\n")
        net.start()

        configure_hosts(net)

        info("\n-- Topología lista --\n")
        info("Routers P4: s1 thrift=9090, s2 thrift=9091, s3 thrift=9092\n")
        info("Para cargar reglas manualmente: python3 controller.py\n\n")

        if auto_test:
            info("Modo auto-test: instalando reglas LPM y ejecutando pruebas\n")

            import controller
            import test_router

            controller.configure_all()
            time.sleep(1)

            ok = test_router.run_tests(net)

            if not ok:
                sys.exit(1)
        else:
            CLI(net)

    finally:
        info("Deteniendo red\n")
        net.stop()


def main():
    parser = argparse.ArgumentParser(
        description="Topología Mininet para Lab 1 Router IPv4 Estático"
    )

    parser.add_argument(
        "--auto-test",
        action="store_true",
        help="Instala reglas LPM, ejecuta pruebas y cierra la topología",
    )

    args = parser.parse_args()
    run(auto_test=args.auto_test)


if __name__ == "__main__":
    main()
