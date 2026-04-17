#!/usr/bin/python
# -*- coding:utf-8 -*-

import time
from datetime import datetime
#multithreading
import threading
import queue
#gps
import serial
import pynmea2
#geophone
import ADS1256
import RPi.GPIO as GPIO

#Konfigurasi GPS
GPS_SERIAL_PORT = '/dev/serial0'
GPS_BAUD_RATE = 9600

#Shared queue untuk data GPS
gps_queue = queue.Queue()

#Variabel untuk menyimpan data GPS terakhir yang valid
last_valid_gps_data = None

#Fungsi read GPS data
def read_gps_data():
    try:
        gps_serial = serial.Serial(GPS_SERIAL_PORT, GPS_BAUD_RATE, timeout=1)
        print("GPS thread started.")
        while True:
            gps_data = gps_serial.readline().decode('ascii', errors='ignore')
            if gps_data.startswith('$GNGGA') or gps_data.startswith('$GPGGA'):
                try:
                    msg = pynmea2.parse(gps_data)
                    #Simpan data GPS ke queue
                    gps_queue.put((msg.latitude, msg.longitude, datetime.now().isoformat()))
                except pynmea2.ParseError as e:
                    print(f"GPS Parse error: {e}")
            time.sleep(1) #Update GPS data setiap 1 detik
    except Exception as e:
        print(f"GPS thread error: {e}")
    finally:
        if 'gps_serial' in locals():
            gps_serial.close()
            print("GPS serial connection closed.")
                    

# Inisialisasi ADS1256
ADC = ADS1256.ADS1256()
if ADC.ADS1256_init() == -1:
    print("ADS1256 initialization failed. Exiting...")
    exit()
        
#Kalibrasi ADC
ADC.ADS1256_WriteCmd(ADS1256.CMD['CMD_SELFCAL'])  # Jalankan self-calibration
time.sleep(0.1)  # Beri waktu untuk kalibrasi (100 ms)

#Atur SPS dan Gain
sps = ADS1256.ADS1256_DRATE_E['ADS1256_5SPS']  
gain = ADS1256.ADS1256_GAIN_E['ADS1256_GAIN_1'] 
ADC.ADS1256_ConfigADC(gain, sps)  # Konfigurasi ADC dengan SPS dan Gain yang dipilih

# Set mode differential input
ADC.ADS1256_SetMode(1)  # Mode 1 untuk differential input

#Mulai thread GPS
gps_thread = threading.Thread(target=read_gps_data, daemon=True)
gps_thread.start()

# Loop untuk membaca data dari geophone
try:
    print("Mulai menampilkan data geophone dan GPS...")
    while True:
        ADC.ADS1256_WaitDRDY() # Tunggu sampai data siap
        timestamp = datetime.now().isoformat() # Timestamp dalam format ISO 8601
        # Baca data dari channel differential 0 (AIN0 - AIN1)
        geophone_value = ADC.ADS1256_GetChannalValue(0)  # Channel 0 untuk differential AIN0-AIN1
        # Konversi nilai ADC ke voltase (asumsi VREF = 5V)
        voltage = geophone_value * 5.0 / 0x7FFFFF  # 0x7FFFFF adalah nilai maksimum untuk ADC 24-bit
        
        #Ambil data GPS terbaru dari queue (jika ada)
        while not gps_queue.empty():
            last_valid_gps_data = gps_queue.get()
            
        #Penggunaan last data GPS
        if last_valid_gps_data:
            latitude, longitude, gps_timestamp = last_valid_gps_data
        else:
            latitude, longitude, gps_timestamp = None, None, None
        
        #Tampilkan data geophone dan GPS
        print(f"Timestamp: {timestamp}, ADC Counts: {voltage}, Latitude: {latitude}, Longitude: {longitude}")

except KeyboardInterrupt:
    # Handle interrupt (Ctrl+C)
    print("\nProgram dihentikan oleh pengguna.")

except Exception as e:
    # Handle error lainnya
    print(f"Terjadi error: {e}")

finally:
    # Bersihkan GPIO dan tutup program
    GPIO.cleanup()
    print("Program selesai.")

