import time
import threading
import queue
import json
import ADS1256
import RPi.GPIO as GPIO
import serial
import pynmea2
from datetime import datetime

# Konfigurasi untuk geophone (ADC)
class GeophonesensorADC:
    def __init__(self):
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
        self.data_queue = queue.Queue()
    
    def read_sensor(self):
        try:
            adc_value = self.adc.ADS1256_GetChannalValue(0)
            voltage = adc_value * 5.0 / 0x7fffff
            timestamp = datetime.now().isoformat()
            return {
                "timestamp": timestamp,
                "voltage": voltage,
                "raw_value": adc_value
            }
        except Exception as e:
            print(f"Error reading geophone: {e}")
            return None
    
    def run(self):
        self.running = True
        try:
            while self.running:
                data = self.read_sensor()
                if data:
                    self.data_queue.put(data)
                    # Kita bisa mengirimkan data ke MQTT di sini
                    # Untuk sementara hanya log
                    print(f"Geophone: {data['voltage']:.6f}V at {data['timestamp']}")
                
                # Untuk menjaga SPS 50, kita perlu waktu tidur yang tepat
                # 1/50 = 0.02 detik per sampel
                time.sleep(0.02)
        except Exception as e:
            print(f"Error in geophone thread: {e}")
        finally:
            GPIO.cleanup()
            print("Geophone thread stopped")
    
    def stop(self):
        self.running = False


# Konfigurasi untuk GPS
class GPSSensor:
    def __init__(self, port='/dev/serial0', baud_rate=9600):
        self.port = port
        self.baud_rate = baud_rate
        self.gps_serial = None
        self.running = False
        self.data_queue = queue.Queue()
    
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
                        return {
                            "timestamp": datetime.now().isoformat(),
                            "latitude": msg.latitude,
                            "longitude": msg.longitude,
                            "altitude": msg.altitude,
                            "satellites": msg.num_sats,
                            "fix_quality": msg.gps_qual
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
                    self.data_queue.put(data)
                    # Kita bisa mengirimkan data ke MQTT di sini
                    # Untuk sementara hanya log
                    print(f"GPS: Lat={data['latitude']}, Lon={data['longitude']} at {data['timestamp']}")
                
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


# Fungsi utama
def main():
    # Inisialisasi sensor
    try:
        geophone = GeophonesensorADC()
        gps = GPSSensor()
        
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
        
    except Exception as e:
        print(f"Error in main: {e}")
    
    finally:
        print("Program selesai.")


if __name__ == "__main__":
    main()