import spidev
import time
import RPi.GPIO as GPIO

# Konfigurasi pin GPIO
DRDY_PIN = 17
RST_PIN = 18
#CS_PIN = 22

# Inisialisasi GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setup(DRDY_PIN, GPIO.IN)
#GPIO.setup(CS_PIN, GPIO.OUT)
GPIO.setup(RST_PIN, GPIO.OUT)

# Inisialisasi SPI
spi = spidev.SpiDev()
spi.open(0, 0)  # SPI bus 0, device 0
spi.max_speed_hz = 1920000  # Set SPI speed to 1.92 MHz
#spi.mode = 0b01

# Fungsi untuk membaca data dari ADS1256
def read_ads1256():
    while GPIO.input(DRDY_PIN) == GPIO.HIGH:
        pass  # Tunggu sampai DRDY rendah

    ## Aktifkan CS (LOW)
    # GPIO.output(CS_PIN, GPIO.LOW)

    # Kirim perintah untuk membaca data
    spi.xfer2([0x01])  # Perintah RDATA
    time.sleep(0.0001)  # Tunggu sedikit

    # Baca 3 byte data (24-bit)
    data = spi.xfer2([0x00, 0x00, 0x00])
    adc_value = (data[0] << 16) | (data[1] << 8) | data[2]

    ## Nonaktifkan CS (HIGH)
    #GPIO.output(CS_PIN, GPIO.HIGH)

    # Konversi ke nilai signed 24-bit
    if adc_value & 0x800000:
        adc_value -= 0x1000000

    return adc_value

# Fungsi untuk mengatur channel differential (AIN0 - AIN1)
def set_channel_diff():
    ## Aktifkan CS (LOW)
    #GPIO.output(CS_PIN, GPIO.LOW)

    # Konfigurasi MUX untuk AIN0 dan AIN1
    spi.xfer2([0x50, 0x01])  # Perintah WREG, mulai dari register MUX
    spi.xfer2([0x00, 0x01])  # Tulis 0x01 ke register MUX (AIN0 - AIN1)

    ## Nonaktifkan CS (HIGH)
    #GPIO.output(CS_PIN, GPIO.HIGH)

# Fungsi untuk mengatur gain
def set_gain(gain):
    if gain not in [1, 2, 4, 8, 16, 32, 64]:
        raise ValueError("Gain tidak valid. Pilih dari [1, 2, 4, 8, 16, 32, 64].")
    gain_map = {1: 0x00, 2: 0x01, 4: 0x02, 8: 0x03, 16: 0x04, 32: 0x05, 64: 0x06}
    gain_value = gain_map[gain]
    spi.xfer2([0x50 | 0x02])  # Perintah WREG, mulai dari register ADCON
    spi.xfer2([0x00])  # Hanya 1 register yang ditulis
    current_adcon = spi.xfer2([0x00])[0]
    new_adcon = (current_adcon & 0xF8) | gain_value
    spi.xfer2([0x50 | 0x02])
    spi.xfer2([0x00])
    spi.xfer2([new_adcon])

# Fungsi untuk mengatur SPS
def set_sps(sps):
    valid_sps = {
        30000: 0xF0, 15000: 0xE0, 7500: 0xD0, 3750: 0xC0,
        2000: 0xB0, 1000: 0xA1, 500: 0x92, 100: 0x82,
        60: 0x72, 50: 0x63, 30: 0x53, 25: 0x43,
        15: 0x33, 10: 0x23, 5: 0x13, 2.5: 0x03
    }
    if sps not in valid_sps:
        raise ValueError("SPS tidak valid. Pilih dari [30000, 15000, 7500, 3750, 2000, 1000, 500, 100, 60, 50, 30, 25, 15, 10, 5, 2.5].")
    drate_value = valid_sps[sps]
    spi.xfer2([0x50 | 0x03])
    spi.xfer2([0x00])
    spi.xfer2([drate_value])

# Reset ADS1256
GPIO.output(RST_PIN, GPIO.LOW)
time.sleep(0.1)
GPIO.output(RST_PIN, GPIO.HIGH)
time.sleep(0.1)

# Set channel differential
set_channel_diff()

# Set gain dan SPS
set_gain(1)  # Gain = 1
set_sps(5)  # SPS = 1000

try:
    while True:
        adc_value = read_ads1256()
        print("ADC Value: ", adc_value)
        time.sleep(1)

except KeyboardInterrupt:
    print("Program dihentikan")

finally:
    spi.close()
    GPIO.cleanup()