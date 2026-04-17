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
from datetime import datetime, timezone
import certifi
from collections import deque
import statistics
import logging
import sys
import signal


# Setup logging untuk systemd service
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),  # Log ke stdout untuk systemd
        logging.FileHandler('/var/log/sensor_service.log')  # Backup log file
    ]
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

class GeophonesensorADC:
    def __init__(self, mqtt_client=None):
        self.adc = ADS1256.ADS1256()
        if self.adc.ADS1256_init() == -1:
            raise Exception("ADS1256 initialization failed")
        
        # Konfigurasi ADC dengan SPS 50 dan gain 1
        sps = ADS1256.ADS1256_DRATE_E['ADS1256_50SPS']
        gain = ADS1256.ADS1256_GAIN_E['ADS1256_GAIN_1']
        self.adc.ADS1256_ConfigADC(gain, sps)
        self.adc.ADS1256_SetMode(1)
        
        self.running = False
        self.mqtt_client = mqtt_client
        
        # Buffer untuk menyimpan data sampling
        self.sample_buffer = deque(maxlen=10000)
        self.buffer_lock = threading.Lock()
        
        # Konfigurasi untuk publish rate control
        self.TARGET_SPS = 50
        self.SAMPLES_PER_PUBLISH = 50  # Publish 50 sampel setiap 1 detik
        self.PUBLISH_INTERVAL = 1.0    # 1 detik
        
        # Statistik sederhana untuk monitoring internal
        self.total_samples = 0
        self.total_published = 0
        self.start_time = None
    
    def sampling_thread(self):
        """Thread untuk sampling data ADC"""
        logger.info("Starting geophone sampling thread")
        self.start_time = time.time()
        
        try:
            while self.running:
                try:
                    adc_value = self.adc.ADS1256_GetChannalValue(0)
                    current_time = time.time()
                    
                    data_point = {
                        'adc_value': adc_value,
                        'timestamp': current_time
                    }
                    
                    with self.buffer_lock:
                        self.sample_buffer.append(data_point)
                    
                    self.total_samples += 1
                    
                    # Log setiap 5000 sampel untuk monitoring
                    if self.total_samples % 5000 == 0:
                        elapsed = current_time - self.start_time
                        rate = self.total_samples / elapsed
                        logger.info(f"Geophone sampling: {self.total_samples} samples, "
                                  f"Rate: {rate:.2f} SPS, Buffer: {len(self.sample_buffer)}")
                    
                    # Minimal delay
                    time.sleep(0.001)
                    
                except Exception as e:
                    logger.error(f"Error in geophone sampling: {e}")
                    time.sleep(0.01)
                    
        except Exception as e:
            logger.error(f"Fatal error in geophone sampling thread: {e}")
        finally:
            logger.info("Geophone sampling thread stopped")
    
    def publish_thread(self):
        """Thread untuk publish data dengan payload sederhana"""
        logger.info("Starting geophone publish thread")
        
        try:
            while self.running:
                publish_start_time = time.time()
                
                # Ambil data dari buffer
                samples_to_send = []
                with self.buffer_lock:
                    for _ in range(min(self.SAMPLES_PER_PUBLISH, len(self.sample_buffer))):
                        if self.sample_buffer:
                            samples_to_send.append(self.sample_buffer.popleft())
                
                # Jika ada data untuk dikirim
                if samples_to_send:
                    # Payload sederhana untuk production
                    adc_counts = [sample['adc_value'] for sample in samples_to_send]
                    reading_times = datetime.fromtimestamp(
                        samples_to_send[0]['timestamp'], tz=timezone.utc
                    ).isoformat()
                    
                    payload = {
                        "adc_counts": adc_counts,
                        "reading_times": reading_times
                    }
                    
                    # Kirim via MQTT
                    if self.mqtt_client:
                        try:
                            json_payload = json.dumps(payload)
                            result = self.mqtt_client.publish(MQTT_TOPIC_GEOPHONE, json_payload)
                            
                            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                                self.total_published += len(adc_counts)
                                
                                # Log setiap 100 publish untuk monitoring
                                if self.total_published % 5000 == 0:
                                    logger.info(f"Geophone published: {self.total_published} samples total")
                                      
                            else:
                                logger.error(f"Geophone MQTT publish failed: {result.rc}")
                                
                        except Exception as e:
                            logger.error(f"Error publishing geophone data: {e}")
                else:
                    logger.warning("No geophone samples available in buffer")
                
                # Tunggu sampai tepat 1 detik dari awal publish cycle
                elapsed_time = time.time() - publish_start_time
                sleep_time = max(0, self.PUBLISH_INTERVAL - elapsed_time)
                
                if sleep_time > 0:
                    time.sleep(sleep_time)
                else:
                    logger.warning(f"Geophone publish cycle took too long ({elapsed_time:.3f}s)")
                    
        except Exception as e:
            logger.error(f"Fatal error in geophone publish thread: {e}")
        finally:
            logger.info("Geophone publish thread stopped")
    
    def run(self):
        """Jalankan geophone sensor"""
        self.running = True
        
        sampling_thread = threading.Thread(target=self.sampling_thread, name="GeophoneSampling")
        publish_thread = threading.Thread(target=self.publish_thread, name="GeoPhonePublish")
        
        sampling_thread.daemon = True
        publish_thread.daemon = True
        
        sampling_thread.start()
        publish_thread.start()
        
        try:
            sampling_thread.join()
            publish_thread.join()
        except Exception as e:
            logger.error(f"Error waiting for geophone threads: {e}")
        finally:
            GPIO.cleanup()
            logger.info("Geophone threads stopped")
    
    def stop(self):
        """Stop geophone sensor"""
        logger.info("Stopping geophone sensor")
        self.running = False

