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
import sys
import signal
import logging
import os


# Setup logging untuk systemd
# Console handler untuk semua level
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(console_formatter)

# File handler hanya untuk ERROR
file_handler = logging.FileHandler('/var/log/seismic-service/sensor_monitor.log')
file_handler.setLevel(logging.ERROR)
file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(file_formatter)

# Setup root logger
logging.basicConfig(
    level=logging.INFO,
    handlers=[console_handler, file_handler]
)
logger = logging.getLogger(__name__)

# Konfigurasi untuk MQTT
MQTT_BROKER = "240fa9ad32cb44929936ab704925afa5.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
MQTT_USERNAME = "project-kuliah"
MQTT_PASSWORD = "Raihan@3012"
MQTT_CLIENT_ID = "skripsi"
MQTT_TOPIC_GEOPHONE = "sensors/geophone"
MQTT_TOPIC_GPS = "sensors/gps"

# Path ke certificate - disesuaikan untuk systemd
# BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# CA_CERT_PATH = os.path.join(BASE_DIR, "frontend-alb-console-portal-euc1-aws-hivemq-cloud.pem")

# Event untuk sinkronisasi GPS
gps_ready_event = threading.Event()
program_stop_event = threading.Event()

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
        logger.info("Geophone: Waiting for GPS to get satellite fix...")
        
        # Tunggu sampai GPS mendapat fix satelit atau program dihentikan
        while not gps_ready_event.is_set() and not program_stop_event.is_set():
            time.sleep(0.1)
        
        if program_stop_event.is_set():
            logger.info("Geophone: Program stopped before GPS ready")
            return
            
        logger.info("Geophone: GPS ready, starting data collection...")
        sample_counter = 0
        
        try:
            while self.running and not program_stop_event.is_set():
                start_time = time.time()
                
                # Baca data ADC
                adc_value = self.read_sensor()
                if adc_value is not None:
                    self.adc_buffer.append(adc_value)
                    sample_counter += 1
                    
                    # Jika buffer sudah penuh (25 data), kirim ke MQTT
                    if len(self.adc_buffer) >= self.buffer_size:
                        timestamp = datetime.now().isoformat()
                        
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
                sleep_time = max(0, (1.0/40) - elapsed)  # 50 SPS = 0.025 detik per sampel
                
                if sleep_time > 0:
                    time.sleep(sleep_time)
                else:
                    # Jika proses terlalu lama, catat peringatan
                    logger.warning(f"Geophone sampling taking too long! ({elapsed:.4f}s > 0.025s)")
        
        except Exception as e:
            logger.error(f"Error in geophone thread: {e}")
        finally:
            GPIO.cleanup()
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
        self.gps_fix_status = False
    
    def initialize(self):
        try:
            self.gps_serial = serial.Serial(self.port, self.baud_rate, timeout=1)
            return True
        except Exception as e:
            logger.error(f"Error initializing GPS: {e}")
            return False
    
    def check_gps_fix(self):
        """Cek apakah GPS sudah mendapat fix satelit"""
        if not self.gps_serial:
            if not self.initialize():
                return False
        
        # Coba baca beberapa kali untuk mendapatkan status fix
        attempts = 0
        max_attempts = 20  # Maksimal 20 kali percobaan per check
        
        while attempts < max_attempts:
            try:
                gps_data = self.gps_serial.readline().decode('ascii', errors='ignore')
                
                # Cek pesan GGA untuk status fix
                if gps_data.startswith('$GNGGA') or gps_data.startswith('$GPGGA'):
                    try:
                        msg = pynmea2.parse(gps_data)
                        # Fix quality: 0=tidak valid, 1=GPS fix, 2=DGPS fix
                        if hasattr(msg, 'gps_qual') and msg.gps_qual and int(msg.gps_qual) > 0:
                            if msg.latitude and msg.longitude:
                                return True
                    except (pynmea2.ParseError, ValueError) as e:
                        pass  # Lanjutkan mencoba
                
                # Cek pesan GSA untuk status fix 3D
                elif gps_data.startswith('$GNGSA') or gps_data.startswith('$GPGSA'):
                    try:
                        msg = pynmea2.parse(gps_data)
                        # Mode fix: 1=no fix, 2=2D fix, 3=3D fix
                        if hasattr(msg, 'mode_fix_type') and msg.mode_fix_type and int(msg.mode_fix_type) >= 2:
                            return True
                    except (pynmea2.ParseError, ValueError) as e:
                        pass  # Lanjutkan mencoba
                
                attempts += 1
                
            except Exception as e:
                logger.error(f"Error checking GPS fix: {e}")
                self.initialize()
                attempts += 1
        
        return False
    
    def read_sensor(self):
        """Baca data koordinat GPS (hanya jika sudah ada fix)"""
        if not self.gps_serial:
            if not self.initialize():
                return None
        
        # Kita akan membaca beberapa baris untuk mendapatkan GNGGA/GPGGA
        start_time = time.time()
        while (time.time() - start_time) < 5:  # Timeout setelah 5 detik
            try:
                gps_data = self.gps_serial.readline().decode('ascii', errors='ignore')
                if gps_data.startswith('$GNGGA') or gps_data.startswith('$GPGGA'):
                    try:
                        msg = pynmea2.parse(gps_data)
                        if msg.latitude and msg.longitude and hasattr(msg, 'gps_qual') and msg.gps_qual and int(msg.gps_qual) > 0:
                            return {
                                "latitude": msg.latitude,
                                "longitude": msg.longitude,
                                "reading_times": datetime.now().isoformat()
                            }
                    except (pynmea2.ParseError, ValueError) as e:
                        logger.error(f"GPS parse error: {e}")
            except Exception as e:
                logger.error(f"Error reading GPS: {e}")
                # Coba reinisialisasi koneksi serial
                self.initialize()
        
        return None
    
    def wait_for_gps_fix(self):
        """Tunggu sampai GPS mendapat fix satelit"""
        logger.info("GPS: Waiting for satellite fix...")
        fix_check_interval = 10  # Cek setiap 10 detik
        
        while not program_stop_event.is_set():
            if self.check_gps_fix():
                logger.info("GPS: Satellite fix acquired!")
                self.gps_fix_status = True
                gps_ready_event.set()  # Beritahu thread lain bahwa GPS sudah siap
                return True
            else:
                logger.info("GPS: No satellite fix yet, retrying in 10 seconds...")
                # Tidur dengan interval kecil untuk memungkinkan penghentian cepat
                for _ in range(fix_check_interval):
                    if program_stop_event.is_set():
                        return False
                    time.sleep(1)
        
        return False
    
    def run(self):
        self.running = True
        
        # Tunggu GPS mendapat fix satelit
        if not self.wait_for_gps_fix():
            logger.info("GPS: Program stopped before getting satellite fix")
            return
        
        logger.info("GPS: Starting data collection...")
        
        try:
            while self.running and not program_stop_event.is_set():
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
                    logger.warning("GPS: Lost satellite fix, checking status...")
                    # Jika kehilangan fix, cek status dan tunggu lagi jika perlu
                    if not self.check_gps_fix():
                        logger.warning("GPS: Satellite fix lost! Stopping all data transmission...")
                        gps_ready_event.clear()  # Reset event
                        self.gps_fix_status = False
                        # Tunggu fix lagi
                        if not self.wait_for_gps_fix():
                            break
                
                # Tunggu 5 menit sebelum pembacaan berikutnya
                # Tetapi kita perlu memecah waktu tidur untuk memungkinkan penghentian dengan cepat
                for _ in range(300):  # 5 menit = 300 detik
                    if not self.running or program_stop_event.is_set():
                        break
                    time.sleep(1)
                    
        except Exception as e:
            logger.error(f"Error in GPS thread: {e}")
        finally:
            if self.gps_serial:
                self.gps_serial.close()
            logger.info("GPS thread stopped")
    
    def stop(self):
        self.running = False


