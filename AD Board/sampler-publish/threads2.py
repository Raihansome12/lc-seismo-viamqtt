import time
import threading
import queue
import json
import ADS1256
import RPi.GPIO as GPIO
import serial
import pynmea2
import paho.mqtt.client as mqtt
import ssl
from datetime import datetime
import certifi

# MQTT Config
MQTT_BROKER = "240fa9ad32cb44929936ab704925afa5.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
MQTT_USERNAME = "project-kuliah"
MQTT_PASSWORD = "Raihan@3012"
MQTT_CLIENT_ID = "skripsi"
MQTT_TOPIC_GEOPHONE = "sensors/geophone"
MQTT_TOPIC_GPS = "sensors/gps"
CA_CERT_PATH = "./frontend-alb-console-portal-euc1-aws-hivemq-cloud.pem"

class GeophoneSensor:
    def __init__(self, mqtt_client=None, sps=60):
        self.adc = ADS1256.ADS1256()
        if self.adc.ADS1256_init() == -1:
            raise Exception("ADS1256 initialization failed")

        gain = ADS1256.ADS1256_GAIN_E['ADS1256_GAIN_1']
        self.adc.ADS1256_ConfigADC(gain, ADS1256.ADS1256_DRATE_E['ADS1256_60SPS'])
        self.adc.ADS1256_SetMode(1)

        self.running = False
        self.mqtt_client = mqtt_client
        self.sample_queue = queue.Queue(maxsize=1000)
        self.sps = sps

    def read_sensor(self):
        try:
            value = self.adc.ADS1256_GetChannalValue(0)
            timestamp = datetime.utcnow().isoformat()
            return (value, timestamp)
        except Exception as e:
            print(f"Error reading sensor: {e}")
            return None

    def sampler(self):
        interval = 1.0 / self.sps
        next_time = time.time()
        while self.running:
            result = self.read_sensor()
            if result:
                try:
                    self.sample_queue.put_nowait(result)
                except queue.Full:
                    print("WARNING: Sample queue is full. Dropping data.")
            next_time += interval
            sleep_time = max(0, next_time - time.time())
            time.sleep(sleep_time)

    def sender(self):
        while self.running:
            buffer = []
            start_time = time.time()
            while len(buffer) < 50 and self.running:
                try:
                    value, ts = self.sample_queue.get(timeout=0.1)
                    buffer.append(value)
                except queue.Empty:
                    continue

            if self.running and self.mqtt_client:
                try:
                    payload = {
                        "adc_counts": buffer,
                        "reading_times": datetime.utcnow().isoformat()
                    }
                    self.mqtt_client.publish(MQTT_TOPIC_GEOPHONE, json.dumps(payload))
                    print(f"Published {len(buffer)} samples at {payload['reading_times']}")
                except Exception as e:
                    print(f"Error publishing: {e}")

            elapsed = time.time() - start_time
            if elapsed < 1.0:
                time.sleep(1.0 - elapsed)

    def run(self):
        self.running = True
        threading.Thread(target=self.sampler, daemon=True).start()
        threading.Thread(target=self.sender, daemon=True).start()

    def stop(self):
        self.running = False
        GPIO.cleanup()

class GPSSensor:
    def __init__(self, port='/dev/serial0', baud_rate=9600, mqtt_client=None):
        self.port = port
        self.baud_rate = baud_rate
        self.gps_serial = None
        self.running = False
        self.mqtt_client = mqtt_client

    def initialize(self):
        try:
            self.gps_serial = serial.Serial(self.port, self.baud_rate, timeout=1)
            return True
        except Exception as e:
            print(f"Error initializing GPS: {e}")
            return False

    def read_sensor(self):
        if not self.gps_serial and not self.initialize():
            return None

        start_time = time.time()
        while (time.time() - start_time) < 5:
            try:
                line = self.gps_serial.readline().decode('ascii', errors='ignore')
                if line.startswith('$GNGGA') or line.startswith('$GPGGA'):
                    msg = pynmea2.parse(line)
                    if msg.latitude and msg.longitude:
                        return {
                            "latitude": msg.latitude,
                            "longitude": msg.longitude,
                            "reading_times": datetime.utcnow().isoformat()
                        }
            except Exception:
                self.initialize()
        return None

    def run(self):
        self.running = True
        while self.running:
            data = self.read_sensor()
            if data and self.mqtt_client:
                try:
                    self.mqtt_client.publish(MQTT_TOPIC_GPS, json.dumps(data))
                    print(f"GPS: {data['latitude']}, {data['longitude']} at {data['reading_times']}")
                except Exception as e:
                    print(f"Error publishing GPS: {e}")
            time.sleep(300)

    def stop(self):
        self.running = False
        if self.gps_serial:
            self.gps_serial.close()


def setup_mqtt():
    def on_connect(client, userdata, flags, rc):
        print("Connected" if rc == 0 else f"Connect failed: {rc}")

    def on_disconnect(client, userdata, rc):
        print(f"Disconnected: {rc}")

    client = mqtt.Client(client_id=MQTT_CLIENT_ID)
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect

    try:
        client.tls_set(ca_certs=CA_CERT_PATH, certfile=None, keyfile=None, cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLSv1_2)
        client.tls_insecure_set(False)
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start()
        time.sleep(2)
        return client
    except Exception as e:
        print(f"MQTT setup error: {e}")
        return None


def main():
    mqtt_client = setup_mqtt()
    if not mqtt_client:
        return

    geophone = GeophoneSensor(mqtt_client=mqtt_client, sps=60)
    gps = GPSSensor(mqtt_client=mqtt_client)

    print("Starting sensors...")
    geophone.run()
    gps_thread = threading.Thread(target=gps.run)
    gps_thread.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping...")

    geophone.stop()
    gps.stop()
    gps_thread.join()
    mqtt_client.loop_stop()
    mqtt_client.disconnect()
    print("Shutdown complete.")


if __name__ == "__main__":
    main()
