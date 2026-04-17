#!/usr/bin/env python3
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
import logging
import sys
import signal
import os

# Setup logging untuk systemd
# Console handler untuk semua level
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(console_formatter)

# File handler hanya untuk ERROR
file_handler = logging.FileHandler('/var/log/seismic-service/seismic_monitor.log')
file_handler.setLevel(logging.ERROR)
file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(file_formatter)

# Setup root logger
logging.basicConfig(
    level=logging.INFO,
    handlers=[console_handler, file_handler]
)
logger = logging.getLogger(__name__)

# Global variable untuk kontrol shutdown
shutdown_event = threading.Event()

# Konfigurasi untuk MQTT
MQTT_BROKER = "240fa9ad32cb44929936ab704925afa5.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
MQTT_USERNAME = "project-kuliah"
MQTT_PASSWORD = "Raihan@3012"
MQTT_CLIENT_ID = "skripsi"
MQTT_TOPIC_GEOPHONE = "sensors/geophone"
MQTT_TOPIC_GPS = "sensors/gps"


# Konfigurasi untuk geophone (ADC)
class GeophonesensorADC:
    def __init__(self, mqtt_client=None):
        self.adc = ADS1256.ADS1256()
        if self.adc.ADS1256_init() == -1:
            raise Exception("ADS1256 initialization failed")
        
        # Konfigurasi ADC dengan SPS 50 dan gain 1
        sps = ADS1256.ADS1256_DRATE_E['ADS1256_50SPS']
        gain = ADS1256.ADS1256_GAIN_E['ADS1256_GAIN_1']
        self.adc.ADS1256_ConfigADC(gain, sps)
        
        # Set mode differential input
        self.adc.ADS1256_SetMode(1)
        
        self.running = False
        self.mqtt_client = mqtt_client
        self.adc_buffer = []  # Buffer untuk menyimpan 25 data ADC
        self.buffer_size = 25
    
    def read_sensor(self):
        try:
            adc_value = self.adc.ADS1256_GetChannalValue(0)
            return adc_value
        except Exception as e:
            logger.error(f"Error reading geophone: {e}")
            return None
    
    def run(self):
        self.running = True
        sample_counter = 0
        logger.info("Geophone thread started")
        
        try:
            while self.running and not shutdown_event.is_set():
                start_time = time.time()
                
                # Baca data ADC
                adc_value = self.read_sensor()
                if adc_value is not None:
                    self.adc_buffer.append(adc_value)
                    sample_counter += 1
                    
                    # Jika buffer sudah penuh (25 data), kirim ke MQTT
                    if len(self.adc_buffer) >= self.buffer_size:
                        timestamp = datetime.utcnow().isoformat()
                        
                        # Buat payload sesuai format yang diminta
                        payload = {
                            "adc_counts": self.adc_buffer.copy(),
                            "reading_times": timestamp
                        }
                        
                        # Kirim data ke MQTT jika klien tersedia
                        if self.mqtt_client:
                            try:
                                json_payload = json.dumps(payload)
                                self.mqtt_client.publish(MQTT_TOPIC_GEOPHONE, json_payload)
                                logger.info(f"Geophone: Sent {len(self.adc_buffer)} samples at {timestamp}")
                            except Exception as e:
                                logger.error(f"Error publishing geophone data: {e}")
                        
                        # Kosongkan buffer
                        self.adc_buffer.clear()
                
                # Hitung berapa lama perlu tidur untuk mencapai SPS 50
                elapsed = time.time() - start_time
                sleep_time = max(0, (1.0/40) - elapsed)  # 50 SPS = 0.02 detik per sampel
                
                if sleep_time > 0:
                    time.sleep(sleep_time)
                else:
                    # Jika proses terlalu lama, catat peringatan
                    logger.warning(f"Geophone sampling taking too long! ({elapsed:.4f}s > 0.02s)")
                
                # Check for shutdown event periodically
                if shutdown_event.wait(0):
                    break
        
        except Exception as e:
            logger.error(f"Error in geophone thread: {e}")
        finally:
            try:
                GPIO.cleanup()
            except:
                pass
            logger.info("Geophone thread stopped")
    
    def stop(self):
        self.running = False


