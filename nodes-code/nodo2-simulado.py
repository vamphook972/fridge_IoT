#!/usr/bin/env python3
"""
Nodo simulado NEVERA_002  (simula el ESP32 del proyecto de monitoreo de nevera)

- Publica por MQTT las lecturas en:   nevera/<ID>/datos
  {"id", "fecha", "hora", "temperatura", "puerta"}
- Escucha el estado que calcula Node-RED en:  nevera/<ID>/estado
  Del mensaje solo usa el campo "estado" (NORMAL | ADVERTENCIA | ALERTA)
  y enciende los LEDs simulados segun ese estado.

Requisitos:  pip install paho-mqtt
Uso:         python nodo-simulado.py
             python nodo-simulado.py --host 192.168.1.50 --intervalo 2
"""

import argparse
import json
import random
import threading
from datetime import datetime, timedelta, timezone

import paho.mqtt.client as mqtt

# Rangos de temperatura (min, max) para cada escenario de simulacion
ESCENARIOS_TEMP = {
    "NORMAL": (24, 26),
    "ADVERTENCIA": (27, 29),
    "ALERTA": (30, 33),
}

AYUDA = """
Comandos:
  1        temperatura NORMAL        (24-26 °C)
  2        temperatura ADVERTENCIA   (27-29 °C)
  3        temperatura ALERTA        (30-33 °C)
  t <n>    temperatura fija en n °C  (ej: t 28)
  a        abrir puerta
  c        cerrar puerta
  r        modo aleatorio ON/OFF (temperatura y puerta cambian solas)
  s        ver estado actual
  h        ayuda
  q        salir
"""

lock = threading.Lock()
sim = {
    "temp": 25,
    "banda": ESCENARIOS_TEMP["NORMAL"],
    "puerta_cerrada": True,
    "aleatorio": False,
    "estado": "SIN_DATOS",  # ultimo estado recibido de Node-RED
}


# ---------- Simulacion de sensores ----------
def fecha_hora():
    t = datetime.now(timezone(timedelta(hours=-5)))  # UTC-5 Colombia
    return t.strftime("%Y-%m-%d"), t.strftime("%H:%M:%S")


def fijar_escenario(nombre):
    lo, hi = ESCENARIOS_TEMP[nombre]
    sim["banda"] = (lo, hi)
    sim["temp"] = random.randint(lo, hi)


def paso_aleatorio():
    """Cambios espontaneos para el modo aleatorio."""
    if random.random() < 0.05:
        nombre = random.choices(
            ["NORMAL", "ADVERTENCIA", "ALERTA"], weights=[70, 20, 10]
        )[0]
        fijar_escenario(nombre)
    if sim["puerta_cerrada"]:
        if random.random() < 0.08:
            sim["puerta_cerrada"] = False
    else:
        if random.random() < 0.15:
            sim["puerta_cerrada"] = True


def paso_temperatura():
    """La temperatura varia +-1 °C dentro de la banda del escenario."""
    lo, hi = sim["banda"]
    t = sim["temp"] + random.choice([-1, 0, 1])
    sim["temp"] = max(lo, min(hi, t))


# ---------- Actuacion (la decide el estado recibido) ----------
def leds_segun_estado(estado):
    amarillo = 1 if estado == "ADVERTENCIA" else 0
    rojo = 1 if estado == "ALERTA" else 0
    return amarillo, rojo


# ---------- MQTT ----------
def crear_cliente(id_objeto):
    try:  # paho-mqtt >= 2.0
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=id_objeto)
    except AttributeError:  # paho-mqtt 1.x
        return mqtt.Client(client_id=id_objeto)


def main():
    ap = argparse.ArgumentParser(description="Nodo simulado de nevera IoT")
    ap.add_argument("--host", default="broker.emqx.io", help="IP del broker Mosquitto")
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--id", default="NEVERA_002", help="Identificador del objeto")
    ap.add_argument(
        "--intervalo", type=float, default=2.0, help="Segundos entre envios"
    )
    args = ap.parse_args()

    topic_datos = f"nevera/{args.id}/datos"
    topic_estado = f"nevera/{args.id}/estado"

    def on_connect(client, userdata, *rest):
        print(f"[MQTT] Conectado al broker {args.host}:{args.port}")
        client.subscribe(topic_estado)  # tambien recibe el ultimo estado retenido
        print(f"[MQTT] Publicando en   {topic_datos}")
        print(f"[MQTT] Suscrito a      {topic_estado}")

    def on_message(client, userdata, msg):
        try:
            estado = json.loads(msg.payload.decode())["estado"]
        except (ValueError, KeyError, UnicodeDecodeError, TypeError):
            print(f"[ESTADO] Mensaje invalido: {msg.payload!r}")
            return
        with lock:
            sim["estado"] = estado
        print(f"[ESTADO] Recibido de Node-RED: {estado}")

    cliente = crear_cliente(args.id)
    cliente.on_connect = on_connect
    cliente.on_message = on_message
    try:
        cliente.connect(args.host, args.port, keepalive=30)
    except OSError as e:
        print(f"No se pudo conectar al broker {args.host}:{args.port} -> {e}")
        return
    cliente.loop_start()

    stop = threading.Event()

    def ciclo():
        while not stop.is_set():
            with lock:
                if sim["aleatorio"]:
                    paso_aleatorio()
                paso_temperatura()

                fecha, hora = fecha_hora()
                datos = {
                    "id": args.id,
                    "fecha": fecha,
                    "hora": hora,
                    "temperatura": sim["temp"],
                    "puerta": "CERRADA" if sim["puerta_cerrada"] else "ABIERTA",
                }
                amarillo, rojo = leds_segun_estado(sim["estado"])
                estado = sim["estado"]

            payload = json.dumps(datos)
            cliente.publish(topic_datos, payload)
            leds = f"amarillo={'ON ' if amarillo else 'off'} rojo={'ON ' if rojo else 'off'}"
            print(f"{payload}   | estado: {estado} | LEDs: {leds}")
            stop.wait(args.intervalo)

    hilo = threading.Thread(target=ciclo, daemon=True)
    hilo.start()

    print(AYUDA)
    try:
        while True:
            entrada = input().strip().lower()
            if not entrada:
                continue
            with lock:
                if entrada == "1":
                    fijar_escenario("NORMAL")
                elif entrada == "2":
                    fijar_escenario("ADVERTENCIA")
                elif entrada == "3":
                    fijar_escenario("ALERTA")
                elif entrada.startswith("t "):
                    try:
                        n = int(entrada.split()[1])
                        sim["banda"] = (n, n)
                        sim["temp"] = n
                    except (ValueError, IndexError):
                        print("Uso: t <numero>")
                elif entrada == "a":
                    sim["puerta_cerrada"] = False
                elif entrada == "c":
                    sim["puerta_cerrada"] = True
                elif entrada == "r":
                    sim["aleatorio"] = not sim["aleatorio"]
                    print(
                        f"[SIM] Modo aleatorio: {'ON' if sim['aleatorio'] else 'OFF'}"
                    )
                elif entrada == "s":
                    print(f"[SIM] {sim}")
                elif entrada == "h":
                    print(AYUDA)
                elif entrada == "q":
                    break
                else:
                    print("Comando desconocido (h para ayuda)")
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        stop.set()
        cliente.loop_stop()
        cliente.disconnect()
        print("Nodo simulado detenido.")


if __name__ == "__main__":
    main()
