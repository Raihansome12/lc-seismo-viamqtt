import time
import json
import serial
import pynmea2
import paho.mqtt.client as mqtt
import ssl
from datetime import datetime
import certifi
from pipyadc import ADS1256
from ADS1256_definitions import *
import waveshare_config

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
    
    def read_sensor(self):
        try:
            raw_value = self.ads.read_async()
            return {
                'raw_value': raw_value,
            }
        except Exception as e:
            print(f"Error reading geophone: {e}")
            return None
    
    def collect_and_send_data(self, mqtt_client):
        """Collect data dan kirim ke MQTT ketika buffer penuh"""
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
                        print(f"Geophone: Sent {len(self.adc_buffer)}")
                    except Exception as e:
                        print(f"Error publishing geophone data: {e}")
                
                # Kosongkan buffer
                self.adc_buffer.clear()
        
        # Hitung berapa lama perlu tidur untuk mencapai SPS 50
        elapsed = time.time() - sample_start_time
        sleep_time = max(0, (1.0/self.sample_rate) - elapsed)
        
        if sleep_time > 0:
            time.sleep(sleep_time)
        else:
            # Jika proses terlalu lama, catat peringatan
            print(f"WARNING: Geophone sampling taking too long! ({elapsed:.4f}s > {1.0/self.sample_rate:.4f}s)")
    
    def cleanup(self):
        """Cleanup ADC"""
        self.ads.stop()


# Konfigurasi untuk GPS (dibaca sekali di awal)
class GPSSensor:
    def __init__(self, port='/dev/serial0', baud_rate=9600):
        self.port = port
        self.baud_rate = baud_rate
        self.gps_serial = None
    
    def initialize(self):
        try:
            self.gps_serial = serial.Serial(self.port, self.baud_rate, timeout=1)
            return True
        except Exception as e:
            print(f"Error initializing GPS: {e}")
            return False
    
    def read_sensor_once(self):
        """Membaca GPS sekali saja dan mengembalikan data"""
        if not self.gps_serial:
            if not self.initialize():
                return None
        
        print("Reading GPS data (one time only)...")
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
                            
                            print(f"GPS: Lat={gps_info['latitude']}, Lon={gps_info['longitude']} at {gps_info['reading_times']}")
                            return gps_info
                            
                    except pynmea2.ParseError as e:
                        print(f"GPS parse error: {e}")
                        
            except Exception as e:
                print(f"Error reading GPS: {e}")
                # Coba reinisialisasi koneksi serial
                self.initialize()
            
            time.sleep(0.1)  # Tunggu sebentar sebelum mencoba lagi
        
        print("Failed to get GPS data after 30 seconds")
        return None
    
    def close(self):
        """Tutup koneksi GPS"""
        if self.gps_serial:
            self.gps_serial.close()
            print("GPS connection closed")


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
        client.tls_set(
            #ca_certs=CA_CERT_PATH,  # Path ke CA certificate
            ca_certs=certifi.where(),  # Gunakan certifi untuk CA certificates
            certfile=None, 
            keyfile=None, 
            cert_reqs=ssl.CERT_REQUIRED,
            tls_version=ssl.PROTOCOL_TLSv1_2
        )
        
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

def main():
    # Inisialisasi MQTT
    mqtt_client = setup_mqtt()
    
    if not mqtt_client:
        print("Failed to initialize MQTT client. Exiting...")
        return
    
    geophone = None
    gps = None
    
    try:
        print("=== Reading GPS data once before starting geophone ===")
        gps = GPSSensor()
        gps_data = gps.read_sensor_once()
        
        if gps_data:
            print(f"GPS data obtained successfully: Lat={gps_data['latitude']}, Lon={gps_data['longitude']}")
            
            # Kirim GPS data ke MQTT
            try:
                payload = json.dumps(gps_data)
                mqtt_client.publish(MQTT_TOPIC_GPS, payload)
                print("GPS data sent to MQTT")
            except Exception as e:
                print(f"Error publishing GPS data: {e}")
        else:
            print("Warning: Could not obtain GPS data, continuing with geophone only")
        
        # Tutup koneksi GPS setelah pembacaan
        gps.close()
        time.sleep(2)  # Tunggu sebentar
        
        # === Mulai pembacaan geophone ===
        print("=== Starting geophone data collection ===")
        geophone = GeophonesensorADC()
        
        samples_collected = 0
        start_time = time.time()
        
        print("Press Ctrl+C to stop the program...")
        
        # Loop utama tanpa threading
        while True:
            geophone.collect_and_send_data(mqtt_client)
            samples_collected += 1
            
            # Print statistik setiap 250 samples (5 detik pada 50 SPS)
            if samples_collected % 250 == 0:
                elapsed_time = time.time() - start_time
                actual_rate = samples_collected / elapsed_time if elapsed_time > 0 else 0
                print(f"Statistics: {samples_collected} samples collected | Actual rate: {actual_rate:.2f} SPS")
        
    except KeyboardInterrupt:
        print("\nProgram dihentikan oleh pengguna")
    
    except Exception as e:
        print(f"Error in main: {e}")
    
    finally:
        # Cleanup
        if geophone:
            geophone.cleanup()
        
        if gps:
            gps.close()
            
        if mqtt_client:
            mqtt_client.loop_stop()
            mqtt_client.disconnect()
        
        print("Program selesai.")


if __name__ == "__main__":
    main()