# Konfigurasi untuk GPS
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
            logger.error(f"Error initializing GPS: {e}")
            return False
    
    def read_sensor(self):
        if not self.gps_serial:
            if not self.initialize():
                return None
        
        # Kita akan membaca beberapa baris untuk mendapatkan GNGGA/GPGGA
        start_time = time.time()
        while (time.time() - start_time) < 5:  # Timeout setelah 5 detik
            if shutdown_event.is_set():
                return None
                
            try:
                gps_data = self.gps_serial.readline().decode('ascii', errors='ignore')
                if gps_data.startswith('$GNGGA') or gps_data.startswith('$GPGGA'):
                    try:
                        msg = pynmea2.parse(gps_data)
                        if msg.latitude and msg.longitude:  # Pastikan ada data koordinat
                            return {
                                "latitude": msg.latitude,
                                "longitude": msg.longitude,
                                "reading_times": datetime.utcnow().isoformat()
                            }
                    except pynmea2.ParseError as e:
                        logger.error(f"GPS parse error: {e}")
            except Exception as e:
                logger.error(f"Error reading GPS: {e}")
                # Coba reinisialisasi koneksi serial
                self.initialize()
        
        return None
    
    def run(self):
        self.running = True
        logger.info("GPS thread started")
        
        try:
            while self.running and not shutdown_event.is_set():
                data = self.read_sensor()
                if data:
                    # Kirim data ke MQTT jika klien tersedia
                    if self.mqtt_client:
                        try:
                            payload = json.dumps(data)
                            self.mqtt_client.publish(MQTT_TOPIC_GPS, payload)
                            logger.info(f"GPS: Lat={data['latitude']}, Lon={data['longitude']} at {data['reading_times']}")
                        except Exception as e:
                            logger.error(f"Error publishing GPS data: {e}")
                else:
                    logger.warning("Failed to get GPS data")
                
                # Tunggu 5 menit sebelum pembacaan berikutnya
                # Tetapi kita perlu memecah waktu tidur untuk memungkinkan penghentian dengan cepat
                for _ in range(300):  # 5 menit = 300 detik
                    if not self.running or shutdown_event.is_set():
                        break
                    time.sleep(1)
        except Exception as e:
            logger.error(f"Error in GPS thread: {e}")
        finally:
            if self.gps_serial:
                try:
                    self.gps_serial.close()
                except:
                    pass
            logger.info("GPS thread stopped")
    
    def stop(self):
        self.running = False


# Konfigurasi MQTT dengan TLS
def setup_mqtt():
    # Callback saat terhubung
    def on_connect(client, userdata, flags, rc, properties=None):
        if rc == 0:
            logger.info("Connected to MQTT broker")
        else:
            logger.error(f"Failed to connect to MQTT broker with error code: {rc}")
    
    # Callback saat terputus
    def on_disconnect(client, userdata, rc, properties=None):
        logger.warning(f"Disconnected from MQTT broker with error code: {rc}")
    
    # Buat klien MQTT
    client = mqtt.Client(
        client_id=MQTT_CLIENT_ID,
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2
    )
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    
    # Set username dan password
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    
    # Konfigurasi TLS/SSL
    try:
        # Untuk HiveMQ Cloud, biasanya menggunakan TLS versi 1.2
        client.tls_set(
            ca_certs=certifi.where(),  # Menggunakan certifi untuk CA certificates
            certfile=None, 
            keyfile=None, 
            cert_reqs=ssl.CERT_REQUIRED,
            tls_version=ssl.PROTOCOL_TLSv1_2
        )
        
        # Untuk HiveMQ Cloud, biasanya tidak perlu verifikasi hostname
        client.tls_insecure_set(False)
        
    except Exception as e:
        logger.error(f"Error setting up TLS: {e}")
        return None
    
    # Coba koneksi ke broker
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start()  # Mulai loop di background
        
        # Wait for connection with timeout
        for _ in range(10):  # Wait up to 10 seconds
            if client.is_connected():
                break
            time.sleep(1)
        
        if not client.is_connected():
            logger.error("Failed to connect to MQTT broker within timeout")
            return None
            
        return client
    except Exception as e:
        logger.error(f"Error connecting to MQTT broker: {e}")
        return None


# Signal handler untuk graceful shutdown
def signal_handler(signum, frame):
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    shutdown_event.set()


# Fungsi utama
def main():
    logger.info("Starting sensor service...")
    
    # Setup signal handlers untuk graceful shutdown
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Inisialisasi MQTT
    mqtt_client = setup_mqtt()
    
    if not mqtt_client:
        logger.error("Failed to initialize MQTT client. Exiting...")
        sys.exit(1)
    
    # Inisialisasi sensor
    geophone = None
    gps = None
    geophone_thread = None
    gps_thread = None
    
    try:
        geophone = GeophonesensorADC(mqtt_client=mqtt_client)
        gps = GPSSensor(mqtt_client=mqtt_client)
        
        # Inisialisasi thread
        geophone_thread = threading.Thread(target=geophone.run, daemon=True)
        gps_thread = threading.Thread(target=gps.run, daemon=True)
        
        # Mulai thread
        logger.info("Starting sensor threads...")
        geophone_thread.start()
        gps_thread.start()
        
        # Wait for shutdown event
        while not shutdown_event.is_set():
            time.sleep(1)
        
        logger.info("Shutdown event received, stopping sensors...")
        
    except Exception as e:
        logger.error(f"Error in main: {e}")
        shutdown_event.set()
    
    finally:
        # Cleanup
        logger.info("Cleaning up...")
        
        if geophone:
            geophone.stop()
        if gps:
            gps.stop()
        
        # Wait for threads to finish (with timeout)
        if geophone_thread and geophone_thread.is_alive():
            geophone_thread.join(timeout=5)
        if gps_thread and gps_thread.is_alive():
            gps_thread.join(timeout=5)
        
        # Stop MQTT
        if mqtt_client:
            try:
                mqtt_client.loop_stop()
                mqtt_client.disconnect()
            except:
                pass
        
        logger.info("Service stopped successfully")


if __name__ == "__main__":
    main()