# Konfigurasi MQTT dengan TLS
def setup_mqtt():
    # Callback saat terhubung
    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            logger.info("Connected to MQTT broker")
        else:
            logger.error(f"Failed to connect to MQTT broker with error code: {rc}")
    
    # Callback saat terputus
    def on_disconnect(client, userdata, rc):
        logger.warning(f"Disconnected from MQTT broker with error code: {rc}")
    
    # Buat klien MQTT
    client = mqtt.Client(client_id=MQTT_CLIENT_ID)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    
    # Set username dan password
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    
    # Konfigurasi TLS/SSL
    try:
        # Untuk HiveMQ Cloud, biasanya menggunakan TLS versi 1.2
        client.tls_set(
            #ca_certs=CA_CERT_PATH,  # Path ke CA certificate
            ca_certs=certifi.where(),  # Gunakan certifi untuk CA bundle
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
        time.sleep(2)  # Tunggu sebentar untuk koneksi stabil
        return client
    except Exception as e:
        logger.error(f"Error connecting to MQTT broker: {e}")
        return None


# Signal handler untuk graceful shutdown
def signal_handler(signum, frame):
    logger.info(f"Received signal {signum}, shutting down gracefully...")
    program_stop_event.set()


# Fungsi utama
def main():
    global program_stop_event
    
    # Setup signal handlers untuk graceful shutdown
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    logger.info("Starting Sensor Monitor Service...")
    
    # Inisialisasi MQTT
    mqtt_client = setup_mqtt()
    
    if not mqtt_client:
        logger.error("Failed to initialize MQTT client. Exiting...")
        return 1
    
    # Inisialisasi sensor
    try:
        geophone = GeophonesensorADC(mqtt_client=mqtt_client)
        gps = GPSSensor(mqtt_client=mqtt_client)
        
        # Inisialisasi thread
        geophone_thread = threading.Thread(target=geophone.run)
        gps_thread = threading.Thread(target=gps.run)
        
        # Mulai thread
        logger.info("Starting sensor threads...")
        logger.info("Note: Geophone data will only be sent after GPS gets satellite fix")
        gps_thread.start()  # GPS dimulai dulu untuk mendapat fix
        geophone_thread.start()  # Geophone akan menunggu GPS ready
        
        # Tunggu sampai program dihentikan
        while not program_stop_event.is_set():
            time.sleep(1)
        
        # Hentikan thread
        logger.info("Stopping sensor threads...")
        geophone.stop()
        gps.stop()
        
        # Tunggu thread selesai
        geophone_thread.join(timeout=10)
        gps_thread.join(timeout=10)
        
        # Berhenti MQTT
        if mqtt_client:
            mqtt_client.loop_stop()
            mqtt_client.disconnect()
        
        logger.info("Service stopped successfully")
        return 0
        
    except Exception as e:
        logger.error(f"Error in main: {e}")
        return 1
    
    finally:
        program_stop_event.set()


if __name__ == "__main__":
    sys.exit(main())