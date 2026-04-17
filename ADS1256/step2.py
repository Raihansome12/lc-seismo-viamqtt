#!/usr/bin/python
# -*- coding:utf-8 -*-

import time
import csv
import ADS1256
import RPi.GPIO as GPIO

# Inisialisasi ADS1256
ADC = ADS1256.ADS1256()
if ADC.ADS1256_init() == -1:
    print("ADS1256 initialization failed. Exiting...")
    exit()

# Konfigurasi SPS dan Gain
sps = ADS1256.ADS1256_DRATE_E['ADS1256_50SPS']  # Set SPS ke 50
gain = ADS1256.ADS1256_GAIN_E['ADS1256_GAIN_4']  # Gain 4 (sesuaikan dengan kebutuhan)
ADC.ADS1256_ConfigADC(gain, sps)  # Konfigurasi ADC dengan SPS dan Gain yang dipilih

# Set mode differential input
ADC.ADS1256_SetMode(1)  # Mode 1 untuk differential input

# Buffer untuk menyimpan data sementara
buffer = []
buffer_size = 100  # Tulis data ke file setiap 100 sampel

# Buka file CSV untuk menyimpan data
with open('geophone_data.csv', mode='w', newline='') as file:
    writer = csv.writer(file)
    writer.writerow(["Timestamp", "ADC Counts"])  # Header file CSV

    try:
        print("Mulai perekaman data geophone...")
        while True:
            ADC.ADS1256_WaitDRDY()  # Tunggu sampai data siap
            timestamp = time.time()  # Catat waktu saat ini
            geophone_value = ADC.ADS1256_GetChannalValue(0)  # Baca data dari channel 0 (AIN0-AIN1)
            buffer.append((timestamp, geophone_value))  # Simpan data ke buffer

            # Jika buffer penuh, tulis data ke file
            if len(buffer) >= buffer_size:
                writer.writerows(buffer)  # Tulis buffer ke file
                buffer = []  # Reset buffer
                print(f"Data ditulis ke file. Jumlah sampel: {buffer_size}")

    except KeyboardInterrupt:
        # Jika program dihentikan oleh pengguna (Ctrl+C), tulis sisa data di buffer
        if buffer:
            writer.writerows(buffer)
            print(f"Data terakhir ditulis ke file. Jumlah sampel: {len(buffer)}")
        print("Perekaman dihentikan oleh pengguna.")

    except Exception as e:
        # Handle error lainnya
        print(f"Terjadi error: {e}")

    finally:
        # Bersihkan GPIO dan tutup program
        GPIO.cleanup()
        print("Program selesai.")