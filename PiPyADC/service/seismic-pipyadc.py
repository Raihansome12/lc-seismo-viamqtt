import time
import json
import serial
import pynmea2
import paho.mqtt.client as mqtt
import ssl
import sys
import logging
import os
import signal
import threading
from datetime import datetime
import certifi
from pipyadc import ADS1256
from ADS1256_definitions import *
import waveshare_config

# Setup logging untuk systemd
def setup_logging():
    # Pastikan direktori log ada
    log_dir = '/var/log/seismic-service'
    if not os.path.exists(log_dir):
        try:
            os.makedirs(log_dir, exist_ok=True)
        except PermissionError:
            # Fallback ke direktori lokal jika tidak bisa akses /var/log
            log_dir = './logs'
            os.makedirs(log_dir, exist_ok=True)
    
    # Console handler untuk semua level
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(console_formatter)
    
    # File handler hanya untuk ERROR
    log_file = os.path.join(log_dir, 'seismic-pipyadc.log')
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.INFO)
    file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_formatter)
    
    # Setup root logger
    logging.basicConfig(
        level=logging.INFO,
        handlers=[console_handler, file_handler]
    )
    
    return logging.getLogger(__name__)

# Inisialisasi logger
logger = setup_logging()

# Global flag untuk graceful shutdown
shutdown_flag = threading.Event()

def signal_handler(signum, frame):
    """Handler untuk graceful shutdown"""
    signal_name = {
        signal.SIGTERM: 'SIGTERM',
        signal.SIGINT: 'SIGINT',
        signal.SIGHUP: 'SIGHUP'
    }.get(signum, f'Signal {signum}')
    
    logger.info(f"Received {signal_name}, initiating graceful shutdown...")
    shutdown_flag.set()

def setup_signal_handlers():
    """Setup signal handlers untuk graceful shutdown"""
    try:
        signal.signal(signal.SIGTERM, signal_handler)  # systemctl stop
        signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C
        signal.signal(signal.SIGHUP, signal_handler)   # systemctl reload
        logger.info("Signal handlers registered successfully")
    except Exception as e:
        logger.error(f"Error setting up signal handlers: {e}")

# Konfigurasi untuk MQTT
MQTT_BROKER = "240fa9ad32cb44929936ab704925afa5.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
MQTT_USERNAME = "project-kuliah"
MQTT_PASSWORD = "Raihan@3012"
MQTT_CLIENT_ID = "skripsi"
MQTT_TOPIC_GEOPHONE = "sensors/geophone"
MQTT_TOPIC_GPS = "sensors/gps"

