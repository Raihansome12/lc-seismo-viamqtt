import time
import json
import serial
import pynmea2
import paho.mqtt.client as mqtt
import ssl
from datetime import datetime, timezone
import certifi
from pipyadc import ADS1256
from ADS1256_definitions import *
import waveshare_config
import numpy as np
from obspy import Stream, Trace, UTCDateTime
from obspy.core.stats import Stats
import pymysql
import os
import atexit
import signal
import sys
import io

# Konfigurasi untuk MQTT
MQTT_BROKER = "240fa9ad32cb44929936ab704925afa5.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
MQTT_USERNAME = "project-kuliah"
MQTT_PASSWORD = "Raihan@3012"
MQTT_CLIENT_ID = "skripsi"
MQTT_TOPIC_GEOPHONE = "sensors/geophone"
MQTT_TOPIC_GPS = "sensors/gps"

# Konfigurasi Database MySQL (menggunakan konfigurasi Anda)
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',    # Ganti dengan username MySQL Anda
    'password': 'Raihan@3012',  # Ganti dengan password MySQL Anda
    'database': 'seismic_monitoring',  # Ganti dengan nama database Anda
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}

# Konfigurasi miniSEED
MSEED_DIR = "/home/pi/mseed_files"  # Direktori untuk menyimpan file miniSEED lokal (backup)
STATION_CODE = "STMKG"  # Kode stasiun
NETWORK_CODE = "IA"  # Kode jaringan Indonesia
LOCATION_CODE = ""  # Kode lokasi kosong
CHANNEL_CODE = "SHZ"  # Kode channel (Short period, High gain, Vertical)

