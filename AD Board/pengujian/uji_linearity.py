#!/usr/bin/python
# -*- coding:utf-8 -*-

import time
import ADS1256
import RPi.GPIO as GPIO
import statistics
import os

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
        
        # Jumlah pembacaan per channel
        num_readings = 5
        choice = input(f"\nJumlah pembacaan per channel (default {num_readings}): ")
        if choice and choice.isdigit():
            num_readings = int(choice)
        
        while True:
            # Lakukan pengujian pada semua channel
            test_all_channels(ADC, num_readings)
            
            # Tanyakan apakah ingin mengukur lagi
            choice = input("\nApakah ingin melakukan pengukuran lagi? (y/n): ")
            if choice.lower() != 'y':
                break
    
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