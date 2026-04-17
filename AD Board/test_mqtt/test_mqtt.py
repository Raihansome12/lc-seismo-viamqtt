import paho.mqtt.client as mqtt
import json
import time
import random
import numpy as np
from datetime import datetime, timezone
import ssl
import os
import certifi

# MQTT Configuration from .env
MQTT_BROKER = "240fa9ad32cb44929936ab704925afa5.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
MQTT_USERNAME = "project-kuliah"
MQTT_PASSWORD = "Raihan@3012"
MQTT_CLIENT_ID = "python-simulator"
TOPIC_GEOPHONE = "sensors/geophone"
TOPIC_GPS = "sensors/gps"

# TLS Configuration
CA_CERT_PATH = "C:/Users/raiha/OneDrive/Desktop/Program Skripsi/AD Board/test_mqtt/frontend-alb-console-portal-euc1-aws-hivemq-cloud.pem"

def generate_seismic_data(samples=50):
    adc_counts = []
    base_value = random.randint(100, 1000)
    for i in range(samples):
        value = base_value + random.randint(-50, 50)
        value = max(10, min(10000, abs(value)))
        if i % 2 == 1:
            value = -value
        adc_counts.append(int(value))
    return adc_counts

def generate_gps_data():
    # Simulate GPS with slight random walk
    latitude = -6.2 + random.uniform(-0.0005, 0.0005)
    longitude = 106.8 + random.uniform(-0.0005, 0.0005)
    gps_time = datetime.utcnow().isoformat(timespec='milliseconds')

    return {
        "latitude": round(latitude, 7),
        "longitude": round(longitude, 7),
        "reading_times": gps_time
    }

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Connected to MQTT Broker!")
    else:
        print(f"Failed to connect, return code {rc}")

def on_disconnect(client, userdata, rc):
    print(f"Disconnected with result code {rc}")

def main():
    client = mqtt.Client(client_id=MQTT_CLIENT_ID)
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    client.tls_set(
        ca_certs=certifi.where(),
        cert_reqs=ssl.CERT_REQUIRED,
        certfile=None,
        keyfile=None,
        tls_version=ssl.PROTOCOL_TLS_CLIENT
    )
    client.tls_insecure_set(False)

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect

    try:
        print(f"Connecting to {MQTT_BROKER}...")
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start()

        print("Starting data simulator...")
        print("- Geophone every 0.5s → topic:", TOPIC_GEOPHONE)
        print("- GPS every 5s        → topic:", TOPIC_GPS)

        gps_timer = time.time()

        while True:
            # --- Publish geophone ---
            adc_counts = generate_seismic_data(samples=50)
            # reading_times = datetime.utcnow().isoformat(timespec='milliseconds')
            reading_times = datetime.now(timezone.utc).isoformat(timespec='milliseconds')
            geo_payload = {
                "adc_counts": adc_counts,
                "reading_times": reading_times
            }
            client.publish(TOPIC_GEOPHONE, json.dumps(geo_payload))
            print(f"[GEO] Published {reading_times} → {adc_counts}")

            # --- Publish GPS every 5 seconds ---
            if time.time() - gps_timer >= 30.0:
                gps_data = generate_gps_data()
                client.publish(TOPIC_GPS, json.dumps(gps_data))
                print(f"[GPS] Published {gps_data['reading_times']} → {gps_data}")
                gps_timer = time.time()

            # Wait 0.5s
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nStopping simulator...")
        client.loop_stop()
        client.disconnect()
    except Exception as e:
        print(f"Error: {e}")
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    main()
