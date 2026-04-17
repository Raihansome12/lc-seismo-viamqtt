import pymysql
import numpy as np
import json
import os
from obspy.core import UTCDateTime, Stream, Trace
from obspy import read_inventory
from datetime import datetime, timedelta

# Konfigurasi database MySQL (sesuaikan dengan database Anda)
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',    # Ganti dengan username MySQL Anda
    'password': 'Raihan@3012',  # Ganti dengan password MySQL Anda
    'database': 'seismic_monitoring',  # Ganti dengan nama database Anda
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}

# Konfigurasi tabel, nama file output, dan stationXML path
TABLE_NAME = 'seismic_readings'  # Ganti dengan nama tabel Anda
OUTPUT_FILE = 'output.mseed'  # Nama file output
STATION_XML_FILE = 'stationXML/IA.STMKG.xml'  # Path tetap ke file stationXML

# Variabel global untuk metadata seismik
STATION = "STMKG"  # Default kode stasiun 
NETWORK = "IA"     # Default kode jaringan
CHANNEL = "SHZ"    # Default kode kanal
LOCATION = "00"    # Default kode lokasi
SAMPLING_RATE = 50 # Default frekuensi sampling dalam Hz

def read_station_metadata(xml_file):
    """Membaca metadata seismik dari file stationXML"""
    global STATION, NETWORK, CHANNEL, LOCATION, SAMPLING_RATE
    
    try:
        if not os.path.exists(xml_file):
            print(f"File stationXML '{xml_file}' tidak ditemukan. Menggunakan nilai default.")
            return False
            
        print(f"Membaca metadata dari stationXML: {xml_file}")
        inventory = read_inventory(xml_file)
        
        # Mengambil data dari inventory
        # Catatan: Inventory bisa memiliki beberapa networks/stations/channels
        # Di sini kita mengambil data pertama untuk kesederhanaan
        if inventory and inventory[0]:
            NETWORK = inventory[0].code
            if inventory[0][0]:
                STATION = inventory[0][0].code
                if inventory[0][0][0]:
                    channel_obj = inventory[0][0][0]
                    CHANNEL = channel_obj.code
                    LOCATION = channel_obj.location_code
                    SAMPLING_RATE = channel_obj.sample_rate
                    
        print(f"Metadata yang terbaca:")
        print(f"  Network: {NETWORK}")
        print(f"  Station: {STATION}")
        print(f"  Channel: {CHANNEL}")
        print(f"  Location: {LOCATION}")
        print(f"  Sampling Rate: {SAMPLING_RATE} Hz")
        
        return True
        
    except Exception as e:
        print(f"Error saat membaca stationXML: {e}")
        print("Menggunakan nilai metadata default.")
        return False

def connect_to_mysql():
    """Membuat koneksi ke database MySQL menggunakan PyMySQL"""
    try:
        conn = pymysql.connect(**DB_CONFIG)
        return conn
    except pymysql.Error as e:
        print(f"Error saat menghubungkan ke MySQL: {e}")
        return None

def fetch_geophone_data(conn, start_time=None, end_time=None):
    """Mengambil data geophone dari database MySQL"""
    try:
        with conn.cursor() as cursor:
            query = f"SELECT adc_counts, reading_times FROM {TABLE_NAME}"
            
            # Tambahkan filter waktu jika disediakan
            if start_time and end_time:
                query += f" WHERE reading_times BETWEEN '{start_time}' AND '{end_time}'"
            elif start_time:
                query += f" WHERE reading_times >= '{start_time}'"
            elif end_time:
                query += f" WHERE reading_times <= '{end_time}'"
                
            query += " ORDER BY reading_times ASC"
            
            cursor.execute(query)
            records = cursor.fetchall()
            
            return records
    except pymysql.Error as e:
        print(f"Error saat mengambil data: {e}")
        return []

