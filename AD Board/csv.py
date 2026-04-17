#!/usr/bin/python
# -*- coding:utf-8 -*-

import time
import ADS1256
import RPi.GPIO as GPIO
import csv
from datetime import datetime

# Configuration
DURATION = 5  # seconds
SAMPLE_RATE = 50  # samples per second
CSV_FILENAME = "geophone_data.csv"
CHANNEL = 0  # Differential channel 0 (AIN0-AIN1)

try:
    # Initialize ADC
    ADC = ADS1256.ADS1256()
    ADC.ADS1256_init()
    
    # Set to differential mode (channel 0 = AIN0-AIN1)
    ADC.ADS1256_SetMode(1)  # 1 = Differential mode
    
    # Configure ADC with gain 1 and 50 SPS (already done in init, but can be changed if needed)
    # ADC.ADS1256_ConfigADC(ADS1256.ADS1256_GAIN_E['ADS1256_GAIN_1'], 
    #                      ADS1256.ADS1256_DRATE_E['ADS1256_50SPS'])
    
    # Open CSV file for writing
    with open(CSV_FILENAME, 'w') as csvfile:
        csvwriter = csv.writer(csvfile)
        csvwriter.writerow(['Timestamp', 'ADC Value', 'Voltage'])
        
        print(f"Starting data acquisition for {DURATION} seconds...")
        start_time = time.time()
        sample_count = 0
        
        while time.time() - start_time < DURATION:
            # Get current timestamp with microseconds
            timestamp = datetime.now().isoformat(timespec='microseconds')
            
            # Read from differential channel 0 (AIN0-AIN1)
            adc_value = ADC.ADS1256_GetChannalValue(CHANNEL)
            
            # Convert to voltage (assuming 5V reference)
            voltage = adc_value * 5.0 / 0x7fffff
            
            # Write to CSV
            csvwriter.writerow([timestamp, adc_value, voltage])
            sample_count += 1
            
            # Small delay to achieve approximately 50 SPS
            # The actual timing will be determined by the ADC conversion time
            time.sleep(1.0/SAMPLE_RATE - 0.001)  # Adjust if needed
            
        print(f"Data acquisition complete. Collected {sample_count} samples.")
        print(f"Average sample rate: {sample_count/DURATION:.2f} SPS")
        
except Exception as e:
    print(f"Error: {str(e)}")
finally:
    GPIO.cleanup()
    print("\r\nProgram end")