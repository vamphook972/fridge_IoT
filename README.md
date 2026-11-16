# Monitoreo remoto de alimentos refrigerados (NEVERA_001)

Sistema IoT con dos nodos (ESP32 real y nodo simulado) que publican por MQTT
a un bróker. Un servidor Node-RED procesa los datos y envía actuaciones de vuelta.

## Requisitos
- Python 3.10+
- Node.js 18+ y Node-RED (`npm install -g node-red`)
## Instalación
```bash
pip install -r requirements.txt
mpremote mip install umqtt.simple   # con el ESP32 conectado
```

## Ejecución

1. **Node-RED**
   ```bash
   node-red
   ```
   Abrir http://localhost:1880, importar el flujo `flows.json` y pulsar *Deploy*.

2. **Nodo 1 – ESP32 (hardware)**
   Editar en `nodo1-nevera-iot.py` el WiFi (2,4 GHz) y la IP del bróker (si se va a trabajar con uno personal y no el de pruebas); luego:
   ```bash
   mpremote run nodo1-nevera-iot.py
   ```
   (Para que arranque solo: `mpremote cp nodo1-nevera-iot.py :main.py`)

   > si genera problemas probar:
   ```
    ```bash
    mpremote connect /dev/tty.usbserial-0001 sleep 2 run nodo1-nevera-iot.py
    ```
    ```
    ```

3. **Nodo 2 – Simulado**
   ```bash
   python nodo2-simulado.py
   ```

## Tópicos MQTT (ajustar a los definidos)
- `nevera/NEVERA_001/datos`: nodos -> bróker (JSON con id, fecha, hora, temperatura, puerta, estado)
- `nevera/NEVERA_001/actuacion`: Node-RED -> nodos (encender LED amarillo/rojo)

## Hardware (ESP32)
DHT11 en GPIO 4 · sensor IR de obstáculos en GPIO 5 · LED amarillo GPIO 18 · LED rojo GPIO 19
