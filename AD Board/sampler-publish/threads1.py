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
        # Menggunakan deque untuk operasi thread-safe dengan maxlen
        self.sample_buffer = deque(maxlen=10000)  # Buffer besar untuk menghindari data loss
        self.buffer_lock = threading.Lock()
        
        # Konfigurasi untuk publish rate control
        self.TARGET_SPS = 50
        self.SAMPLES_PER_PUBLISH = 50  # Publish 50 sampel setiap 1 detik
        self.PUBLISH_INTERVAL = 1.0    # 1 detik
        
        # Statistik untuk monitoring
        self.sampling_stats = {
            'total_samples': 0,
            'start_time': None,
            'last_sample_time': None,
            'actual_sampling_rate': 0
        }
        
        self.publish_stats = {
            'total_published': 0,
            'publish_count': 0,
            'start_time': None,
            'last_publish_time': None
        }
    
    def sampling_thread(self):
        """
        Thread khusus untuk sampling - mengambil data secepat mungkin
        Tidak peduli dengan timing, fokus pada akuisisi data
        """
        print("Starting sampling thread...")
        self.sampling_stats['start_time'] = time.time()
        
        try:
            while self.running:
                # Ambil data ADC tanpa delay artifisial
                try:
                    adc_value = self.adc.ADS1256_GetChannalValue(0)
                    current_time = time.time()
                    
                    # Buat data point dengan timestamp
                    data_point = {
                        'adc_value': adc_value,
                        'timestamp': current_time,
                        'sample_number': self.sampling_stats['total_samples']
                    }
                    
                    # Masukkan ke buffer (thread-safe)
                    with self.buffer_lock:
                        self.sample_buffer.append(data_point)
                    
                    # Update statistik
                    self.sampling_stats['total_samples'] += 1
                    self.sampling_stats['last_sample_time'] = current_time
                    
                    # Hitung actual sampling rate setiap 1000 sampel
                    if self.sampling_stats['total_samples'] % 1000 == 0:
                        elapsed = current_time - self.sampling_stats['start_time']
                        self.sampling_stats['actual_sampling_rate'] = self.sampling_stats['total_samples'] / elapsed
                        print(f"Sampling: {self.sampling_stats['total_samples']} samples, "
                              f"Rate: {self.sampling_stats['actual_sampling_rate']:.2f} SPS, "
                              f"Buffer size: {len(self.sample_buffer)}")
                    
                    # Minimal delay untuk mencegah 100% CPU usage
                    # Nilai ini bisa disesuaikan, atau dihilangkan jika perlu
                    time.sleep(0.001)  # 1ms - opsional
                    
                except Exception as e:
                    print(f"Error in sampling: {e}")
                    time.sleep(0.01)  # Delay lebih lama jika error
                    
        except Exception as e:
            print(f"Fatal error in sampling thread: {e}")
        finally:
            print("Sampling thread stopped")
    
    def publish_thread(self):
        """
        Thread khusus untuk publish - mengirim data dengan rate yang terkontrol
        Mengambil data dari buffer dan mengirim tepat 50 sampel setiap 1 detik
        """
        print("Starting publish thread...")
        self.publish_stats['start_time'] = time.time()
        
        try:
            while self.running:
                publish_start_time = time.time()
                
                # Ambil data dari buffer
                samples_to_send = []
                with self.buffer_lock:
                    # Ambil maksimal SAMPLES_PER_PUBLISH data dari buffer
                    for _ in range(min(self.SAMPLES_PER_PUBLISH, len(self.sample_buffer))):
                        if self.sample_buffer:
                            samples_to_send.append(self.sample_buffer.popleft())
                
                # Jika ada data untuk dikirim
                if samples_to_send:
                    # Siapkan payload
                    adc_counts = [sample['adc_value'] for sample in samples_to_send]
                    first_timestamp = datetime.fromtimestamp(
                        samples_to_send[0]['timestamp'], tz=timezone.utc
                    ).isoformat()
                    
                    # Metadata untuk rekonstruksi timing
                    actual_timestamps = [sample['timestamp'] for sample in samples_to_send]
                    sample_numbers = [sample['sample_number'] for sample in samples_to_send]
                    
                    # Hitung statistik interval untuk monitoring
                    if len(actual_timestamps) > 1:
                        intervals = []
                        for i in range(1, len(actual_timestamps)):
                            interval = actual_timestamps[i] - actual_timestamps[i-1]
                            intervals.append(interval * 1000)  # Convert to ms
                        
                        avg_interval = statistics.mean(intervals)
                        std_interval = statistics.stdev(intervals) if len(intervals) > 1 else 0
                    else:
                        avg_interval = 0
                        std_interval = 0
                    
                    payload = {
                        "adc_counts": adc_counts,
                        "reading_times": first_timestamp,
                        "sample_count": len(adc_counts),
                        "target_sps": self.TARGET_SPS,
                        "actual_avg_interval_ms": avg_interval,
                        "interval_std_ms": std_interval,
                        "sample_numbers": sample_numbers,
                        "publish_sequence": self.publish_stats['publish_count'],
                        "buffer_size_at_publish": len(self.sample_buffer)
                    }
                    
                    # Kirim via MQTT
                    if self.mqtt_client:
                        try:
                            json_payload = json.dumps(payload)
                            result = self.mqtt_client.publish(MQTT_TOPIC_GEOPHONE, json_payload)
                            
                            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                                # Update statistik publish
                                self.publish_stats['total_published'] += len(adc_counts)
                                self.publish_stats['publish_count'] += 1
                                self.publish_stats['last_publish_time'] = time.time()
                                
                                print(f"Published {len(adc_counts)} samples, "
                                      f"Avg interval: {avg_interval:.2f}±{std_interval:.2f}ms, "
                                      f"Buffer: {len(self.sample_buffer)}, "
                                      f"Sequence: {self.publish_stats['publish_count']}")
                                      
                            else:
                                print(f"MQTT publish failed: {result.rc}")
                                
                        except Exception as e:
                            print(f"Error publishing data: {e}")
                else:
                    print("No samples available in buffer")
                
                # Tunggu sampai tepat 1 detik dari awal publish cycle
                elapsed_time = time.time() - publish_start_time
                sleep_time = max(0, self.PUBLISH_INTERVAL - elapsed_time)
                
                if sleep_time > 0:
                    time.sleep(sleep_time)
                else:
                    print(f"WARNING: Publish cycle took too long ({elapsed_time:.3f}s > {self.PUBLISH_INTERVAL}s)")
                    
        except Exception as e:
            print(f"Fatal error in publish thread: {e}")
        finally:
            print("Publish thread stopped")
    
    def monitoring_thread(self):
        """
        Thread untuk monitoring dan logging statistik
        """
        print("Starting monitoring thread...")
        
        try:
            while self.running:
                time.sleep(10)  # Report setiap 10 detik
                
                current_time = time.time()
                
                # Statistik sampling
                if self.sampling_stats['start_time']:
                    sampling_elapsed = current_time - self.sampling_stats['start_time']
                    sampling_rate = self.sampling_stats['total_samples'] / sampling_elapsed if sampling_elapsed > 0 else 0
                else:
                    sampling_rate = 0
                
                # Statistik publish
                if self.publish_stats['start_time']:
                    publish_elapsed = current_time - self.publish_stats['start_time']
                    publish_rate = self.publish_stats['total_published'] / publish_elapsed if publish_elapsed > 0 else 0
                    effective_sps = self.publish_stats['total_published'] / publish_elapsed if publish_elapsed > 0 else 0
                else:
                    publish_rate = 0
                    effective_sps = 0
                
                print(f"=== MONITORING REPORT ===")
                print(f"Sampling Rate: {sampling_rate:.2f} SPS (actual hardware)")
                print(f"Effective SPS: {effective_sps:.2f} SPS (published data)")
                print(f"Buffer Size: {len(self.sample_buffer)}")
                print(f"Total Sampled: {self.sampling_stats['total_samples']}")
                print(f"Total Published: {self.publish_stats['total_published']}")
                print(f"Publish Cycles: {self.publish_stats['publish_count']}")
                
                # Warning jika buffer terlalu penuh atau kosong
                buffer_size = len(self.sample_buffer)
                if buffer_size > 8000:  # 80% dari maxlen
                    print(f"WARNING: Buffer getting full ({buffer_size}/10000)")
                elif buffer_size < 100:
                    print(f"WARNING: Buffer getting low ({buffer_size}/10000)")
                
                print("========================")
                
        except Exception as e:
            print(f"Error in monitoring thread: {e}")
        finally:
            print("Monitoring thread stopped")
    
    def run(self):
        """
        Jalankan semua thread
        """
        self.running = True
        
        # Buat dan start thread
        sampling_thread = threading.Thread(target=self.sampling_thread, name="SamplingThread")
        publish_thread = threading.Thread(target=self.publish_thread, name="PublishThread")
        monitoring_thread = threading.Thread(target=self.monitoring_thread, name="MonitoringThread")
        
        # Set daemon agar thread otomatis stop ketika main program berhenti
        sampling_thread.daemon = True
        publish_thread.daemon = True
        monitoring_thread.daemon = True
        
        # Start semua thread
        sampling_thread.start()
        publish_thread.start()
        monitoring_thread.start()
        
        try:
            # Wait untuk semua thread
            sampling_thread.join()
            publish_thread.join()
            monitoring_thread.join()
        except Exception as e:
            print(f"Error waiting for threads: {e}")
        finally:
            GPIO.cleanup()
            print("All geophone threads stopped")
    
    def stop(self):
        """
        Stop semua operasi
        """
        print("Stopping geophone sensor...")
        self.running = False
        
        # Print final statistics
        if self.sampling_stats['start_time']:
            total_time = time.time() - self.sampling_stats['start_time']
            final_sampling_rate = self.sampling_stats['total_samples'] / total_time
            final_publish_rate = self.publish_stats['total_published'] / total_time
            
            print(f"=== FINAL STATISTICS ===")
            print(f"Total Runtime: {total_time:.2f} seconds")
            print(f"Total Samples: {self.sampling_stats['total_samples']}")
            print(f"Total Published: {self.publish_stats['total_published']}")
            print(f"Average Sampling Rate: {final_sampling_rate:.2f} SPS")
            print(f"Average Publish Rate: {final_publish_rate:.2f} SPS")
            print(f"Efficiency: {(self.publish_stats['total_published']/self.sampling_stats['total_samples']*100):.1f}%")
            print("========================")