class GeophonesensorADC:
    def __init__(self):
        self.ads = ADS1256(waveshare_config)
        self.ads.drate = DRATE_50
        self.ads.pga_gain = 1
        self.ads.mux = POS_AIN0 | NEG_AIN1
        self.ads.sync()
        
        self.adc_buffer = []  # Buffer untuk menyimpan 50 data ADC
        self.buffer_size = 50
        self.sample_rate = 50  # SPS target
        
        # Tracking untuk logging setiap 1000 data
        self.total_sent_count = 0
        self.batch_start_time = time.time()
        
        logger.info("Geophone ADC initialized successfully")
    
    def read_sensor(self):
        try:
            raw_value = self.ads.read_async()
            return {
                'raw_value': raw_value,
            }
        except Exception as e:
            logger.error(f"Error reading geophone: {e}")
            return None
    
    def collect_and_send_data(self, mqtt_client):
        """Collect data dan kirim ke MQTT ketika buffer penuh"""
        # Check shutdown flag
        if shutdown_flag.is_set():
            return False
            
        sample_start_time = time.time()
        
        # Baca data ADC
        adc_data = self.read_sensor()
        if adc_data is not None:
            # Simpan ke buffer dengan timestamp
            sample_data = {
                'timestamp': datetime.now().isoformat(),
                'raw_value': adc_data['raw_value'],
            }
            
            self.adc_buffer.append(sample_data)
            
            # Jika buffer sudah penuh, kirim ke MQTT
            if len(self.adc_buffer) >= self.buffer_size:
                # Buat payload sesuai format yang diminta
                payload = {
                    "adc_counts": [sample['raw_value'] for sample in self.adc_buffer],
                    "reading_times": [sample['timestamp'] for sample in self.adc_buffer],
                }
                
                # Kirim data ke MQTT
                if mqtt_client:
                    try:
                        json_payload = json.dumps(payload)
                        mqtt_client.publish(MQTT_TOPIC_GEOPHONE, json_payload)
                        
                        # Update counter
                        self.total_sent_count += len(self.adc_buffer)
                        
                        # Log setiap 3000 data terkirim
                        if self.total_sent_count % 3000 == 0:
                            elapsed_time = time.time() - self.batch_start_time
                            actual_rate = 3000 / elapsed_time if elapsed_time > 0 else 0
                            logger.info(f"Geophone: {self.total_sent_count} total samples sent | "
                                      f"Last 3000 samples rate: {actual_rate:.2f} SPS")
                            # Reset timer untuk batch berikutnya
                            self.batch_start_time = time.time()
                            
                    except Exception as e:
                        logger.error(f"Error publishing geophone data: {e}")
                
                # Kosongkan buffer
                self.adc_buffer.clear()
        
        # Hitung berapa lama perlu tidur untuk mencapai SPS 50
        elapsed = time.time() - sample_start_time
        sleep_time = max(0, (1.0/self.sample_rate) - elapsed)
        
        if sleep_time > 0:
            time.sleep(sleep_time)
        else:
            # Jika proses terlalu lama, catat peringatan
            logger.warning(f"Geophone sampling taking too long! ({elapsed:.4f}s > {1.0/self.sample_rate:.4f}s)")
        
        return True  # Continue operation
    def cleanup(self):
        """Cleanup ADC dengan handling untuk remaining buffer"""
        try:
            # Jika masih ada data di buffer, log informasi
            if self.adc_buffer:
                logger.info(f"Cleanup: {len(self.adc_buffer)} samples remaining in buffer (not sent)")
            
            logger.info(f"Total samples collected during session: {self.total_sent_count}")
            self.ads.stop()
            logger.info("Geophone ADC cleanup completed")
        except Exception as e:
            logger.error(f"Error during geophone cleanup: {e}")


class GPSSensor:
    def __init__(self, port='/dev/serial0', baud_rate=9600):
        self.port = port
        self.baud_rate = baud_rate
        self.gps_serial = None
        logger.info(f"GPS sensor initialized with port: {port}, baud: {baud_rate}")
    
    def initialize(self):
        try:
            self.gps_serial = serial.Serial(self.port, self.baud_rate, timeout=1)
            logger.info("GPS serial connection established")
            return True
        except Exception as e:
            logger.error(f"Error initializing GPS: {e}")
            return False
    
    def read_sensor_once(self):
        """Membaca GPS sekali saja dan mengembalikan data"""
        if not self.gps_serial:
            if not self.initialize():
                return None
        
        logger.info("Reading GPS data (one time only)...")
        start_time = time.time()
        attempts = 0
        max_attempts = 30  # Maksimal 30 detik mencoba
        
        while (time.time() - start_time) < 30 and attempts < max_attempts:
            try:
                gps_data = self.gps_serial.readline().decode('ascii', errors='ignore')
                attempts += 1
                
                if gps_data.startswith('$GNGGA') or gps_data.startswith('$GPGGA'):
                    try:
                        msg = pynmea2.parse(gps_data)
                        if msg.latitude and msg.longitude:  # Pastikan ada data koordinat
                            gps_info = {
                                "latitude": msg.latitude,
                                "longitude": msg.longitude,
                                "reading_times": datetime.now().isoformat()
                            }
                            
                            logger.info(f"GPS data obtained: Lat={gps_info['latitude']}, "
                                      f"Lon={gps_info['longitude']} at {gps_info['reading_times']}")
                            return gps_info
                            
                    except pynmea2.ParseError as e:
                        logger.error(f"GPS parse error: {e}")
                        
            except Exception as e:
                logger.error(f"Error reading GPS: {e}")
                # Coba reinisialisasi koneksi serial
                self.initialize()
            
            time.sleep(0.1)  # Tunggu sebentar sebelum mencoba lagi
        
        logger.warning("Failed to get GPS data after 30 seconds")
        return None
    
    def close(self):
        """Tutup koneksi GPS"""
        if self.gps_serial:
            try:
                self.gps_serial.close()
                logger.info("GPS connection closed")
            except Exception as e:
                logger.error(f"Error closing GPS connection: {e}")


