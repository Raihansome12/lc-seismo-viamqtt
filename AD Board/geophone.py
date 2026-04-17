import time
import ADS1256
import RPi.GPIO as GPIO

try:
    ADC = ADS1256.ADS1256()
    if ADC.ADS1256_init() == -1:
        print("ADS1256 initialization failed. Exiting...")
        exit()

    sps = ADS1256.ADS1256_DRATE_E['ADS1256_50SPS']
    gain = ADS1256.ADS1256_GAIN_E['ADS1256_GAIN_1']
    ADC.ADS1256_ConfigADC(gain, sps) # Configure ADC with SPS and Gain
    
    ADC.ADS1256_SetMode(1) #  Set mode differential input

    while True:
        adc_value = ADC.ADS1256_GetChannalValue(0) # Channel measuerement
        voltage = adc_value * 5.0 / 0x7fffff

        print(f"Voltage: {voltage:.6f} V")

except KeyboardInterrupt:
    print("\nProgram dihentikan oleh pengguna.")

except Exception as e:
    print(f"Terjadi error: {e}")

finally:
    GPIO.cleanup()
    print("Program selesai.")