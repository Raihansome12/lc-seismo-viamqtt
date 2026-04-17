#!/usr/bin/env python3
import time
import csv
from datetime import datetime
from pipyadc import ADS1256
from pipyadc.ADS1256_definitions import *
import waveshare_config

# Differential channel configuration
GEOPHONE = POS_AIN0 | NEG_AIN1  # Differential input AIN0-AIN1

# Measurement parameters
DURATION = 5  # seconds
SAMPLE_RATE = 50  # samples per second
GAIN = GAIN_1
FILENAME = "geophone_data_async.csv"

def setup_adc():
    """Configure the ADS1256 with specified parameters"""
    ads = ADS1256(waveshare_config)
    ads.drate = DRATE_50  # Set 50 SPS
    ads.pga_gain = 1  # Set gain to 1
    ads.mux = GEOPHONE  # Set the channel
    ads.sync()  # Sync to start new conversion cycle
    return ads

def collect_data(ads):
    """Collect data using read_async"""
    start_time = time.time()
    samples_collected = 0
    
    with open(FILENAME, 'w', newline='') as csvfile:
        csvwriter = csv.writer(csvfile)
        csvwriter.writerow(["Timestamp", "Raw Value", "Voltage"])
        
        print(f"Starting async measurement... Saving to {FILENAME}")
        
        while time.time() - start_time < DURATION:
            raw_value = ads.read_async()
            voltage = raw_value * ads.v_per_digit
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            
            csvwriter.writerow([timestamp, raw_value, voltage])
            samples_collected += 1
            
            elapsed = time.time() - start_time
            print(f"\rProgress: {elapsed:.2f}/{DURATION} seconds | Samples: {samples_collected}", end="")
    
    print("\nMeasurement complete.")
    return samples_collected

def main():
    ads = setup_adc()
    try:
        samples = collect_data(ads)
        print(f"\nActual sample rate: {samples/DURATION:.2f} SPS")
    finally:
        ads.stop()

if __name__ == "__main__":
    main()