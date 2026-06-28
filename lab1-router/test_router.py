#!/usr/bin/env python3
"""
test_router.py — Lab 1 Pruebas del Router IPv4 Estático

Este archivo contiene las pruebas de verificación usadas por topology.py
cuando se ejecuta:

    make test

Las pruebas revisan:
  - Conectividad entre hosts en subredes distintas.
  - Paso por varios routers.
  - Reducción del TTL observada en las respuestas ICMP.
  - Descarte por defecto cuando no existe una ruta LPM.
"""

import re


# Cada prueba tiene: host_origen, IP_destino, debe_funcionar, descripción.
PING_TESTS = [
    ("h1", "10.0.2.2", True, "h1 -> h2, pasando por s1 y s2"),
    ("h1", "10.0.3.3", True, "h1 -> h3, pasando por s1 y s3"),
    ("h1", "10.0.4.4", True, "h1 -> h4, pasando por s1 y s3"),
    ("h2", "10.0.4.4", True, "h2 -> h4, pasando por s2 y s3"),
    ("h3", "10.0.4.4", True, "h3 -> h4, mismo router s3"),
    ("h1", "10.0.99.99", False, "h1 -> 10.0.99.99, sin ruta LPM"),
]


def _packet_loss(output: str) -> int | None:
    """
    Extrae el porcentaje de pérdida de la salida de ping.
    """
    match = re.search(r"(\d+)% packet loss", output)

    if not match:
        return None

    return int(match.group(1))


def _ttl_values(output: str) -> list[int]:
    """
    Extrae valores TTL observados en respuestas ICMP.
    """
    return [int(value) for value in re.findall(r"ttl=(\d+)", output)]


def run_tests(net) -> bool:
    """
    Ejecuta pruebas usando los objetos Host de Mininet.
    Devuelve True si todas las pruebas pasan.
    """
    print("\n=== Pruebas Lab 1: Router IPv4 Estático ===\n")

    all_ok = True

    for src_name, dst_ip, should_work, description in PING_TESTS:
        host = net.get(src_name)

        print(f"--- {description} ---")
        output = host.cmd(f"ping -c 3 -W 1 {dst_ip}")

        loss = _packet_loss(output)
        ttls = _ttl_values(output)

        if should_work:
            passed = loss == 0
            status = "OK" if passed else "FALLÓ"
            ttl_text = f" TTL observado: {ttls[0]}" if ttls else ""

            print(f"Resultado esperado: conectividad. Resultado: {status}.{ttl_text}")
        else:
            passed = loss == 100
            status = "OK" if passed else "FALLÓ"

            print(f"Resultado esperado: descarte sin ruta. Resultado: {status}.")

        if not passed:
            all_ok = False
            print("Salida de ping:")
            print(output)

        print()

    if all_ok:
        print("Todas las pruebas pasaron correctamente.\n")
    else:
        print("Al menos una prueba falló. Revisar rutas LPM, ARP o puertos.\n")

    return all_ok


def main():
    print("Este archivo se usa automáticamente con: make test")
    print("Para pruebas manuales, levante la red con make run y use comandos ping en Mininet.")


if __name__ == "__main__":
    main()