# GPS Sensor dengan struktur yang sama
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
    
    def initialize(self):
        try:
            self.gps_serial = serial.Serial(self.port, self.baud_rate, timeout=1)
            return True
        except Exception as e:
            print(f"Error initializing GPS: {e}")
            return False
    
    def gps_sampling_thread(self):
        """
        Thread untuk sampling GPS data
        """
        print("Starting GPS sampling thread...")
        
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
                                    "timestamp": time.time(),
                                    "raw_data": gps_data.strip()
                                }
                                
                                with self.buffer_lock:
                                    self.gps_buffer.append(data_point)
                                    
                        except pynmea2.ParseError as e:
                            print(f"GPS parse error: {e}")
                            
                except Exception as e:
                    print(f"Error reading GPS: {e}")
                    self.initialize()
                    
                time.sleep(1)  # GPS sampling setiap detik
                
        except Exception as e:
            print(f"Error in GPS sampling thread: {e}")
        finally:
            if self.gps_serial:
                self.gps_serial.close()
            print("GPS sampling thread stopped")
    
    def gps_publish_thread(self):
        """
        Thread untuk publish GPS data setiap 5 menit
        """
        print("Starting GPS publish thread...")
        
        try:
            while self.running:
                publish_start_time = time.time()
                
                # Ambil data terbaru dari buffer
                latest_data = None
                with self.buffer_lock:
                    if self.gps_buffer:
                        latest_data = self.gps_buffer[-1]  # Ambil data terbaru
                
                if latest_data and self.mqtt_client:
                    # Siapkan payload
                    payload = {
                        "latitude": latest_data["latitude"],
                        "longitude": latest_data["longitude"],
                        "reading_times": datetime.fromtimestamp(
                            latest_data["timestamp"], tz=timezone.utc
                        ).isoformat(),
                        "buffer_size": len(self.gps_buffer)
                    }
                    
                    try:
                        json_payload = json.dumps(payload)
                        result = self.mqtt_client.publish(MQTT_TOPIC_GPS, json_payload)
                        
                        if result.rc == mqtt.MQTT_ERR_SUCCESS:
                            print(f"GPS Published: Lat={latest_data['latitude']:.6f}, "
                                  f"Lon={latest_data['longitude']:.6f}")
                        else:
                            print(f"GPS MQTT publish failed: {result.rc}")
                            
                    except Exception as e:
                        print(f"Error publishing GPS data: {e}")
                        
                else:
                    print("No GPS data available for publish")
                
                # Tunggu interval berikutnya
                elapsed_time = time.time() - publish_start_time
                sleep_time = max(0, self.GPS_PUBLISH_INTERVAL - elapsed_time)
                
                # Sleep dengan kemampuan early exit
                for _ in range(int(sleep_time)):
                    if not self.running:
                        break
                    time.sleep(1)
                    
        except Exception as e:
            print(f"Error in GPS publish thread: {e}")
        finally:
            print("GPS publish thread stopped")
    
    def run(self):
        self.running = True
        
        # Start threads
        sampling_thread = threading.Thread(target=self.gps_sampling_thread, name="GPSSamplingThread")
        publish_thread = threading.Thread(target=self.gps_publish_thread, name="GPSPublishThread")
        
        sampling_thread.daemon = True
        publish_thread.daemon = True
        
        sampling_thread.start()
        publish_thread.start()
        
        try:
            sampling_thread.join()
            publish_thread.join()
        except Exception as e:
            print(f"Error in GPS threads: {e}")
        finally:
            print("GPS threads stopped")
    
    def stop(self):
        self.running = False

# Fungsi setup MQTT (sama seperti sebelumnya)
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

# Fungsi utama
def main():
    mqtt_client = setup_mqtt()
    
    if not mqtt_client:
        print("Failed to initialize MQTT client. Exiting...")
        return
    
    try:
        geophone = GeophonesensorADC(mqtt_client=mqtt_client)
        gps = GPSSensor(mqtt_client=mqtt_client)
        
        geophone_thread = threading.Thread(target=geophone.run)
        gps_thread = threading.Thread(target=gps.run)
        
        print("Starting sensor threads...")
        geophone_thread.start()
        gps_thread.start()
        
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nProgram dihentikan oleh pengguna")
        
        print("Stopping sensor threads...")
        geophone.stop()
        gps.stop()
        
        geophone_thread.join()
        gps_thread.join()
        
        if mqtt_client:
            mqtt_client.loop_stop()
            mqtt_client.disconnect()
        
    except Exception as e:
        print(f"Error in main: {e}")
    
    finally:
        print("Program selesai.")

if __name__ == "__main__":
    main()