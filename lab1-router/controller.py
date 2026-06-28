#!/usr/bin/env python3
"""
controller.py — Lab 1 Controlador de Router IPv4 Estático

Este controlador instala las reglas LPM de cada router P4 usando
simple_switch_CLI, igual que un plano de control sencillo.

La lógica de forwarding NO está quemada en router.p4. El programa P4 solo
contiene la tabla ipv4_lpm; las rutas concretas se cargan desde este archivo.

Uso:
    python3 controller.py
    python3 controller.py --switch s1
"""

import argparse
import subprocess
import sys
import time


# Puertos Thrift usados por los tres switches BMv2.
SWITCHES = {
    "s1": 9090,
    "s2": 9091,
    "s3": 9092,
}


# Entradas LPM por router.
# Formato: (prefijo, longitud, mac_destino, mac_origen, puerto_salida)
ROUTES = {
    "s1": [
        ("10.0.1.0", 24, "08:00:00:00:01:11", "08:00:00:00:01:00", 1),
        ("10.0.2.0", 24, "08:00:00:00:21:00", "08:00:00:00:12:00", 2),
        ("10.0.3.0", 24, "08:00:00:00:31:00", "08:00:00:00:13:00", 3),
        ("10.0.4.0", 24, "08:00:00:00:31:00", "08:00:00:00:13:00", 3),
    ],
    "s2": [
        ("10.0.1.0", 24, "08:00:00:00:12:00", "08:00:00:00:21:00", 2),
        ("10.0.2.0", 24, "08:00:00:00:02:22", "08:00:00:00:02:00", 1),
        ("10.0.3.0", 24, "08:00:00:00:32:00", "08:00:00:00:23:00", 3),
        ("10.0.4.0", 24, "08:00:00:00:32:00", "08:00:00:00:23:00", 3),
    ],
    "s3": [
        ("10.0.1.0", 24, "08:00:00:00:13:00", "08:00:00:00:31:00", 2),
        ("10.0.2.0", 24, "08:00:00:00:23:00", "08:00:00:00:32:00", 3),
        ("10.0.3.0", 24, "08:00:00:00:03:33", "08:00:00:00:03:00", 1),
        ("10.0.4.0", 24, "08:00:00:00:04:44", "08:00:00:00:04:00", 4),
    ],
}


def mac_to_hex(mac: str) -> str:
    """
    Convierte una MAC tipo 08:00:00:00:01:11 al formato hexadecimal
    esperado por simple_switch_CLI para parámetros bit<48>.
    """
    return "0x" + mac.replace(":", "")


def _cli(thrift_port: int, commands: list[str]) -> str:
    """
    Ejecuta un bloque de comandos en simple_switch_CLI y devuelve la salida.
    """
    cmd_str = "\n".join(commands) + "\n"

    result = subprocess.run(
        ["simple_switch_CLI", "--thrift-port", str(thrift_port)],
        input=cmd_str,
        capture_output=True,
        text=True,
        timeout=10,
    )

    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)

    output = result.stdout + result.stderr
    errors = [line for line in output.splitlines() if "Error" in line]

    if errors:
        raise RuntimeError("\n".join(errors))

    return output


def build_commands(switch_name: str) -> list[str]:
    """
    Construye los comandos CLI para limpiar e instalar la tabla ipv4_lpm
    de un switch específico.
    """
    commands = ["table_clear MyIngress.ipv4_lpm"]

    for prefix, length, dst_mac, src_mac, port in ROUTES[switch_name]:
        commands.append(
            "table_add MyIngress.ipv4_lpm MyIngress.ipv4_forward "
            f"{prefix}/{length} => {mac_to_hex(dst_mac)} {mac_to_hex(src_mac)} {port}"
        )

    return commands


def configure_switch(switch_name: str, thrift_port: int):
    """
    Instala las reglas LPM de un router P4.
    """
    commands = build_commands(switch_name)
    _cli(thrift_port, commands)

    print(
        f"{switch_name}: {len(ROUTES[switch_name])} rutas LPM instaladas "
        f"en thrift port {thrift_port}."
    )


def configure_all(switch: str = "all"):
    """
    Configura todos los switches o solo uno.
    Esta función también es usada por topology.py en el modo --auto-test.
    """
    time.sleep(1)

    selected = SWITCHES.keys() if switch == "all" else [switch]

    for sw in selected:
        if sw not in SWITCHES:
            raise ValueError(f"Switch desconocido: {sw}")

        configure_switch(sw, SWITCHES[sw])


def main():
    parser = argparse.ArgumentParser(
        description="Controlador de reglas LPM para Lab 1 Router IPv4"
    )

    parser.add_argument(
        "--switch",
        choices=["all", "s1", "s2", "s3"],
        default="all",
        help="Switch a configurar. Default: all",
    )

    args = parser.parse_args()

    try:
        configure_all(args.switch)
    except Exception as exc:
        print(f"Error configurando switches: {exc}", file=sys.stderr)
        print("Verifique que la topología esté corriendo con: make run", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
