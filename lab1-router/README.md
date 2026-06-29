# Lab 1 — Router IPv4 Estático en P4

Router IPv4 estático implementado en el plano de datos usando P4 (BMv2/v1model).

Este laboratorio implementa una red con tres routers P4 y cuatro hosts ubicados en subredes distintas. Cada router ejecuta el mismo programa `router.p4`, pero recibe reglas LPM diferentes desde un controlador en Python. El programa P4 se encarga de procesar paquetes Ethernet/IPv4, aplicar una tabla de enrutamiento LPM, reescribir direcciones MAC, seleccionar el puerto de salida, decrementar el TTL y descartar paquetes cuando no existe una ruta válida.

# Estructura de archivos

```
lab1-router/
  router.p4              # Programa P4: parser Ethernet/IPv4, tabla LPM, TTL, MAC rewrite
  router.p4info.txtpb    # Generado por p4c: información de runtime del programa P4
  build/
     router.json         # JSON para BMv2
     router.p4i          # Salida del preprocesador
  topology.py            # Topología Mininet: 3 routers P4 + 4 hosts
  controller.py          # Controlador Python: instala reglas LPM en s1, s2 y s3
  test_router.py         # Script de pruebas automáticas
  Makefile               # Compilación, ejecución, pruebas y limpieza
  README.md
```

# Requisitos

* Python 3.8+
* p4c con soporte para v1model
* BMv2 simple_switch
* Mininet 2.3+
* simple_switch_CLI

# Compilar el programa P4

Desde `lab1-router/`:

```bash
make
```

También se puede compilar manualmente con:

```bash
p4c --target bmv2 --arch v1model \
    --p4runtime-files router.p4info.txtpb \
    -o build \
    router.p4
```

Verifica que existan `build/router.json` y `router.p4info.txtpb`.

# Levantar la topología Mininet

```bash
make run
```

Esto arranca:

* 3 routers P4 (`s1`, `s2`, `s3`) ejecutando BMv2 con `router.json`.
* 4 hosts ubicados en subredes IPv4 distintas.
* Cada router usa un puerto Thrift distinto para recibir reglas desde el controlador.

| Router | Puerto Thrift | Device ID |
| ------ | ------------- | --------- |
| s1     | 9090          | 0         |
| s2     | 9091          | 1         |
| s3     | 9092          | 2         |

Hosts configurados:

| Host | IP          | MAC               | Gateway   |
| ---- | ----------- | ----------------- | --------- |
| h1   | 10.0.1.1/24 | 08:00:00:00:01:11 | 10.0.1.10 |
| h2   | 10.0.2.2/24 | 08:00:00:00:02:22 | 10.0.2.20 |
| h3   | 10.0.3.3/24 | 08:00:00:00:03:33 | 10.0.3.30 |
| h4   | 10.0.4.4/24 | 08:00:00:00:04:44 | 10.0.4.40 |

Esquema lógico:

```
    h1 -- s1 -- s2 -- h2
           \   /
            s3 -- h3
             |
             h4
```

Cada switch P4 actúa como router IPv4. Las rutas no están escritas directamente dentro de `router.p4`, sino que se instalan desde `controller.py` usando `simple_switch_CLI`.

# Lanzar el controlador

En otra terminal, mientras Mininet está corriendo:

```bash
python3 controller.py
```

El controlador instala las reglas LPM en los tres routers:

```
s1: 4 rutas LPM instaladas en thrift port 9090.
s2: 4 rutas LPM instaladas en thrift port 9091.
s3: 4 rutas LPM instaladas en thrift port 9092.
```

También se puede configurar un router específico:

```bash
python3 controller.py --switch s1
python3 controller.py --switch s2
python3 controller.py --switch s3
```

Opciones:

```
--switch all    Configura todos los routers. Es el valor por defecto.
--switch s1     Configura solo el router s1.
--switch s2     Configura solo el router s2.
--switch s3     Configura solo el router s3.
```

# Pruebas manuales desde la CLI de Mininet

