#!/usr/bin/python
# -*- coding:utf-8 -*-

import time
import ADS1256
import RPi.GPIO as GPIO
import statistics
import os
import numpy as np
from datetime import datetime

def clear_screen():
    """Membersihkan layar terminal"""
    os.system('clear' if os.name == 'posix' else 'cls')

def read_differential_channel(adc, channel, num_readings=5, delay=0.2):
    """
    Membaca nilai dari channel differential sebanyak num_readings kali
    
    Args:
        adc: Objek ADS1256
        channel: Channel differential yang akan dibaca (0-3)
        num_readings: Jumlah pembacaan yang akan dilakukan
        delay: Jeda antar pembacaan dalam detik
        
    Returns:
        List nilai pembacaan, nilai rata-rata, dan standar deviasi
    """
    readings = []
    voltages = []
    
    print(f"Melakukan {num_readings} kali pembacaan pada channel differential {channel}...")
    
    for i in range(num_readings):
        # Baca nilai ADC dari channel differential
        value = adc.ADS1256_GetChannalValue(channel)
        
        # Konversi nilai ADC ke voltase (asumsi VREF = 5V)
        voltage = value * 5.0 / 0x7FFFFF  # 0x7FFFFF adalah nilai maksimum untuk ADC 24-bit
        
        readings.append(value)
        voltages.append(voltage)
        
        print(f"Pembacaan {i+1}: Nilai ADC = {value}, Tegangan = {voltage:.6f} V")
        time.sleep(delay)
    
    # Hitung rata-rata dan standar deviasi
    avg_reading = statistics.mean(readings)
    avg_voltage = statistics.mean(voltages)
    
    try:
        std_dev_reading = statistics.stdev(readings)
        std_dev_voltage = statistics.stdev(voltages)
    except statistics.StatisticsError:
        # Jika hanya ada satu nilai, stdev akan error
        std_dev_reading = 0
        std_dev_voltage = 0
    
    return {
        'readings': readings,
        'voltages': voltages,
        'avg_reading': avg_reading,
        'avg_voltage': avg_voltage,
        'std_dev_reading': std_dev_reading,
        'std_dev_voltage': std_dev_voltage
    }

def test_all_channels(adc, num_readings=5):
    """
    Menguji semua channel differential (0-3)
    
    Args:
        adc: Objek ADS1256
        num_readings: Jumlah pembacaan per channel
    """
    diff_channels = {
        0: "AIN0-AIN1",
        1: "AIN2-AIN3",
        2: "AIN4-AIN5",
        3: "AIN6-AIN7"
    }
    
    results = {}
    
    for channel in range(4):
        clear_screen()
        print(f"\n===== Pengujian Channel Differential {channel} ({diff_channels[channel]}) =====")
        results[channel] = read_differential_channel(adc, channel, num_readings)
    
    # Tampilkan ringkasan hasil
    clear_screen()
    print("\n===== Ringkasan Hasil Pengujian 4 Channel Differential =====")
    for channel in range(4):
        print(f"\nChannel {channel} ({diff_channels[channel]}):")
        print(f"  Rata-rata: {results[channel]['avg_reading']:.2f} (ADC) = {results[channel]['avg_voltage']:.6f} V")
        print(f"  Std Dev: {results[channel]['std_dev_reading']:.2f} (ADC) = {results[channel]['std_dev_voltage']:.6f} V")
        print(f"  Pembacaan: {results[channel]['readings']}")
        print(f"  Tegangan: {[f'{v:.6f}' for v in results[channel]['voltages']]}")
    
    return results

