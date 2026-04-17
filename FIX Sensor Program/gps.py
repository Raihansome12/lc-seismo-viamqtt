import serial
import pynmea2
from datetime import datetime
import csv

# Konfigurasi serial port
GPS_PORT = '/dev/serial0'  # Port UART pada Raspberry Pi
BAUD_RATE = 9600  # Kecepatan baud GPS Ublox-7M
OUTPUT_FILE = 'ublox-7m_gps_data.csv'                                      

gps_serial = serial.Serial(GPS_PORT, BAUD_RATE, timeout=1)
data = []

print("Mengumpulkan 50 data GPS dari NEO-7M...")

while len(data) < 50:
    gps_data = gps_serial.readline().decode('ascii', errors='ignore')
    if gps_data.startswith('$GNGGA') or gps_data.startswith('$GPGGA'):
        try:
            msg = pynmea2.parse(gps_data)
            lat = msg.latitude
            lon = msg.longitude
            timestamp = datetime.now().isoformat()  # Bisa diganti msg.timestamp jika ingin waktu GPS
            data.append((lat, lon, timestamp))
            print(f"{len(data)} - Lat: {lat}, Lon: {lon}")
        except pynmea2.ParseError:
            continue

# Simpan ke CSV
with open(OUTPUT_FILE, 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['latitude', 'longitude', 'timestamp'])
    writer.writerows(data)

print("Selesai. Data disimpan di", OUTPUT_FILE)