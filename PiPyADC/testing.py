#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ADS1256 Implementation Examples
Implementasi untuk uji SPS, linearitas, dan aplikasi geophone
"""

import time
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime
import csv
import json
from pipyadc import ADS1256
from ADS1256_definitions import *

class ADS1256Controller:
    """
    Controller class untuk ADS1256 dengan berbagai fungsi pengujian
    """
    
    def __init__(self):
        """Initialize ADS1256 dengan konfigurasi default"""
        try:
            self.ads = ADS1256()
            print(f"ADS1256 initialized successfully. Chip ID: {self.ads.chip_ID}")
            
            # Konfigurasi dasar
            self.ads.v_ref = 2.5  # Reference voltage
            self.ads.pga_gain = 1  # Gain = 1
            
            # Channel definitions untuk differential measurement
            self.channels = {
                'CH0': POS_AIN0 | NEG_AIN1,  # AIN0 - AIN1
                'CH1': POS_AIN2 | NEG_AIN3,  # AIN2 - AIN3
                'CH2': POS_AIN4 | NEG_AIN5,  # AIN4 - AIN5
                'CH3': POS_AIN6 | NEG_AIN7   # AIN6 - AIN7
            }
            
        except Exception as e:
            print(f"Error initializing ADS1256: {e}")
            raise

    def voltage_from_raw(self, raw_value):
        """Convert raw ADC value to voltage"""
        return raw_value * self.ads.v_per_digit

    def set_data_rate(self, sps):
        """Set sampling rate berdasarkan SPS yang diinginkan"""
        sps_mapping = {
            2.5: DRATE_2_5,
            5: DRATE_5,
            10: DRATE_10,
            15: DRATE_15,
            25: DRATE_25,
            30: DRATE_30,
            50: DRATE_50,
            60: DRATE_60,
            100: DRATE_100,
            500: DRATE_500,
            1000: DRATE_1000,
            2000: DRATE_2000,
            3750: DRATE_3750,
            7500: DRATE_7500,
            15000: DRATE_15000,
            30000: DRATE_30000
        }
        
        if sps in sps_mapping:
            self.ads.drate = sps_mapping[sps]
            print(f"Data rate set to {sps} SPS")
        else:
            available_rates = list(sps_mapping.keys())
            print(f"Invalid SPS. Available rates: {available_rates}")
            raise ValueError(f"SPS {sps} not supported")

    def test_sps_4channel(self, target_sps, n_samples=1000):
        """
        Test 1: Uji SPS untuk 4 channel differential
        
        Args:
            target_sps: Target sampling rate
            n_samples: Jumlah sample yang akan diambil
        """
        print(f"\n=== TEST SPS 4 CHANNEL DIFFERENTIAL ===")
        print(f"Target SPS: {target_sps}")
        print(f"Number of samples: {n_samples}")
        
        # Set data rate
        self.set_data_rate(target_sps)
        
        # Sequence untuk 4 channel differential
        ch_sequence = [
            self.channels['CH0'],
            self.channels['CH1'], 
            self.channels['CH2'],
            self.channels['CH3']
        ]
        
        # Buffer untuk menyimpan hasil
        results = {
            'timestamps': [],
            'CH0': [],
            'CH1': [],
            'CH2': [],
            'CH3': [],
            'raw_CH0': [],
            'raw_CH1': [],
            'raw_CH2': [],
            'raw_CH3': []
        }
        
        print("Starting acquisition...")
        start_time = time.time()
        
        # Sinkronisasi awal
        self.ads.sync()
        
        for sample in range(n_samples):
            cycle_start = time.time()
            
            # Baca sequence 4 channel
            raw_values = self.ads.read_sequence(ch_sequence)
            
            timestamp = time.time()
            results['timestamps'].append(timestamp - start_time)
            
            # Store raw dan voltage values
            for i, ch_name in enumerate(['CH0', 'CH1', 'CH2', 'CH3']):
                raw_val = raw_values[i]
                voltage = self.voltage_from_raw(raw_val)
                
                results[f'raw_{ch_name}'].append(raw_val)
                results[ch_name].append(voltage)
            
            # Progress indicator
            if (sample + 1) % 100 == 0:
                print(f"Progress: {sample + 1}/{n_samples} samples")
        
        end_time = time.time()
        total_time = end_time - start_time
        actual_sps = n_samples / total_time
        
        # Analisis hasil
        print(f"\n=== RESULTS ===")
        print(f"Total time: {total_time:.3f} seconds")
        print(f"Target SPS: {target_sps}")
        print(f"Actual SPS: {actual_sps:.2f}")
        print(f"SPS Error: {abs(actual_sps - target_sps)/target_sps*100:.2f}%")
        
        # Statistik untuk setiap channel
        for ch_name in ['CH0', 'CH1', 'CH2', 'CH3']:
            voltages = results[ch_name]
            print(f"\n{ch_name} Statistics:")
            print(f"  Mean: {np.mean(voltages):.6f} V")
            print(f"  Std:  {np.std(voltages):.6f} V")
            print(f"  Min:  {np.min(voltages):.6f} V")
            print(f"  Max:  {np.max(voltages):.6f} V")
        
        # Save hasil ke file
        self.save_sps_test_results(results, target_sps, actual_sps, n_samples)
        
        return results, actual_sps

    def test_linearity_4channel(self, sps=100, n_readings=5):
        """
        Test 2: Uji linearitas untuk 4 channel differential
        
        Args:
            sps: Sampling rate untuk test
            n_readings: Jumlah pembacaan untuk setiap test
        """
        print(f"\n=== TEST LINEARITAS 4 CHANNEL DIFFERENTIAL ===")
        print(f"SPS: {sps}")
        print(f"Number of readings per test: {n_readings}")
        
        # Set data rate
        self.set_data_rate(sps)
        
        # Channel sequence
        ch_sequence = [
            self.channels['CH0'],
            self.channels['CH1'],
            self.channels['CH2'], 
            self.channels['CH3']
        ]
        
        linearity_results = {
            'test_info': {
                'sps': sps,
                'n_readings': n_readings,
                'timestamp': datetime.now().isoformat()
            },
            'readings': []
        }
        
        print("\nPerforming linearity test...")
        print("Ambil pembacaan dengan kondisi input yang stabil")
        
        for reading_num in range(n_readings):
            print(f"\nReading {reading_num + 1}/{n_readings}")
            input("Press Enter when ready for next reading...")
            
            # Ambil beberapa sample untuk averaging
            samples_per_reading = 50
            reading_data = {
                'reading_number': reading_num + 1,
                'timestamp': time.time(),
                'channels': {}
            }
            
            # Buffer untuk averaging
            ch_samples = {ch: [] for ch in ['CH0', 'CH1', 'CH2', 'CH3']}
            
            # Sinkronisasi
            self.ads.sync()
            
            # Ambil samples
            for _ in range(samples_per_reading):
                raw_values = self.ads.read_sequence(ch_sequence)
                
                for i, ch_name in enumerate(['CH0', 'CH1', 'CH2', 'CH3']):
                    voltage = self.voltage_from_raw(raw_values[i])
                    ch_samples[ch_name].append(voltage)
            
            # Hitung statistik untuk setiap channel
            for ch_name in ['CH0', 'CH1', 'CH2', 'CH3']:
                samples = ch_samples[ch_name]
                reading_data['channels'][ch_name] = {
                    'mean': np.mean(samples),
                    'std': np.std(samples),
                    'min': np.min(samples),
                    'max': np.max(samples),
                    'samples': samples
                }
                
                print(f"  {ch_name}: {np.mean(samples):.6f} ± {np.std(samples):.6f} V")
            
            linearity_results['readings'].append(reading_data)
        
        # Analisis linearitas
        self.analyze_linearity(linearity_results)
        
        # Save results
        self.save_linearity_results(linearity_results)
        
        return linearity_results

    def geophone_monitoring(self, duration_minutes=60, sps=50, save_interval=10):
        """
        Test 3: Implementasi untuk sensor geophone (1 channel SHZ)
        
        Args:
            duration_minutes: Durasi monitoring dalam menit
            sps: Sampling rate (50 SPS)
            save_interval: Interval penyimpanan data (detik)
        """
        print(f"\n=== GEOPHONE MONITORING SYSTEM ===")
        print(f"Duration: {duration_minutes} minutes")
        print(f"Sampling rate: {sps} SPS")
        print(f"Save interval: {save_interval} seconds")
        
        # Set data rate untuk 50 SPS
        self.set_data_rate(sps)
        
        # Geophone biasanya single-ended, gunakan AINCOM sebagai reference
        geophone_channel = POS_AIN0 | NEG_AINCOM  # AIN0 vs AINCOM
        
        # Set higher gain untuk geophone (signal biasanya kecil)
        self.ads.pga_gain = 64  # Gain tinggi untuk sinyal geophone
        print(f"PGA Gain set to: {self.ads.pga_gain}")
        print(f"Voltage per digit: {self.ads.v_per_digit:.9f} V")
        
        # Data storage
        monitoring_data = {
            'config': {
                'sps': sps,
                'duration_minutes': duration_minutes,
                'gain': self.ads.pga_gain,
                'v_ref': self.ads.v_ref,
                'start_time': datetime.now().isoformat()
            },
            'data': {
                'timestamps': [],
                'raw_values': [],
                'voltages': [],
                'accelerations': []  # Akan dihitung dari voltage
            }
        }
        
        print("\nStarting geophone monitoring...")
        print("Press Ctrl+C to stop monitoring early")
        
        start_time = time.time()
        end_time = start_time + (duration_minutes * 60)
        last_save_time = start_time
        sample_count = 0
        
        try:
            # Set channel dan sync
            self.ads.mux = geophone_channel
            self.ads.sync()
            
            while time.time() < end_time:
                current_time = time.time()
                
                # Baca data geophone
                raw_value = self.ads.read_async()
                voltage = self.voltage_from_raw(raw_value)
                
                # Convert ke acceleration (tergantung sensitivitas geophone)
                # Asumsi: 1 V/g sensitivity, adjust sesuai spec geophone
                acceleration = voltage / 1.0  # dalam g
                
                # Store data
                monitoring_data['data']['timestamps'].append(current_time - start_time)
                monitoring_data['data']['raw_values'].append(raw_value)
                monitoring_data['data']['voltages'].append(voltage)
                monitoring_data['data']['accelerations'].append(acceleration)
                
                sample_count += 1
                
                # Progress dan statistik real-time
                if sample_count % (sps * 5) == 0:  # Setiap 5 detik
                    elapsed = current_time - start_time
                    actual_sps = sample_count / elapsed if elapsed > 0 else 0
                    
                    print(f"Time: {elapsed:.1f}s, Samples: {sample_count}, "
                          f"SPS: {actual_sps:.1f}, Current: {voltage:.6f}V ({acceleration:.6f}g)")
                
                # Save data secara periodik
                if current_time - last_save_time >= save_interval:
                    self.save_geophone_data(monitoring_data, sample_count)
                    last_save_time = current_time
                
                # Deteksi event (ambang batas)
                if abs(acceleration) > 0.1:  # 0.1g threshold
                    print(f"EVENT DETECTED! Acceleration: {acceleration:.6f}g at {elapsed:.2f}s")
        
        except KeyboardInterrupt:
            print("\nMonitoring stopped by user")
        
        # Final save
        total_time = time.time() - start_time
        actual_sps = sample_count / total_time
        
        print(f"\n=== MONITORING COMPLETE ===")
        print(f"Total time: {total_time:.2f} seconds")
        print(f"Total samples: {sample_count}")
        print(f"Average SPS: {actual_sps:.2f}")
        
        # Analisis sinyal
        self.analyze_geophone_data(monitoring_data)
        
        # Final save
        self.save_geophone_data(monitoring_data, sample_count, final=True)
        
        return monitoring_data

    def analyze_linearity(self, results):
        """Analisis linearitas dari hasil pengujian"""
        print(f"\n=== LINEARITY ANALYSIS ===")
        
        for ch_name in ['CH0', 'CH1', 'CH2', 'CH3']:
            means = [reading['channels'][ch_name]['mean'] for reading in results['readings']]
            stds = [reading['channels'][ch_name]['std'] for reading in results['readings']]
            
            print(f"\n{ch_name} Linearity:")
            print(f"  Mean values: {[f'{v:.6f}' for v in means]}")
            print(f"  Std dev: {[f'{v:.6f}' for v in stds]}")
            print(f"  Range: {np.max(means) - np.min(means):.6f} V")
            print(f"  Repeatability (avg std): {np.mean(stds):.6f} V")

    def analyze_geophone_data(self, data):
        """Analisis data geophone"""
        voltages = np.array(data['data']['voltages'])
        accelerations = np.array(data['data']['accelerations'])
        
        print(f"\n=== GEOPHONE DATA ANALYSIS ===")
        print(f"Signal Statistics:")
        print(f"  Voltage - Mean: {np.mean(voltages):.6f} V, RMS: {np.sqrt(np.mean(voltages**2)):.6f} V")
        print(f"  Acceleration - Mean: {np.mean(accelerations):.6f} g, RMS: {np.sqrt(np.mean(accelerations**2)):.6f} g")
        print(f"  Peak acceleration: {np.max(np.abs(accelerations)):.6f} g")
        
        # Deteksi events
        threshold = 0.05  # 0.05g threshold
        events = np.where(np.abs(accelerations) > threshold)[0]
        print(f"  Events detected (>{threshold}g): {len(events)}")

    def save_sps_test_results(self, results, target_sps, actual_sps, n_samples):
        """Save SPS test results"""
        filename = f"sps_test_{target_sps}sps_{n_samples}samples_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        with open(filename, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['Timestamp', 'CH0_V', 'CH1_V', 'CH2_V', 'CH3_V', 
                           'CH0_Raw', 'CH1_Raw', 'CH2_Raw', 'CH3_Raw'])
            
            for i in range(len(results['timestamps'])):
                row = [results['timestamps'][i]]
                row.extend([results[f'CH{j}'][i] for j in range(4)])
                row.extend([results[f'raw_CH{j}'][i] for j in range(4)])
                writer.writerow(row)
        
        print(f"SPS test results saved to: {filename}")

    def save_linearity_results(self, results):
        """Save linearity test results"""
        filename = f"linearity_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(filename, 'w') as f:
            json.dump(results, f, indent=2)
        
        print(f"Linearity test results saved to: {filename}")

    def save_geophone_data(self, data, sample_count, final=False):
        """Save geophone monitoring data"""
        suffix = "final" if final else f"samples_{sample_count}"
        filename = f"geophone_data_{suffix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
        
        if final:
            print(f"Final geophone data saved to: {filename}")


def main():
    """Main function untuk menjalankan semua test"""
    try:
        # Initialize controller
        controller = ADS1256Controller()
        
        print("ADS1256 Test Suite")
        print("1. SPS Test (4 Channel Differential)")
        print("2. Linearity Test (4 Channel Differential)")  
        print("3. Geophone Monitoring (1 Channel)")
        print("4. Run All Tests")
        
        choice = input("\nSelect test (1-4): ")
        
        if choice == '1':
            # Test 1: SPS Test
            sps = int(input("Enter target SPS (e.g., 100): "))
            n_samples = int(input("Enter number of samples (e.g., 1000): "))
            controller.test_sps_4channel(sps, n_samples)
            
        elif choice == '2':
            # Test 2: Linearity Test
            sps = int(input("Enter SPS for linearity test (e.g., 100): "))
            n_readings = int(input("Enter number of readings (e.g., 5): "))
            controller.test_linearity_4channel(sps, n_readings)
            
        elif choice == '3':
            # Test 3: Geophone Monitoring
            duration = float(input("Enter monitoring duration in minutes (e.g., 5): "))
            controller.geophone_monitoring(duration_minutes=duration, sps=50)
            
        elif choice == '4':
            # Run all tests
            print("Running all tests...")
            
            # SPS Test
            controller.test_sps_4channel(100, 500)
            
            # Linearity Test  
            controller.test_linearity_4channel(100, 3)
            
            # Geophone Test (short duration)
            controller.geophone_monitoring(duration_minutes=2, sps=50)
            
        else:
            print("Invalid choice")
    
    except Exception as e:
        print(f"Error: {e}")
    
    finally:
        print("Test completed.")


if __name__ == "__main__":
    main()