class GPSSensor:
    def __init__(self, port='/dev/serial0', baud_rate=9600, mqtt_client=None):
        self.port = port
        self.baud_rate = baud_rate
        self.gps_serial = None
        self.running = False
        self.mqtt_client = mqtt_client
        
        # Buffer untuk GPS data
        self.gps_buffer = deque(maxlen=100)
        self.buffer_lock = threading.Lock()
        
        # GPS publish setiap 5 menit
        self.GPS_PUBLISH_INTERVAL = 300  # 5 menit
        
        # Statistik sederhana
        self.total_readings = 0
        self.total_published = 0
    
    def initialize(self):
        try:
            self.gps_serial = serial.Serial(self.port, self.baud_rate, timeout=1)
            logger.info("GPS serial port initialized")
            return True
        except Exception as e:
            logger.error(f"Error initializing GPS: {e}")
            return False
    
    def gps_sampling_thread(self):
        """Thread untuk sampling GPS data"""
        logger.info("Starting GPS sampling thread")
        
        try:
            while self.running:
                if not self.gps_serial:
                    if not self.initialize():
                        time.sleep(5)
                        continue
                
                try:
                    gps_data = self.gps_serial.readline().decode('ascii', errors='ignore')
                    if gps_data.startswith('$GNGGA') or gps_data.startswith('$GPGGA'):
                        try:
                            msg = pynmea2.parse(gps_data)
                            if msg.latitude and msg.longitude:
                                data_point = {
                                    "latitude": msg.latitude,
                                    "longitude": msg.longitude,
                                    "timestamp": time.time()
                                }
                                
                                with self.buffer_lock:
                                    self.gps_buffer.append(data_point)
                                
                                self.total_readings += 1
                                
                                # Log setiap 100 readings
                                if self.total_readings % 100 == 0:
                                    logger.info(f"GPS readings: {self.total_readings} total")
                                    
                        except pynmea2.ParseError as e:
                            logger.error(f"GPS parse error: {e}")
                            
                except Exception as e:
                    logger.error(f"Error reading GPS: {e}")
                    self.initialize()
                    
                time.sleep(1)  # GPS sampling setiap detik
                
        except Exception as e:
            logger.error(f"Error in GPS sampling thread: {e}")
        finally:
            if self.gps_serial:
                self.gps_serial.close()
            logger.info("GPS sampling thread stopped")
    
    def gps_publish_thread(self):
        """Thread untuk publish GPS data setiap 5 menit"""
        logger.info("Starting GPS publish thread")
        
        try:
            while self.running:
                # Ambil data terbaru dari buffer
                latest_data = None
                with self.buffer_lock:
                    if self.gps_buffer:
                        latest_data = self.gps_buffer[-1]
                
                if latest_data and self.mqtt_client:
                    # Payload sederhana untuk production
                    payload = {
                        "latitude": latest_data["latitude"],
                        "longitude": latest_data["longitude"],
                        "reading_times": datetime.fromtimestamp(
                            latest_data["timestamp"], tz=timezone.utc
                        ).isoformat()
                    }
                    
                    try:
                        json_payload = json.dumps(payload)
                        result = self.mqtt_client.publish(MQTT_TOPIC_GPS, json_payload)
                        
                        if result.rc == mqtt.MQTT_ERR_SUCCESS:
                            self.total_published += 1
                            logger.info(f"GPS published: Lat={latest_data['latitude']:.6f}, "
                                      f"Lon={latest_data['longitude']:.6f}")
                        else:
                            logger.error(f"GPS MQTT publish failed: {result.rc}")
                            
                    except Exception as e:
                        logger.error(f"Error publishing GPS data: {e}")
                        
                else:
                    logger.warning("No GPS data available for publish")
                
                # Sleep dengan kemampuan early exit
                for _ in range(self.GPS_PUBLISH_INTERVAL):
                    if not self.running:
                        break
                    time.sleep(1)
                    
        except Exception as e:
            logger.error(f"Error in GPS publish thread: {e}")
        finally:
            logger.info("GPS publish thread stopped")
    
    def run(self):
        self.running = True
        
        sampling_thread = threading.Thread(target=self.gps_sampling_thread, name="GPSSampling")
        publish_thread = threading.Thread(target=self.gps_publish_thread, name="GPSPublish")
        
        sampling_thread.daemon = True
        publish_thread.daemon = True
        
        sampling_thread.start()
        publish_thread.start()
        
        try:
            sampling_thread.join()
            publish_thread.join()
        except Exception as e:
            logger.error(f"Error in GPS threads: {e}")
        finally:
            logger.info("GPS threads stopped")
    
    def stop(self):
        logger.info("Stopping GPS sensor")
        self.running = False

