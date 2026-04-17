import time
import ADS1256
import RPi.GPIO as GPIO
import csv
from datetime import datetime

def collect_adc_data(num_samples=1000, sps_setting=ADS1256.ADS1256_DRATE_E['ADS1256_50SPS']):
    """
    Mengumpulkan data ADC dengan pencatatan waktu untuk analisis interval
    
    Args:
        num_samples: Jumlah sampel yang akan diambil (default: 1000)
        sps_setting: Setting SPS untuk ADC (default: 50 SPS)
    """
    
    # Mapping SPS untuk menghitung interval teoritis
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
        ADS1256.ADS1256_DRATE_E['ADS1256_25SPS']: 25,
        ADS1256.ADS1256_DRATE_E['ADS1256_15SPS']: 15,
        ADS1256.ADS1256_DRATE_E['ADS1256_10SPS']: 10,
        ADS1256.ADS1256_DRATE_E['ADS1256_5SPS']: 5,
        ADS1256.ADS1256_DRATE_E['ADS1256_2d5SPS']: 2.5
    }
    
    current_sps = sps_values.get(sps_setting, 50)
    theoretical_interval = 1000 / current_sps  # dalam ms
    theoretical_total_time = num_samples / current_sps  # dalam detik
    
    print(f"=== ADC Data Collection Setup ===")
    print(f"Jumlah sampel: {num_samples}")
    print(f"SPS Setting: {current_sps}")
    print(f"Interval teoritis: {theoretical_interval:.2f} ms")
    print(f"Waktu total teoritis: {theoretical_total_time:.2f} detik")
    print(f"{'='*40}")
    
    try:
        # Inisialisasi ADC
        ADC = ADS1256.ADS1256()
        if ADC.ADS1256_init() == -1:
            print("ADS1256 initialization failed. Exiting...")
            return
        
        # Konfigurasi ADC
        gain = ADS1256.ADS1256_GAIN_E['ADS1256_GAIN_1']
        ADC.ADS1256_ConfigADC(gain, sps_setting)
        ADC.ADS1256_SetMode(1)  # Set mode differential input
        
        # Siapkan data collection
        data_list = []
        start_time = time.time()
        
        print("Memulai pengumpulan data...")
        print("Tekan Ctrl+C untuk menghentikan pengumpulan data")
        
        for i in range(num_samples):
            # Catat waktu sebelum pembacaan
            sample_start_time = time.time()
            
            # Baca nilai ADC
            adc_value = ADC.ADS1256_GetChannalValue(0)
            voltage = adc_value * 5.0 / 0x7fffff
            
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
            
            print(f"\n=== Analisis Interval ===")
            print(f"Interval rata-rata: {avg_interval:.3f} ms")
            print(f"Interval teoritis: {theoretical_interval:.3f} ms")
            print(f"Interval minimum: {min_interval:.3f} ms")
            print(f"Interval maximum: {max_interval:.3f} ms")
            print(f"Standar deviasi interval: {(sum([(x-avg_interval)**2 for x in intervals])/len(intervals))**0.5:.3f} ms")
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
                f.write(f"Standar deviasi: {(sum([(x-avg_interval)**2 for x in intervals])/len(intervals))**0.5:.3f} ms\n")
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
        GPIO.cleanup()
        print("Program selesai.")

def main():
    """
    Fungsi utama untuk menjalankan pengumpulan data
    """
    print("=== ADC Data Logger dengan Analisis Timing ===")
    print("Program ini akan mengumpulkan data ADC dan menganalisis akurasi timing")
    
    # Konfigurasi yang bisa diubah
    NUM_SAMPLES = 1000
    SPS_SETTING = ADS1256.ADS1256_DRATE_E['ADS1256_50SPS']  # Ubah sesuai kebutuhan
    
    # Pilihan SPS lain yang bisa digunakan:
    # ADS1256.ADS1256_DRATE_E['ADS1256_100SPS']   # 100 SPS -> 10ms interval
    # ADS1256.ADS1256_DRATE_E['ADS1256_25SPS']    # 25 SPS -> 40ms interval
    # ADS1256.ADS1256_DRATE_E['ADS1256_10SPS']    # 10 SPS -> 100ms interval
    
    collect_adc_data(NUM_SAMPLES, SPS_SETTING)

if __name__ == "__main__":
    main()