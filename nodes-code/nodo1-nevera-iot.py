import network, ntptime, time, json, dht
from machine import Pin
from umqtt.simple import MQTTClient

# ---------- Configuración ----------
SSID = "@Martinez-wifi7"  # red de 2,4 GHz
CLAVE = "QazsW123"
BROKER = "broker.emqx.io"  # Ip BROKER (Broker de pruebas de emqx)
PUERTO = 1883
ID_OBJETO = "NEVERA_001"
INTERVALO = 2  # segundos entre envíos
NTP_SERVIDORES = ("pool.ntp.org", "time.google.com", "time.cloudflare.com")

TOPIC_DATOS = "nevera/{}/datos".format(ID_OBJETO).encode()
TOPIC_ESTADO = "nevera/{}/estado".format(ID_OBJETO).encode()

# ---------- Hardware ----------
sensor = dht.DHT11(Pin(4))
obstaculo = Pin(5, Pin.IN)
led_amarillo = Pin(18, Pin.OUT)
led_rojo = Pin(19, Pin.OUT)

wlan = network.WLAN(network.STA_IF)


# ---------- Funciones ----------
def conectar_wifi():
    wlan.active(True)
    if not wlan.isconnected():
        wlan.connect(SSID, CLAVE)
        intentos = 0
        while not wlan.isconnected() and intentos < 30:
            time.sleep(1)
            intentos += 1
    return wlan.isconnected()


def sincronizar_hora():
    ntptime.timeout = 5  # por defecto es 1 s y a veces no alcanza
    for _ in range(3):
        for servidor in NTP_SERVIDORES:
            try:
                ntptime.host = servidor
                ntptime.settime()
                print("Hora sincronizada con", servidor)
                return True
            except OSError as e:
                print("NTP falló con", servidor, e)
        time.sleep(1)
    return False


def fecha_hora():
    t = time.localtime(time.time() - 5 * 3600)  # UTC-5 (Colombia)
    fecha = "{:04d}-{:02d}-{:02d}".format(t[0], t[1], t[2])
    hora = "{:02d}:{:02d}:{:02d}".format(t[3], t[4], t[5])
    return fecha, hora


def leer_temperatura():
    # Devuelve la temperatura o None si el DHT11 falla
    try:
        sensor.measure()
        return sensor.temperature()
    except OSError:
        return None


def actuar(estado):
    # El nodo decide cómo reaccionar al estado que envía Node-RED
    led_amarillo.value(1 if estado == "ADVERTENCIA" else 0)
    led_rojo.value(1 if estado == "ALERTA" else 0)


def al_recibir(topic, msg):
    try:
        estado = json.loads(msg)["estado"]
    except (ValueError, KeyError, TypeError):
        print("Mensaje de estado inválido:", msg)
        return
    print("Estado recibido:", estado)
    actuar(estado)


def conectar_mqtt():
    cliente = MQTTClient(ID_OBJETO, BROKER, port=PUERTO, keepalive=30)
    cliente.set_callback(al_recibir)
    cliente.connect()
    cliente.subscribe(TOPIC_ESTADO)  # recibe también el último estado retenido
    print("Conectado al broker", BROKER)
    return cliente


# ---------- Inicio ----------
print("Conectando a WiFi...")
if not conectar_wifi():
    print("No se pudo conectar al WiFi. Código:", wlan.status())
    print("201 = no encuentra la red | 202 = clave incorrecta")
    raise SystemExit
print("WiFi OK:", wlan.ifconfig())

if not sincronizar_hora():
    print("No se pudo sincronizar la hora (¿la red tiene Internet?)")
    raise SystemExit
print("Hora OK:", fecha_hora())

# Esperar una primera lectura válida del DHT11
temp = None
while temp is None:
    time.sleep(2)
    temp = leer_temperatura()
print("DHT11 OK:", temp, "°C")

actuar("NORMAL")  # LEDs apagados hasta recibir el primer estado
cliente = None

# ---------- Ciclo principal ----------
while True:
    try:
        if not wlan.isconnected():
            conectar_wifi()
        if cliente is None:
            print("Conectando al broker", BROKER, "...")
            cliente = conectar_mqtt()

        nueva = leer_temperatura()
        if nueva is not None:
            temp = nueva  # si falla una lectura, se conserva la anterior

        # Objeto frente al sensor (valor 0) = puerta cerrada
        puerta = "CERRADA" if obstaculo.value() == 0 else "ABIERTA"

        fecha, hora = fecha_hora()
        datos = {
            "id": ID_OBJETO,
            "fecha": fecha,
            "hora": hora,
            "temperatura": temp,
            "puerta": puerta,
        }
        mensaje = json.dumps(datos)
        print(mensaje)
        cliente.publish(TOPIC_DATOS, mensaje)

        # Espera el siguiente envío, atendiendo mensajes de estado entrantes
        fin = time.ticks_add(time.ticks_ms(), INTERVALO * 1000)
        while time.ticks_diff(fin, time.ticks_ms()) > 0:
            cliente.check_msg()
            time.sleep_ms(100)

    except OSError as e:
        print("Conexión perdida, reintentando...", e)
        cliente = None
        time.sleep(2)