def setup_mqtt():
    """Konfigurasi MQTT dengan TLS"""
    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            logger.info("Connected to MQTT broker successfully")
        else:
            logger.error(f"Failed to connect to MQTT broker with error code: {rc}")
    
    def on_disconnect(client, userdata, rc):
        if rc != 0:
            logger.warning(f"Unexpected disconnection from MQTT broker with error code: {rc}")
        else:
            logger.info("Disconnected from MQTT broker")
    
    def on_publish(client, userdata, mid):
        logger.debug(f"Message {mid} published successfully")
    
    # Buat klien MQTT
    client = mqtt.Client(client_id=MQTT_CLIENT_ID)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_publish = on_publish
    
    # Set username dan password
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    
    # Konfigurasi TLS/SSL
    try:
        client.tls_set(
            ca_certs=certifi.where(),  # Gunakan certifi untuk CA certificates
            certfile=None, 
            keyfile=None, 
            cert_reqs=ssl.CERT_REQUIRED,
            tls_version=ssl.PROTOCOL_TLSv1_2
        )
        
        client.tls_insecure_set(False)
        logger.info("TLS configuration set successfully")
        
    except Exception as e:
        logger.error(f"Error setting up TLS: {e}")
        return None
    
    # Coba koneksi ke broker
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start()  # Mulai loop di background
        time.sleep(2)  # Tunggu sebentar untuk koneksi stabil
        logger.info("MQTT client setup completed")
        return client
    except Exception as e:
        logger.error(f"Error connecting to MQTT broker: {e}")
        return None

def main():
    logger.info("=== Seismic Monitor Service Starting ===")
    
    # Setup signal handlers untuk graceful shutdown
    setup_signal_handlers()
    
    # Inisialisasi MQTT
    mqtt_client = setup_mqtt()
    
    if not mqtt_client:
        logger.error("Failed to initialize MQTT client. Exiting...")
        return 1
    
    geophone = None
    gps = None
    
    try:
        logger.info("=== Reading GPS data once before starting geophone ===")
        gps = GPSSensor()
        gps_data = gps.read_sensor_once()
        
        if gps_data:
            logger.info(f"GPS data obtained successfully: Lat={gps_data['latitude']}, Lon={gps_data['longitude']}")
            
            # Kirim GPS data ke MQTT
            try:
                payload = json.dumps(gps_data)
                mqtt_client.publish(MQTT_TOPIC_GPS, payload)
                logger.info("GPS data sent to MQTT successfully")
            except Exception as e:
                logger.error(f"Error publishing GPS data: {e}")
        else:
            logger.warning("Could not obtain GPS data, continuing with geophone only")
        
        # Tutup koneksi GPS setelah pembacaan
        gps.close()
        time.sleep(2)  # Tunggu sebentar
        
        # === Mulai pembacaan geophone ===
        logger.info("=== Starting geophone data collection ===")
        geophone = GeophonesensorADC()
        
        logger.info("Geophone data collection started. Service running in background...")
        
        # Loop utama dengan check shutdown flag
        while not shutdown_flag.is_set():
            if not geophone.collect_and_send_data(mqtt_client):
                break
                
            # Check shutdown flag lebih sering untuk responsive shutdown
            if shutdown_flag.wait(timeout=0.001):  # 1ms timeout
                break
        
        logger.info("Main loop terminated due to shutdown signal")
        
    except KeyboardInterrupt:
        logger.info("Program stopped by user interrupt (Ctrl+C)")
    
    except Exception as e:
        logger.error(f"Unexpected error in main: {e}", exc_info=True)
        return 1
    
    finally:
        logger.info("Shutting down service...")
        
        # Cleanup dengan timeout untuk avoid hanging
        cleanup_timeout = 10  # seconds
        cleanup_start = time.time()
        
        # Cleanup geophone
        if geophone:
            try:
                geophone.cleanup()
            except Exception as e:
                logger.error(f"Error during geophone cleanup: {e}")
        
        # Cleanup GPS
        if gps:
            try:
                gps.close()
            except Exception as e:
                logger.error(f"Error during GPS cleanup: {e}")
        
        # Cleanup MQTT
        if mqtt_client:
            try:
                mqtt_client.loop_stop()
                mqtt_client.disconnect()
                # Wait a bit for clean disconnect
                time.sleep(1)
            except Exception as e:
                logger.error(f"Error during MQTT cleanup: {e}")
        
        cleanup_elapsed = time.time() - cleanup_start
        logger.info(f"Service shutdown completed in {cleanup_elapsed:.2f} seconds")
        
        return 0


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)