def parse_adc_counts(data_records):
    """Parse data adc_counts dan reading_times dari record database"""
    times = []
    data_arrays = []

    for record in data_records:
        try:
            # Parse adc_counts (string berformat JSON array)
            adc_counts_str = record['adc_counts']
            
            # Clean the string by removing extra quotes and brackets
            adc_counts_str = adc_counts_str.strip('"\'[]')
            
            # Split the string by comma and convert to float
            adc_counts = [float(x.strip()) for x in adc_counts_str.split(',')]
            
            # Parse timestamp
            reading_time = record['reading_times']
            
            # Menambahkan data ke list
            times.append(reading_time)
            data_arrays.append(adc_counts)
            
        except Exception as e:
            print(f"Error saat memproses record: {e}")
            print(f"Record yang bermasalah: {record}")
            continue
    
    return times, data_arrays

def create_mseed(times, data_arrays, output_file):
    """Membuat file MiniSEED dari data sensor"""
    # Membuat stream kosong
    st = Stream()
    
    # Mengonversi semua data menjadi array 1D
    all_data = []
    
    if not times:
        print("Tidak ada data yang dapat diproses.")
        return
    
    start_time = UTCDateTime(times[0])
    
    for adc_counts in data_arrays:
        all_data.extend(adc_counts)
    
    # Membuat Trace dengan semua data yang digabungkan
    trace = Trace(data=np.array(all_data))
    trace.stats.network = NETWORK
    trace.stats.station = STATION
    trace.stats.location = LOCATION
    trace.stats.channel = CHANNEL
    trace.stats.starttime = start_time
    trace.stats.sampling_rate = SAMPLING_RATE
    
    # Menambahkan trace ke stream
    st.append(trace)
    
    # Menyimpan stream sebagai file MiniSEED
    st.write(output_file, format="MSEED")
    print(f"File MiniSEED telah disimpan: {output_file}")

def get_time_range_option():
    """Fungsi untuk mendapatkan rentang waktu kustom dari pengguna"""
    print("\nMasukkan rentang waktu kustom:")
    
    while True:
        try:
            start_time = input("Masukkan waktu mulai (format: YYYY-MM-DD HH:MM:SS): ")
            # Validasi format waktu mulai
            datetime.strptime(start_time, '%Y-%m-%d %H:%M:%S')
            
            end_time = input("Masukkan waktu akhir (format: YYYY-MM-DD HH:MM:SS): ")
            # Validasi format waktu akhir
            datetime.strptime(end_time, '%Y-%m-%d %H:%M:%S')
            
            # Pastikan waktu akhir lebih besar dari waktu mulai
            if datetime.strptime(end_time, '%Y-%m-%d %H:%M:%S') <= datetime.strptime(start_time, '%Y-%m-%d %H:%M:%S'):
                print("Error: Waktu akhir harus lebih besar dari waktu mulai.")
                continue
                
            return start_time, end_time
            
        except ValueError:
            print("Format waktu tidak valid. Harap gunakan format: YYYY-MM-DD HH:MM:SS")
            print("Contoh: 2025-04-16 14:30:00")
            continue

# Fungsi get_station_xml_file dihapus karena menggunakan path tetap

def main():
    # Koneksi ke database
    print("Menghubungkan ke database MySQL menggunakan PyMySQL...")
    conn = connect_to_mysql()
    if not conn:
        return
    
    # Baca metadata dari stationXML dengan path tetap
    read_station_metadata(STATION_XML_FILE)
    
    # Minta pengguna untuk memilih rentang waktu
    print("Memilih rentang waktu untuk konversi data...")
    start_time, end_time = get_time_range_option()
    
    print(f"Menggunakan rentang waktu: {start_time} - {end_time}")
    
    # Ambil data dari database
    print("Mengambil data dari database...")
    data_records = fetch_geophone_data(conn, start_time, end_time)
    
    if not data_records:
        print("Tidak ada data yang ditemukan untuk rentang waktu yang ditentukan.")
        conn.close()
        return
    
    print(f"Berhasil mengambil {len(data_records)} records dari database.")
    
    # Parse data adc_counts dan reading_times
    print("Memproses data...")
    times, data_arrays = parse_adc_counts(data_records)
    
    if not times:
        print("Tidak ada data yang berhasil diproses. Pastikan format data benar.")
        conn.close()
        return
        
    print(f"Berhasil memproses {len(times)} records.")
    
    # Buat file MSEED
    print("Membuat file MSEED...")
    create_mseed(times, data_arrays, OUTPUT_FILE)
    
    conn.close()
    print("Program selesai.")

if __name__ == "__main__":
    main()