def test_sps_accuracy(adc, sps_code, num_samples=100):
    """
    Menguji keakuratan Sample Per Second (SPS) yang dipilih
    
    Args:
        adc: Objek ADS1256
        sps_code: Kode SPS yang dipilih
        num_samples: Jumlah sampel yang akan diambil
    """
    # Dictionary kode SPS ke nilai SPS yang diharapkan (dalam Hz)
    sps_values = {
        ADS1256.ADS1256_DRATE_E['ADS1256_30000SPS']: 30000,
        ADS1256.ADS1256_DRATE_E['ADS1256_15000SPS']: 15000,
        ADS1256.ADS1256_DRATE_E['ADS1256_7500SPS']: 7500,
        ADS1256.ADS1256_DRATE_E['ADS1256_3750SPS']: 3750,
        ADS1256.ADS1256_DRATE_E['ADS1256_2000SPS']: 2000,
        ADS1256.ADS1256_DRATE_E['ADS1256_1000SPS']: 1000,
        ADS1256.ADS1256_DRATE_E['ADS1256_500SPS']: 500,
        ADS1256.ADS1256_DRATE_E['ADS1256_100SPS']: 100,
        ADS1256.ADS1256_DRATE_E['ADS1256_60SPS']: 60,
        ADS1256.ADS1256_DRATE_E['ADS1256_50SPS']: 50,
        ADS1256.ADS1256_DRATE_E['ADS1256_30SPS']: 30,
        ADS1256.ADS1256_DRATE_E['ADS1256_25SPS']: 25,
        ADS1256.ADS1256_DRATE_E['ADS1256_15SPS']: 15,
        ADS1256.ADS1256_DRATE_E['ADS1256_10SPS']: 10,
        ADS1256.ADS1256_DRATE_E['ADS1256_5SPS']: 5,
        ADS1256.ADS1256_DRATE_E['ADS1256_2d5SPS']: 2.5
    }
    
    # Ambil nilai SPS yang diharapkan
    expected_sps = sps_values.get(sps_code, 50)  # Default ke 50 jika tidak ditemukan
    expected_interval_ms = 1000.0 / expected_sps  # Konversi ke interval dalam ms
    
    print(f"\n===== Uji Kecepatan SPS =====")
    print(f"SPS yang dipilih: {expected_sps} Hz")
    print(f"Interval yang diharapkan: {expected_interval_ms:.3f} ms")
    print(f"Mengambil {num_samples} sampel untuk pengujian...")
    
    # Pilih channel untuk pengujian (gunakan channel 0)
    channel = 0
    
    # Array untuk menyimpan timestamp
    timestamps = []
    values = []
    
    try:
        # Pengambilan sampel pertama
        start_time = time.time()
        first_time = start_time
        
        for i in range(num_samples):
            # Ambil nilai dari ADC
            value = adc.ADS1256_GetChannalValue(channel)
            current_time = time.time()
            
            timestamps.append(current_time)
            values.append(value)
            
            # Print progress setiap 10 sampel
            if (i+1) % 10 == 0:
                print(f"Sampel {i+1}/{num_samples} diambil...")
    
    except KeyboardInterrupt:
        print("\nPengujian SPS dihentikan oleh pengguna.")
    
    # Hitung interval antar sampel
    if len(timestamps) < 2:
        print("Terlalu sedikit sampel untuk analisis.")
        return
    
    # Konversi timestamps ke array numpy
    timestamps = np.array(timestamps)
    
    # Hitung perbedaan waktu antar sampel (dalam milidetik)
    intervals = np.diff(timestamps) * 1000.0  # konversi ke ms
    
    # Analisis hasil
    avg_interval = np.mean(intervals)
    std_dev = np.std(intervals)
    min_interval = np.min(intervals)
    max_interval = np.max(intervals)
    actual_sps = 1000.0 / avg_interval
    total_time = timestamps[-1] - first_time
    actual_overall_sps = (len(timestamps) - 1) / total_time
    
    # Tampilkan hasil
    print("\n===== Hasil Pengujian SPS =====")
    print(f"Jumlah sampel yang dianalisis: {len(intervals)}")
    print(f"Waktu total pengujian: {total_time:.3f} detik")
    print(f"Interval rata-rata: {avg_interval:.3f} ms (SPS aktual: {actual_sps:.2f} Hz)")
    print(f"SPS keseluruhan: {actual_overall_sps:.2f} Hz")
    print(f"SPS yang diharapkan: {expected_sps} Hz")
    print(f"Deviasi dari yang diharapkan: {(actual_sps - expected_sps) / expected_sps * 100:.2f}%")
    print(f"Standar deviasi interval: {std_dev:.3f} ms")
    print(f"Interval minimum: {min_interval:.3f} ms")
    print(f"Interval maksimum: {max_interval:.3f} ms")
    
    # Simpan data ke file jika diperlukan
    choice = input("\nApakah ingin menyimpan data SPS ke file? (y/n): ")
    if choice.lower() == 'y':
        filename = f"sps_test_{expected_sps}hz_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        with open(filename, 'w') as f:
            f.write("timestamp,interval_ms,adc_value\n")
            f.write(f"{timestamps[0]},0,{values[0]}\n")  # data pertama
            for i in range(1, len(timestamps)):
                interval = (timestamps[i] - timestamps[i-1]) * 1000.0
                f.write(f"{timestamps[i]},{interval:.6f},{values[i]}\n")
        print(f"Data disimpan ke file: {filename}")
    
    return {
        'expected_sps': expected_sps,
        'actual_sps': actual_sps,
        'avg_interval': avg_interval,
        'std_dev': std_dev,
        'min_interval': min_interval,
        'max_interval': max_interval,
        'num_samples': len(intervals),
        'deviation_percent': (actual_sps - expected_sps) / expected_sps * 100
    }