def setup_mqtt():
    """Setup MQTT client dengan reconnection handling"""
    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            logger.info("Connected to MQTT broker")
        else:
            logger.error(f"Failed to connect to MQTT broker with error code: {rc}")
    
    def on_disconnect(client, userdata, rc):
        logger.warning(f"Disconnected from MQTT broker with error code: {rc}")
        # Automatic reconnection akan dihandle oleh paho-mqtt
    
    def on_publish(client, userdata, mid):
        # Optional: bisa digunakan untuk tracking publish success
        pass
    
    client = mqtt.Client(client_id=MQTT_CLIENT_ID)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_publish = on_publish
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    
    # Enable automatic reconnection
    client.reconnect_delay_set(min_delay=1, max_delay=120)
    
    try:
        client.tls_set(
            ca_certs=certifi.where(),
            certfile=None, 
            keyfile=None, 
            cert_reqs=ssl.CERT_REQUIRED,
            tls_version=ssl.PROTOCOL_TLSv1_2
        )
        client.tls_insecure_set(False)
        
    except Exception as e:
        logger.error(f"Error setting up TLS: {e}")
        return None
    
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start()
        time.sleep(2)
        return client
    except Exception as e:
        logger.error(f"Error connecting to MQTT broker: {e}")
        return None

class SensorService:
    """Main service class untuk systemd"""
    def __init__(self):
        self.mqtt_client = None
        self.geophone = None
        self.gps = None
        self.running = False
        
        # Setup signal handlers untuk graceful shutdown
        signal.signal(signal.SIGTERM, self.signal_handler)
        signal.signal(signal.SIGINT, self.signal_handler)
    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.stop()
    
    def start(self):
        """Start the sensor service"""
        logger.info("Starting sensor service...")
        
        # Setup MQTT
        self.mqtt_client = setup_mqtt()
        if not self.mqtt_client:
            logger.error("Failed to initialize MQTT client. Exiting...")
            return False
        
        try:
            # Initialize sensors
            self.geophone = GeophonesensorADC(mqtt_client=self.mqtt_client)
            self.gps = GPSSensor(mqtt_client=self.mqtt_client)
            
            # Start sensor threads
            geophone_thread = threading.Thread(target=self.geophone.run, name="GeoPhone")
            gps_thread = threading.Thread(target=self.gps.run, name="GPS")
            
            self.running = True
            
            logger.info("Starting sensor threads...")
            geophone_thread.start()
            gps_thread.start()
            
            # Keep service running
            try:
                while self.running:
                    time.sleep(1)
            except KeyboardInterrupt:
                logger.info("Service interrupted by user")
            
            # Wait for threads to complete
            logger.info("Stopping sensor threads...")
            if self.geophone:
                self.geophone.stop()
            if self.gps:
                self.gps.stop()
            
            geophone_thread.join(timeout=10)
            gps_thread.join(timeout=10)
            
            return True
            
        except Exception as e:
            logger.error(f"Error in sensor service: {e}")
            return False
        
        finally:
            self.cleanup()
    
    def stop(self):
        """Stop the sensor service"""
        logger.info("Stopping sensor service...")
        self.running = False
        
        if self.geophone:
            self.geophone.stop()
        if self.gps:
            self.gps.stop()
    
    def cleanup(self):
        """Cleanup resources"""
        if self.mqtt_client:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
        
        logger.info("Sensor service stopped")

def main():
    """Main function untuk systemd service"""
    logger.info("Sensor Service Starting...")
    
    service = SensorService()
    success = service.start()
    
    if success:
        logger.info("Sensor service completed successfully")
        sys.exit(0)
    else:
        logger.error("Sensor service failed")
        sys.exit(1)

if __name__ == "__main__":
    main()