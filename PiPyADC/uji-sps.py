#!/usr/bin/env python3
import time
import logging
from pipyadc import ADS1256
from pipyadc.ADS1256_definitions import *
import waveshare_config
import csv
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.WARNING)  # Reduced logging to avoid clutter

def collect_adc_data(num_samples=1000, drate_setting=DRATE_50):
    """
    Mengumpulkan data ADC dengan pencatatan waktu untuk analisis interval
    
    Args:
        num_samples: Jumlah sampel yang akan diambil (default: 1000)
        drate_setting: Setting data rate untuk ADC (default: DRATE_50)
    """
    
    # Mapping data rate untuk menghitung interval teoritis
    drate_values = {
        DRATE_30000: 30000,
        DRATE_15000: 15000,
        DRATE_7500: 7500,
        DRATE_3750: 3750,
        DRATE_2000: 2000,
        DRATE_1000: 1000,
        DRATE_500: 500,
        DRATE_100: 100,
        DRATE_60: 60,
        DRATE_50: 50,
        DRATE_25: 25,
        DRATE_15: 15,
        DRATE_10: 10,
        DRATE_5: 5,
        DRATE_2_5: 2.5
    }
    
    current_sps = drate_values.get(drate_setting, 50)
    theoretical_interval = 1000 / current_sps  # dalam ms
    theoretical_total_time = num_samples / current_sps  # dalam detik
    
    print(f"=== ADC Data Collection Setup ===")
    print(f"Jumlah sampel: {num_samples}")
    print(f"SPS Setting: {current_sps}")
    print(f"Interval teoritis: {theoretical_interval:.2f} ms")
    print(f"Waktu total teoritis: {theoretical_total_time:.2f} detik")
    print(f"{'='*40}")
    
    try:
        # Inisialisasi ADC dengan PiPyADC
        with ADS1256(waveshare_config) as ads:
            # Konfigurasi ADC
            ads.drate = drate_setting
            ads.gain = GAIN_1  # Gain 1x
            
            # Kalibrasi otomatis
            print("Melakukan kalibrasi ADC...")
            ads.cal_self()
            
            # Definisi channel differential (AIN0-AIN1)
            channel_config = POS_AIN0 | NEG_AIN1
            
            # Siapkan data collection
            data_list = []
            start_time = time.time()
            
            print("Memulai pengumpulan data...")
            print("Tekan Ctrl+C untuk menghentikan pengumpulan data")
            
            for i in range(num_samples):
                # Catat waktu sebelum pembacaan
                sample_start_time = time.time()
                
                # Baca nilai ADC menggunakan PiPyADC
                adc_value = ads.read_oneshot(channel_config)
                voltage = adc_value * ads.v_per_digit
                
                # Catat waktu setelah pembacaan
                sample_end_time = time.time()
                
                # Hitung waktu relatif dari awal pengumpulan data
                relative_time = sample_start_time - start_time
                
                # Simpan data
                data_point = {
                    'sample_number': i + 1,
                    'timestamp': sample_start_time,
                    'relative_time_ms': relative_time * 1000,
                    'adc_raw': adc_value,
                    'voltage': voltage,
                    'read_duration_ms': (sample_end_time - sample_start_time) * 1000
                }
                data_list.append(data_point)
                
                # Progress indicator
                if (i + 1) % 100 == 0:
                    progress = (i + 1) / num_samples * 100
                    elapsed_time = time.time() - start_time
                    print(f"Progress: {progress:.1f}% ({i+1}/{num_samples}) - "
                          f"Elapsed: {elapsed_time:.2f}s - "
                          f"Voltage: {voltage:.6f}V")
            
            end_time = time.time()
            total_time = end_time - start_time
            
            # Analisis timing
            print(f"\n=== Analisis Timing ===")
            print(f"Total waktu pengumpulan: {total_time:.3f} detik")
            print(f"Waktu teoritis: {theoretical_total_time:.3f} detik")
            print(f"Selisih: {abs(total_time - theoretical_total_time):.3f} detik")
            print(f"Akurasi timing: {(theoretical_total_time/total_time)*100:.2f}%")
            
            # Hitung interval antar sampel
            intervals = []
            for i in range(1, len(data_list)):
                interval = data_list[i]['relative_time_ms'] - data_list[i-1]['relative_time_ms']
                intervals.append(interval)
            
            if intervals:
                avg_interval = sum(intervals) / len(intervals)
                min_interval = min(intervals)
                max_interval = max(intervals)
                std_dev = (sum([(x-avg_interval)**2 for x in intervals])/len(intervals))**0.5
                
                print(f"\n=== Analisis Interval ===")
                print(f"Interval rata-rata: {avg_interval:.3f} ms")
                print(f"Interval teoritis: {theoretical_interval:.3f} ms")
                print(f"Interval minimum: {min_interval:.3f} ms")
                print(f"Interval maximum: {max_interval:.3f} ms")
                print(f"Standar deviasi interval: {std_dev:.3f} ms")
                print(f"Akurasi interval: {(theoretical_interval/avg_interval)*100:.2f}%")
            
            # Simpan ke CSV
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"adc_data_{current_sps}sps_{num_samples}samples_{timestamp_str}.csv"
            
            with open(filename, 'w', newline='') as csvfile:
                fieldnames = ['sample_number', 'timestamp', 'relative_time_ms', 
                             'adc_raw', 'voltage', 'read_duration_ms']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                
                # Tulis header
                writer.writeheader()
                
                # Tulis data
                for data_point in data_list:
                    writer.writerow(data_point)
            
            print(f"\n=== File Tersimpan ===")
            print(f"Data berhasil disimpan ke: {filename}")
            print(f"Jumlah data: {len(data_list)} sampel")
            
            # Simpan juga file analisis
            analysis_filename = f"analysis_{current_sps}sps_{num_samples}samples_{timestamp_str}.txt"
            with open(analysis_filename, 'w') as f:
                f.write(f"=== Analisis ADC Data Collection ===\n")
                f.write(f"Tanggal: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Jumlah sampel: {num_samples}\n")
                f.write(f"SPS Setting: {current_sps}\n")
                f.write(f"Interval teoritis: {theoretical_interval:.3f} ms\n")
                f.write(f"Waktu total teoritis: {theoretical_total_time:.3f} detik\n\n")
                
                f.write(f"=== Hasil Pengukuran ===\n")
                f.write(f"Total waktu pengumpulan: {total_time:.3f} detik\n")
                f.write(f"Selisih waktu: {abs(total_time - theoretical_total_time):.3f} detik\n")
                f.write(f"Akurasi timing: {(theoretical_total_time/total_time)*100:.2f}%\n\n")
                
                if intervals:
                    f.write(f"=== Analisis Interval ===\n")
                    f.write(f"Interval rata-rata: {avg_interval:.3f} ms\n")
                    f.write(f"Interval minimum: {min_interval:.3f} ms\n")
                    f.write(f"Interval maximum: {max_interval:.3f} ms\n")
                    f.write(f"Standar deviasi: {std_dev:.3f} ms\n")
                    f.write(f"Akurasi interval: {(theoretical_interval/avg_interval)*100:.2f}%\n")
            
            print(f"Analisis tersimpan ke: {analysis_filename}")
            
    except KeyboardInterrupt:
        print(f"\nPengumpulan data dihentikan oleh pengguna pada sampel ke-{len(data_list)}")
        if data_list:
            # Simpan data yang sudah terkumpul
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"adc_data_partial_{len(data_list)}samples_{timestamp_str}.csv"
            
            with open(filename, 'w', newline='') as csvfile:
                fieldnames = ['sample_number', 'timestamp', 'relative_time_ms', 
                             'adc_raw', 'voltage', 'read_duration_ms']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                for data_point in data_list:
                    writer.writerow(data_point)
            
            print(f"Data parsial tersimpan ke: {filename}")
            
    except Exception as e:
        print(f"Terjadi error: {e}")
    finally:
        print("Program selesai.")

def main():
    """
    Fungsi utama untuk menjalankan pengumpulan data
    """
    print("=== ADC Data Logger dengan Analisis Timing (PiPyADC) ===")
    print("Program ini akan mengumpulkan data ADC dan menganalisis akurasi timing")
    
    # Konfigurasi yang bisa diubah
    NUM_SAMPLES = 1000
    DRATE_SETTING = DRATE_50  # Default 50 SPS
    
    # Pilihan data rate lain yang bisa digunakan:
    # DRATE_100     # 100 SPS -> 10ms interval
    # DRATE_25      # 25 SPS -> 40ms interval
    # DRATE_10      # 10 SPS -> 100ms interval
    # DRATE_5       # 5 SPS -> 200ms interval
    # DRATE_2_5     # 2.5 SPS -> 400ms interval
    
    print(f"\nKonfigurasi:")
    print(f"- Jumlah sampel: {NUM_SAMPLES}")
    print(f"- Channel: AIN0-AIN1 (differential)")
    print(f"- Gain: 1x")
    
    collect_adc_data(NUM_SAMPLES, DRATE_SETTING)

if __name__ == "__main__":
    main()