def main():
    try:
        # Inisialisasi ADS1256
        ADC = ADS1256.ADS1256()
        if ADC.ADS1256_init() == -1:
            print("ADS1256 initialization failed. Exiting...")
            exit()
        
        print("ADS1256 diinisialisasi dengan sukses!")
        
        # Pengaturan default
        sps = ADS1256.ADS1256_DRATE_E['ADS1256_50SPS']  # 50 SPS default
        gain = ADS1256.ADS1256_GAIN_E['ADS1256_GAIN_1']  # Gain 1 default
        
        # Menu untuk pengaturan SPS
        print("\n===== Pengaturan Sample Rate (SPS) =====")
        print("1. 30,000 SPS")
        print("2. 15,000 SPS")
        print("3. 7,500 SPS")
        print("4. 3,750 SPS")
        print("5. 2,000 SPS")
        print("6. 1,000 SPS")
        print("7. 500 SPS")
        print("8. 100 SPS")
        print("9. 60 SPS")
        print("10. 50 SPS (default)")
        print("11. 30 SPS")
        print("12. 25 SPS")
        print("13. 15 SPS")
        print("14. 10 SPS")
        print("15. 5 SPS")
        print("16. 2.5 SPS")
        
        choice = input("Pilih sample rate (1-16, atau tekan Enter untuk default): ")
        
        sps_options = {
            '1': ADS1256.ADS1256_DRATE_E['ADS1256_30000SPS'],
            '2': ADS1256.ADS1256_DRATE_E['ADS1256_15000SPS'],
            '3': ADS1256.ADS1256_DRATE_E['ADS1256_7500SPS'],
            '4': ADS1256.ADS1256_DRATE_E['ADS1256_3750SPS'],
            '5': ADS1256.ADS1256_DRATE_E['ADS1256_2000SPS'],
            '6': ADS1256.ADS1256_DRATE_E['ADS1256_1000SPS'],
            '7': ADS1256.ADS1256_DRATE_E['ADS1256_500SPS'],
            '8': ADS1256.ADS1256_DRATE_E['ADS1256_100SPS'],
            '9': ADS1256.ADS1256_DRATE_E['ADS1256_60SPS'],
            '10': ADS1256.ADS1256_DRATE_E['ADS1256_50SPS'],
            '11': ADS1256.ADS1256_DRATE_E['ADS1256_30SPS'],
            '12': ADS1256.ADS1256_DRATE_E['ADS1256_25SPS'],
            '13': ADS1256.ADS1256_DRATE_E['ADS1256_15SPS'],
            '14': ADS1256.ADS1256_DRATE_E['ADS1256_10SPS'],
            '15': ADS1256.ADS1256_DRATE_E['ADS1256_5SPS'],
            '16': ADS1256.ADS1256_DRATE_E['ADS1256_2d5SPS']
        }
        
        if choice and choice in sps_options:
            sps = sps_options[choice]
        
        # Menu untuk pengaturan Gain
        print("\n===== Pengaturan Gain =====")
        print("1. Gain 1 (default)")
        print("2. Gain 2")
        print("3. Gain 4")
        print("4. Gain 8")
        print("5. Gain 16")
        print("6. Gain 32")
        print("7. Gain 64")
        
        choice = input("Pilih gain (1-7, atau tekan Enter untuk default): ")
        
        gain_options = {
            '1': ADS1256.ADS1256_GAIN_E['ADS1256_GAIN_1'],
            '2': ADS1256.ADS1256_GAIN_E['ADS1256_GAIN_2'],
            '3': ADS1256.ADS1256_GAIN_E['ADS1256_GAIN_4'],
            '4': ADS1256.ADS1256_GAIN_E['ADS1256_GAIN_8'],
            '5': ADS1256.ADS1256_GAIN_E['ADS1256_GAIN_16'],
            '6': ADS1256.ADS1256_GAIN_E['ADS1256_GAIN_32'],
            '7': ADS1256.ADS1256_GAIN_E['ADS1256_GAIN_64']
        }
        
        if choice and choice in gain_options:
            gain = gain_options[choice]
        
        # Konfigurasi ADC dengan SPS dan Gain yang dipilih
        ADC.ADS1256_ConfigADC(gain, sps)
        
        # Set mode differential input
        ADC.ADS1256_SetMode(1)  # Mode 1 untuk differential input
        
        # Menu utama
        while True:
            print("\n===== Menu Utama =====")
            print("1. Uji Linearitas Ke-empat Input Differential")
            print("2. Uji Kecepatan SPS")
            print("3. Keluar")
            
            menu_choice = input("Pilih menu (1-3): ")
            
            if menu_choice == '1':
                # Jumlah pembacaan per channel
                num_readings = 5
                choice = input(f"\nJumlah pembacaan per channel (default {num_readings}): ")
                if choice and choice.isdigit():
                    num_readings = int(choice)
                
                while True:
                    # Lakukan pengujian pada semua channel
                    test_all_channels(ADC, num_readings)
                    
                    # Tanyakan apakah ingin mengukur lagi
                    choice = input("\nApakah ingin melakukan pengukuran linearitas lagi? (y/n): ")
                    if choice.lower() != 'y':
                        break
            
            elif menu_choice == '2':
                # Uji kecepatan SPS
                num_samples = 100
                choice = input(f"\nJumlah sampel untuk pengujian SPS (default {num_samples}): ")
                if choice and choice.isdigit():
                    num_samples = int(choice)
                
                while True:
                    # Lakukan pengujian SPS
                    test_sps_accuracy(ADC, sps, num_samples)
                    
                    # Tanyakan apakah ingin mengukur lagi
                    choice = input("\nApakah ingin melakukan pengujian SPS lagi? (y/n): ")
                    if choice.lower() != 'y':
                        break
            
            elif menu_choice == '3':
                print("Keluar dari program...")
                break
            
            else:
                print("Pilihan tidak valid, silakan coba lagi.")
    
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

if __name__ == "__main__":
    main()