Una vez que la topología esté corriendo y el controlador haya instalado las reglas, se pueden ejecutar estas pruebas desde la consola de Mininet:

```
mininet> h1 ping -c 3 h2
mininet> h1 ping -c 3 h3
mininet> h1 ping -c 3 h4
mininet> h2 ping -c 3 h4
mininet> h3 ping -c 3 h4
```

Estas pruebas deben responder correctamente con `0% packet loss`.

Para verificar el descarte por defecto cuando no existe una ruta LPM:

```
mininet> h3 ping -c 3 10.0.99.99
```

Esta prueba debe fallar con `100% packet loss`, ya que no existe ninguna regla para alcanzar la red `10.0.99.0/24`.

# Pruebas automáticas

El laboratorio también incluye un script de verificación automática:

```bash
make test
```

Este comando:

1. Compila `router.p4`.
2. Levanta la topología Mininet.
3. Instala las reglas LPM usando `controller.py`.
4. Ejecuta pruebas de conectividad usando `test_router.py`.
5. Verifica el descarte por defecto.
6. Cierra la topología al finalizar.

# Salida esperada de las pruebas

Ejemplo de conectividad entre hosts:

```
mininet> h1 ping -c 3 h2
PING 10.0.2.2 (10.0.2.2) 56(84) bytes of data.
64 bytes from 10.0.2.2: icmp_seq=1 ttl=62 time=1.95 ms
64 bytes from 10.0.2.2: icmp_seq=2 ttl=62 time=1.77 ms
64 bytes from 10.0.2.2: icmp_seq=3 ttl=62 time=1.78 ms

--- 10.0.2.2 ping statistics ---
3 packets transmitted, 3 received, 0% packet loss
```

El valor `ttl=62` indica que la respuesta pasó por dos routers P4. El host responde normalmente con TTL inicial 64 y cada router decrementa el TTL en una unidad.

Ejemplo de hosts conectados al mismo router P4:

```
mininet> h3 ping -c 3 h4
PING 10.0.4.4 (10.0.4.4) 56(84) bytes of data.
64 bytes from 10.0.4.4: icmp_seq=1 ttl=63 time=0.945 ms
64 bytes from 10.0.4.4: icmp_seq=2 ttl=63 time=1.12 ms
64 bytes from 10.0.4.4: icmp_seq=3 ttl=63 time=1.03 ms

--- 10.0.4.4 ping statistics ---
3 packets transmitted, 3 received, 0% packet loss
```

El valor `ttl=63` indica que el paquete pasó por un solo router P4, ya que `h3` y `h4` están conectados al router `s3`.

Ejemplo de descarte por falta de ruta:

```
mininet> h3 ping -c 3 10.0.99.99
PING 10.0.99.99 (10.0.99.99) 56(84) bytes of data.

--- 10.0.99.99 ping statistics ---
3 packets transmitted, 0 received, 100% packet loss
```

# Limpieza

Para limpiar archivos generados y logs temporales:

```bash
make clean
```

Si Mininet deja interfaces antiguas después de una ejecución manual, se puede limpiar con:

```bash
sudo -E env "PATH=$PATH" mn -c
sudo pkill -f simple_switch
sudo rm -f /tmp/bmv2-*-notifications.ipc
sudo rm -rf /tmp/lab1-router-logs
```

# Funcionamiento general

El programa `router.p4` procesa únicamente paquetes IPv4. Primero extrae los encabezados Ethernet e IPv4. Luego aplica la tabla `ipv4_lpm`, donde el controlador instala las rutas de cada router. Cuando una entrada coincide, se ejecuta la acción `ipv4_forward`, la cual modifica la MAC destino, modifica la MAC origen, asigna el puerto de salida y decrementa el TTL.

Si el paquete no es IPv4, si el TTL es menor o igual a 1, o si no existe una entrada LPM válida, el paquete se descarta. Después de modificar el TTL, el programa recalcula el checksum IPv4 antes de reenviar el paquete.
