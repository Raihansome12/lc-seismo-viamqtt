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


# Konfigurasi untuk MQTT
MQTT_BROKER = "240fa9ad32cb44929936ab704925afa5.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
MQTT_USERNAME = "project-kuliah"
MQTT_PASSWORD = "Raihan@3012"
MQTT_CLIENT_ID = "skripsi"
MQTT_TOPIC_GEOPHONE = "sensors/geophone"
MQTT_TOPIC_GPS = "sensors/gps"
# TLS Configuration
CA_CERT_PATH = "./frontend-alb-console-portal-euc1-aws-hivemq-cloud.pem"

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
            print(f"Error reading geophone: {e}")
            return None
    
    def run(self):
        self.running = True
        sample_counter = 0
        try:
            while self.running:
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
                                print(f"Geophone: Sent {len(self.adc_buffer)} samples at {timestamp}")
                            except Exception as e:
                                print(f"Error publishing geophone data: {e}")
                        
                        # Kosongkan buffer
                        self.adc_buffer.clear()
                
                # Hitung berapa lama perlu tidur untuk mencapai SPS 50
                elapsed = time.time() - start_time
                sleep_time = max(0, (1.0/50) - elapsed)  # 50 SPS = 0.02 detik per sampel
                
                if sleep_time > 0:
                    time.sleep(sleep_time)
                else:
                    # Jika proses terlalu lama, catat peringatan
                    print(f"WARNING: Geophone sampling taking too long! ({elapsed:.4f}s > 0.02s)")
        
        except Exception as e:
            print(f"Error in geophone thread: {e}")
        finally:
            GPIO.cleanup()
            print("Geophone thread stopped")
    
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
            print(f"Error initializing GPS: {e}")
            return False
    
    def read_sensor(self):
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
                        if msg.latitude and msg.longitude:  # Pastikan ada data koordinat
                            return {
                                "latitude": msg.latitude,
                                "longitude": msg.longitude,
                                "reading_times": datetime.now().isoformat()
                            }
                    except pynmea2.ParseError as e:
                        print(f"GPS parse error: {e}")
            except Exception as e:
                print(f"Error reading GPS: {e}")
                # Coba reinisialisasi koneksi serial
                self.initialize()
        
        return None
    
    def run(self):
        self.running = True
        try:
            while self.running:
                data = self.read_sensor()
                if data:
                    # Kirim data ke MQTT jika klien tersedia
                    if self.mqtt_client:
                        try:
                            payload = json.dumps(data)
                            self.mqtt_client.publish(MQTT_TOPIC_GPS, payload)
                            print(f"GPS: Lat={data['latitude']}, Lon={data['longitude']} at {data['reading_times']}")
                        except Exception as e:
                            print(f"Error publishing GPS data: {e}")
                else:
                    print("Failed to get GPS data")
                
                # Tunggu 5 menit sebelum pembacaan berikutnya
                # Tetapi kita perlu memecah waktu tidur untuk memungkinkan penghentian dengan cepat
                for _ in range(300):  # 5 menit = 300 detik
                    if not self.running:
                        break
                    time.sleep(1)
        except Exception as e:
            print(f"Error in GPS thread: {e}")
        finally:
            if self.gps_serial:
                self.gps_serial.close()
            print("GPS thread stopped")
    
    def stop(self):
        self.running = False


# Konfigurasi MQTT dengan TLS
def setup_mqtt():
    # Callback saat terhubung
    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            print("Connected to MQTT broker")
        else:
            print(f"Failed to connect to MQTT broker with error code: {rc}")
    
    # Callback saat terputus
    def on_disconnect(client, userdata, rc):
        print(f"Disconnected from MQTT broker with error code: {rc}")
    
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
            # ca_certs=certifi.where(),  # Menggunakan certifi untuk CA certificates
            ca_certs=CA_CERT_PATH,  # Path ke CA certificate
            certfile=None, 
            keyfile=None, 
            cert_reqs=ssl.CERT_REQUIRED,
            tls_version=ssl.PROTOCOL_TLSv1_2
        )
        
        # Untuk HiveMQ Cloud, biasanya tidak perlu verifikasi hostname
        client.tls_insecure_set(False)
        
    except Exception as e:
        print(f"Error setting up TLS: {e}")
        return None
    
    # Coba koneksi ke broker
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start()  # Mulai loop di background
        time.sleep(2)  # Tunggu sebentar untuk koneksi stabil
        return client
    except Exception as e:
        print(f"Error connecting to MQTT broker: {e}")
        return None


# Fungsi utama
def main():
    # Inisialisasi MQTT
    mqtt_client = setup_mqtt()
    
    if not mqtt_client:
        print("Failed to initialize MQTT client. Exiting...")
        return
    
    # Inisialisasi sensor
    try:
        geophone = GeophonesensorADC(mqtt_client=mqtt_client)
        gps = GPSSensor(mqtt_client=mqtt_client)
        
        # Inisialisasi thread
        geophone_thread = threading.Thread(target=geophone.run)
        gps_thread = threading.Thread(target=gps.run)
        
        # Mulai thread
        print("Starting sensor threads...")
        geophone_thread.start()
        gps_thread.start()
        
        # Tunggu keyboard interrupt
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nProgram dihentikan oleh pengguna")
        
        # Hentikan thread
        print("Stopping sensor threads...")
        geophone.stop()
        gps.stop()
        
        # Tunggu thread selesai
        geophone_thread.join()
        gps_thread.join()
        
        # Berhenti MQTT
        if mqtt_client:
            mqtt_client.loop_stop()
            mqtt_client.disconnect()
        
    except Exception as e:
        print(f"Error in main: {e}")
    
    finally:
        print("Program selesai.")


if __name__ == "__main__":
    main()