class DataLogger:
    """Class untuk mencatat semua data ADC dan menghasilkan miniSEED"""
    def __init__(self):
        self.all_adc_data = []  # Menyimpan semua data ADC
        self.start_time = None
        self.end_time = None
        self.gps_data = None
        
        # Buat direktori miniSEED jika belum ada (untuk backup lokal)
        os.makedirs(MSEED_DIR, exist_ok=True)
        
        # Test koneksi database
        self.test_database_connection()
    
    def test_database_connection(self):
        """Test koneksi ke database"""
        try:
            connection = pymysql.connect(**DB_CONFIG)
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                result = cursor.fetchone()
                print("Database connection successful")
            connection.close()
        except Exception as e:
            print(f"Error connecting to database: {e}")
            print("Please check your database configuration and ensure MySQL is running")
    
    def start_session(self, gps_data=None):
        """Mulai sesi perekaman baru"""
        self.start_time = datetime.now(timezone.utc)
        self.gps_data = gps_data
        self.all_adc_data.clear()
        print(f"Started new recording session at: {self.start_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    
    def add_data(self, adc_value, timestamp):
        """Tambahkan data ADC ke logger"""
        self.all_adc_data.append({
            'value': adc_value,
            'timestamp': timestamp
        })
    
    def generate_mseed_file(self):
        """Generate file miniSEED dari data yang telah dikumpulkan"""
        if not self.all_adc_data or not self.start_time:
            print("No data to generate miniSEED file")
            return None, None
        
        try:
            self.end_time = datetime.now(timezone.utc)
            
            # Konversi data ke numpy array
            adc_values = np.array([data['value'] for data in self.all_adc_data], dtype=np.float64)
            
            # Buat Stats object untuk miniSEED
            stats = Stats()
            stats.network = NETWORK_CODE
            stats.station = STATION_CODE
            stats.location = LOCATION_CODE
            stats.channel = CHANNEL_CODE
            stats.starttime = UTCDateTime(self.start_time)
            stats.sampling_rate = 50.0  # 50 SPS
            stats.npts = len(adc_values)
            
            # Tambahkan informasi GPS jika ada
            if self.gps_data:
                stats.coordinates = {
                    'latitude': self.gps_data['latitude'],
                    'longitude': self.gps_data['longitude']
                }
            
            # Buat Trace dan Stream
            trace = Trace(data=adc_values, header=stats)
            stream = Stream([trace])
            
            # Format nama file sesuai dengan format yang diminta
            # IA.STMKG.SHZ_{start-time}-{endtime}
            start_str = self.start_time.strftime("%Y%m%dT%H%M%S")
            end_str = self.end_time.strftime("%Y%m%dT%H%M%S")
            filename = f"{NETWORK_CODE}.{STATION_CODE}.{CHANNEL_CODE}_{start_str}-{end_str}.mseed"
            
            # Simpan file lokal sebagai backup
            local_filepath = os.path.join(MSEED_DIR, filename)
            stream.write(local_filepath, format='MSEED')
            
            # Buat binary data untuk database
            mseed_buffer = io.BytesIO()
            stream.write(mseed_buffer, format='MSEED')
            mseed_binary = mseed_buffer.getvalue()
            mseed_buffer.close()
            
            print(f"miniSEED file created: {filename}")
            print(f"Duration: {len(adc_values) / 50.0:.2f} seconds")
            print(f"Total samples: {len(adc_values)}")
            print(f"Local backup saved: {local_filepath}")
            
            return filename, mseed_binary
            
        except Exception as e:
            print(f"Error generating miniSEED file: {e}")
            return None, None
    
    def save_to_database(self, filename, mseed_binary):
        """Simpan file miniSEED ke database MySQL sebagai LONGBLOB"""
        if not filename or not mseed_binary or not self.start_time or not self.end_time:
            print("No data to save to database")
            return False
        
        try:
            connection = pymysql.connect(**DB_CONFIG)
            with connection.cursor() as cursor:
                # Query untuk insert data
                insert_query = """
                    INSERT INTO mseed_files (filename, start_time, end_time, content)
                    VALUES (%s, %s, %s, %s)
                """
                
                # Data untuk insert
                data = (
                    filename,
                    self.start_time,
                    self.end_time,
                    mseed_binary
                )
                
                # Execute query
                cursor.execute(insert_query, data)
                connection.commit()
                
                print(f"miniSEED file saved to database: {filename}")
                print(f"Start time: {self.start_time}")
                print(f"End time: {self.end_time}")
                print(f"File size: {len(mseed_binary)} bytes")
                
                return True
                
        except Exception as e:
            print(f"Error saving to database: {e}")
            return False
        finally:
            if 'connection' in locals():
                connection.close()
    
    def finish_session(self):
        """Selesaikan sesi dan generate miniSEED + simpan ke database"""
        print("\n=== Finishing recording session ===")
        
        if not self.all_adc_data:
            print("No data recorded in this session")
            return
        
        # Generate miniSEED file
        filename, mseed_binary = self.generate_mseed_file()
        
        if filename and mseed_binary:
            # Simpan ke database
            success = self.save_to_database(filename, mseed_binary)
            
            if success:
                print("=== Session completed successfully ===")
            else:
                print("=== Session completed but database save failed ===")
        else:
            print("=== Session completed but miniSEED generation failed ===")

class GeophonesensorADC:
    def __init__(self, data_logger):
        self.ads = ADS1256(waveshare_config)
        self.ads.drate = DRATE_50
        self.ads.pga_gain = 1
        self.ads.mux = POS_AIN0 | NEG_AIN1
        self.ads.sync()
        
        self.adc_buffer = []  # Buffer untuk MQTT
        self.buffer_size = 50
        self.sample_rate = 50  # SPS target
        self.data_logger = data_logger
    
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
        """Collect data, kirim ke MQTT, dan simpan ke logger"""
        sample_start_time = time.time()
        current_time = datetime.now(timezone.utc)
        
        # Baca data ADC
        adc_data = self.read_sensor()
        if adc_data is not None:
            # Simpan ke data logger (untuk miniSEED)
            self.data_logger.add_data(adc_data['raw_value'], current_time)
            
            # Simpan ke buffer MQTT
            sample_data = {
                'timestamp': current_time.isoformat(),
                'raw_value': adc_data['raw_value'],
            }
            
            self.adc_buffer.append(sample_data)
            
            # Jika buffer sudah penuh, kirim ke MQTT
            if len(self.adc_buffer) >= self.buffer_size:
                payload = {
                    "adc_counts": [sample['raw_value'] for sample in self.adc_buffer],
                    "reading_times": [sample['timestamp'] for sample in self.adc_buffer],
                }
                
                # Kirim data ke MQTT
                if mqtt_client:
                    try:
                        json_payload = json.dumps(payload)
                        mqtt_client.publish(MQTT_TOPIC_GEOPHONE, json_payload)
                        print(f"Geophone: Sent {len(self.adc_buffer)} samples | Total logged: {len(self.data_logger.all_adc_data)}")
                    except Exception as e:
                        print(f"Error publishing geophone data: {e}")
                
                # Kosongkan buffer MQTT
                self.adc_buffer.clear()
        
        # Timing control
        elapsed = time.time() - sample_start_time
        sleep_time = max(0, (1.0/self.sample_rate) - elapsed)
        
        if sleep_time > 0:
            time.sleep(sleep_time)
        else:
            print(f"WARNING: Geophone sampling taking too long! ({elapsed:.4f}s > {1.0/self.sample_rate:.4f}s)")
    
    def cleanup(self):
        """Cleanup ADC"""
        self.ads.stop()

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
        max_attempts = 30
        
        while (time.time() - start_time) < 30 and attempts < max_attempts:
            try:
                gps_data = self.gps_serial.readline().decode('ascii', errors='ignore')
                attempts += 1
                
                if gps_data.startswith('$GNGGA') or gps_data.startswith('$GPGGA'):
                    try:
                        msg = pynmea2.parse(gps_data)
                        if msg.latitude and msg.longitude:
                            gps_info = {
                                "latitude": msg.latitude,
                                "longitude": msg.longitude,
                                "reading_times": datetime.now(timezone.utc).isoformat()
                            }
                            
                            print(f"GPS: Lat={gps_info['latitude']}, Lon={gps_info['longitude']} at {gps_info['reading_times']}")
                            return gps_info
                            
                    except pynmea2.ParseError as e:
                        print(f"GPS parse error: {e}")
                        
            except Exception as e:
                print(f"Error reading GPS: {e}")
                self.initialize()
            
            time.sleep(0.1)
        
        print("Failed to get GPS data after 30 seconds")
        return None
    
    def close(self):
        """Tutup koneksi GPS"""
        if self.gps_serial:
            self.gps_serial.close()
            print("GPS connection closed")

def setup_mqtt():
    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            print("Connected to MQTT broker")
        else:
            print(f"Failed to connect to MQTT broker with error code: {rc}")
    
    def on_disconnect(client, userdata, rc):
        print(f"Disconnected from MQTT broker with error code: {rc}")
    
    client = mqtt.Client(client_id=MQTT_CLIENT_ID)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    
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
        print(f"Error setting up TLS: {e}")
        return None
    
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start()
        time.sleep(2)
        return client
    except Exception as e:
        print(f"Error connecting to MQTT broker: {e}")
        return None

# Global variables untuk cleanup
data_logger = None
geophone = None
gps = None
mqtt_client = None

def cleanup_and_exit(signum=None, frame=None):
    """Function untuk cleanup saat program dihentikan"""
    global data_logger, geophone, gps, mqtt_client
    
    print("\n=== Program dihentikan, melakukan cleanup ===")
    
    # Finish session dan generate miniSEED
    if data_logger:
        data_logger.finish_session()
    
    # Cleanup hardware
    if geophone:
        geophone.cleanup()
    
    if gps:
        gps.close()
        
    if mqtt_client:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
    
    print("Cleanup selesai. Program berakhir.")
    sys.exit(0)

def main():
    global data_logger, geophone, gps, mqtt_client
    
    # Setup signal handlers untuk cleanup
    signal.signal(signal.SIGINT, cleanup_and_exit)
    signal.signal(signal.SIGTERM, cleanup_and_exit)
    atexit.register(cleanup_and_exit)
    
    # Inisialisasi MQTT
    mqtt_client = setup_mqtt()
    
    if not mqtt_client:
        print("Failed to initialize MQTT client. Exiting...")
        return
    
    try:
        # Inisialisasi Data Logger
        data_logger = DataLogger()
        
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
        time.sleep(2)
        
        # Mulai sesi perekaman
        data_logger.start_session(gps_data)
        
        # === Mulai pembacaan geophone ===
        print("=== Starting geophone data collection ===")
        geophone = GeophonesensorADC(data_logger)
        
        samples_collected = 0
        start_time = time.time()
        
        print("Press Ctrl+C to stop the program and generate miniSEED file...")
        
        # Loop utama
        while True:
            geophone.collect_and_send_data(mqtt_client)
            samples_collected += 1
            
            # Print statistik setiap 250 samples (5 detik pada 50 SPS)
            if samples_collected % 250 == 0:
                elapsed_time = time.time() - start_time
                actual_rate = samples_collected / elapsed_time if elapsed_time > 0 else 0
                logged_samples = len(data_logger.all_adc_data)
                duration_minutes = elapsed_time / 60
                print(f"Stats: {samples_collected} samples | Rate: {actual_rate:.2f} SPS | Logged: {logged_samples} | Duration: {duration_minutes:.1f} min")
        
    except KeyboardInterrupt:
        print("\nProgram dihentikan oleh pengguna")
        cleanup_and_exit()
    
    except Exception as e:
        print(f"Error in main: {e}")
        cleanup_and_exit()

if __name__ == "__main__":
    main()