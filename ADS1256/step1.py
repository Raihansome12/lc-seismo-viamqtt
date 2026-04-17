#!/usr/bin/python
# -*- coding:utf-8 -*-

import time
import ADS1256
import RPi.GPIO as GPIO

try:
    # Inisialisasi ADS1256
    ADC = ADS1256.ADS1256()
    if ADC.ADS1256_init() == -1:
        print("ADS1256 initialization failed. Exiting...")
        exit()

    # Atur SPS dan Gain
    sps = ADS1256.ADS1256_DRATE_E['ADS1256_50SPS']  # 1000 SPS
    gain = ADS1256.ADS1256_GAIN_E['ADS1256_GAIN_4']   # Gain 4
    ADC.ADS1256_ConfigADC(gain, sps)  # Konfigurasi ADC dengan SPS dan Gain yang dipilih

    # Set mode differential input
    ADC.ADS1256_SetMode(1)  # Mode 1 untuk differential input

    # Loop untuk membaca data dari geophone
    while True:
        # Baca data dari channel differential 0 (AIN0 - AIN1)
        geophone_value = ADC.ADS1256_GetChannalValue(0)  # Channel 0 untuk differential AIN0-AIN1

        # Konversi nilai ADC ke voltase (asumsi VREF = 5V)
        voltage = geophone_value * 5.0 / 0x7FFFFF  # 0x7FFFFF adalah nilai maksimum untuk ADC 24-bit

        # Tampilkan hasil pembacaan
        print(f"Geophone Value (AIN0-AIN1): {geophone_value}")
        print(f"Voltage: {voltage:.6f} V")
        print("\33[2A")  # Pindah kursor ke atas untuk overwrite output sebelumnya

        # Jeda sebentar sebelum membaca lagi
        time.sleep(0.1)

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