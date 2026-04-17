import pymysql
import numpy as np
import os
import io
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

# Konfigurasi tabel dan stationXML path
READINGS_TABLE = 'seismic_readings'  # Tabel data seismik
MSEED_TABLE = 'mseed_files'  # Tabel untuk menyimpan file MSEED
STATION_XML_FILE = r"C:\Users\raiha\OneDrive\Desktop\Program Skripsi\MSEED & PPSD\stationXML\IA.STMKG.xml" 

# Variabel global untuk metadata seismik
STATION = "STMKG"  # Default kode stasiun 
NETWORK = "IA"     # Default kode jaringan
CHANNEL = "SHZ"    # Default kode kanal
LOCATION = "00"    # Default kode lokasi
SAMPLING_RATE = 50 # Default frekuensi sampling dalam Hz

# Tetapkan batas minimum durasi sesi (dalam detik)
MIN_SESSION_DURATION = 60  # 1 menit

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

def fetch_all_geophone_data(conn):
    """Mengambil semua data geophone dari database MySQL, terurut berdasarkan waktu"""
    try:
        with conn.cursor() as cursor:
            query = f"SELECT adc_counts, reading_times FROM {READINGS_TABLE} ORDER BY reading_times ASC"
            cursor.execute(query)
            records = cursor.fetchall()
            return records
    except pymysql.Error as e:
        print(f"Error saat mengambil data: {e}")
        return []

def parse_adc_counts(records):
    """Parse data adc_counts dan reading_times dari record database"""
    parsed_data = []

    for record in records:
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
            parsed_data.append({
                'time': reading_time,
                'data': adc_counts
            })
            
        except Exception as e:
            print(f"Error saat memproses record: {e}")
            print(f"Record yang bermasalah: {record}")
            continue
    
    return parsed_data

def detect_sessions(parsed_data):
    """Mendeteksi sesi pengiriman data berdasarkan selisih waktu"""
    if not parsed_data:
        return []
        
    sessions = []
    current_session = [parsed_data[0]]
    
    # Asumsi selisih normal adalah 0.5 detik
    EXPECTED_DIFF = timedelta(seconds=0.5)
    # Batas toleransi (kita gunakan 2x selisih normal)
    MAX_DIFF = timedelta(seconds=2.0)
    
    for i in range(1, len(parsed_data)):
        current_time = parsed_data[i]['time']
        prev_time = parsed_data[i-1]['time']
        
        # Hitung selisih waktu
        time_diff = current_time - prev_time
        
        # Jika selisih waktu melebihi batas toleransi
        if time_diff > MAX_DIFF:
            # Simpan sesi saat ini jika ada data
            if current_session:
                sessions.append(current_session)
            
            # Mulai sesi baru
            current_session = [parsed_data[i]]
        else:
            # Tambahkan data ke sesi saat ini
            current_session.append(parsed_data[i])
    
    # Tambahkan sesi terakhir jika ada
    if current_session:
        sessions.append(current_session)
    
    return sessions

def create_mseed_binary(session):
    """Membuat binary MSEED dari data sesi tertentu"""
    if not session:
        print("Tidak ada data dalam sesi yang diberikan.")
        return None
    
    # Membuat stream kosong
    st = Stream()
    
    # Mengonversi semua data menjadi array 1D
    all_data = []
    
    start_time = UTCDateTime(session[0]['time'])
    
    for item in session:
        all_data.extend(item['data'])
    
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
    
    # Menyimpan stream sebagai bytes di memory
    buffer = io.BytesIO()
    st.write(buffer, format="MSEED")
    buffer.seek(0)
    
    # Mengembalikan binary data
    return buffer.read()

def insert_mseed_to_database(conn, session_number, start_time, end_time, mseed_binary):
    """Menyimpan file MSEED ke dalam tabel mseed_files"""
    try:
        with conn.cursor() as cursor:
            # Format nama file sesuai dengan permintaan
            formatted_start = start_time.strftime('%Y%m%d.%H%M%S')
            formatted_end = end_time.strftime('%H%M%S')
            filename = f"{NETWORK}.{STATION}.{CHANNEL}_{formatted_start}-{formatted_end}.mseed"
            
            # Query untuk menyimpan data
            query = f"""
                INSERT INTO {MSEED_TABLE} (filename, start_time, end_time, content, created_at, updated_at)
                VALUES (%s, %s, %s, %s, NOW(), NOW())
            """
            
            cursor.execute(query, (filename, start_time, end_time, mseed_binary))
            conn.commit()
            
            return True
    except pymysql.Error as e:
        print(f"Error saat menyimpan MSEED ke database: {e}")
        return False

def format_time_for_display(dt):
    """Format datetime untuk tampilan"""
    return dt.strftime('%Y-%m-%d %H-%M-%S')

def display_sessions_info(sessions):
    """Menampilkan informasi tentang sesi-sesi yang terdeteksi"""
    print("\n" + "="*80)
    print(f"{'INFORMASI SESI SEISMIK':^80}")
    print("="*80)
    
    print(f"\nTotal sesi terdeteksi: {len(sessions)}")
    valid_sessions = []
    invalid_sessions = []
    
    for i, session in enumerate(sessions):
        start_time = session[0]['time']
        end_time = session[-1]['time']
        duration = (end_time - start_time).total_seconds()
        
        session_info = {
            'index': i,
            'start_time': start_time,
            'end_time': end_time,
            'duration': duration,
            'data': session
        }
        
        if duration >= MIN_SESSION_DURATION:
            valid_sessions.append(session_info)
        else:
            invalid_sessions.append(session_info)
    
    # Tampilkan sesi valid
    if valid_sessions:
        print("\n" + "-"*80)
        print(f"{'SESI VALID (>= '+str(MIN_SESSION_DURATION)+' detik)':^80}")
        print("-"*80)
        
        for i, session in enumerate(valid_sessions):
            print(f"\nSesi Valid #{i+1}:")
            print(f"  Waktu mulai : {format_time_for_display(session['start_time'])}")
            print(f"  Waktu akhir : {format_time_for_display(session['end_time'])}")
            print(f"  Durasi      : {session['duration']:.2f} detik ({session['duration']/60:.2f} menit)")
    else:
        print("\nTidak ada sesi valid yang terdeteksi!")
    
    # Tampilkan sesi tidak valid
    if invalid_sessions:
        print("\n" + "-"*80)
        print(f"{'SESI TIDAK VALID (< '+str(MIN_SESSION_DURATION)+' detik)':^80}")
        print("-"*80)
        
        for i, session in enumerate(invalid_sessions):
            print(f"\nSesi Tidak Valid #{i+1}:")
            print(f"  Waktu mulai : {format_time_for_display(session['start_time'])}")
            print(f"  Waktu akhir : {format_time_for_display(session['end_time'])}")
            print(f"  Durasi      : {session['duration']:.2f} detik ({session['duration']/60:.2f} menit)")
    
    return valid_sessions

def check_mseed_table_exists(conn):
    """Memeriksa apakah tabel mseed_files sudah ada di database"""
    try:
        with conn.cursor() as cursor:
            cursor.execute(f"SHOW TABLES LIKE '{MSEED_TABLE}'")
            result = cursor.fetchone()
            return result is not None
    except pymysql.Error as e:
        print(f"Error saat memeriksa tabel: {e}")
        return False

def print_fancy_header():
    """Menampilkan header program yang menarik"""
    print("\n" + "="*80)
    print(f"{'PROGRAM KONVERSI DATA SEISMIC KE FORMAT MSEED':^80}")
    print(f"{'Dengan Penyimpanan Langsung ke Database':^80}")
    print("="*80)

def check_session_exists(conn, start_time, end_time, tolerance_seconds=5):
    """
    Mengecek apakah sesi dengan waktu mulai dan akhir tertentu sudah ada di database.
    
    Args:
        conn: Koneksi database
        start_time: Waktu mulai sesi
        end_time: Waktu akhir sesi
        tolerance_seconds: Toleransi waktu dalam detik untuk menganggap sesi sama
    
    Returns:
        dict: {'exists': bool, 'filename': str, 'id': int} atau None jika error
    """
    try:
        with conn.cursor() as cursor:
            # Query untuk mencari sesi yang sudah ada dengan toleransi waktu
            query = f"""
                SELECT id, filename, start_time, end_time 
                FROM {MSEED_TABLE} 
                WHERE ABS(TIMESTAMPDIFF(SECOND, start_time, %s)) <= %s 
                AND ABS(TIMESTAMPDIFF(SECOND, end_time, %s)) <= %s
                ORDER BY created_at DESC
                LIMIT 1
            """
            
            cursor.execute(query, (start_time, tolerance_seconds, end_time, tolerance_seconds))
            result = cursor.fetchone()
            
            if result:
                return {
                    'exists': True,
                    'id': result['id'],
                    'filename': result['filename'],
                    'start_time': result['start_time'],
                    'end_time': result['end_time']
                }
            else:
                return {'exists': False}
                
    except pymysql.Error as e:
        print(f"Error saat mengecek duplikasi sesi: {e}")
        return None

def filter_new_sessions(conn, valid_sessions):
    """
    Memfilter sesi valid untuk menghilangkan yang sudah ada di database.
    
    Args:
        conn: Koneksi database
        valid_sessions: List sesi valid yang akan difilter
    
    Returns:
        tuple: (new_sessions, existing_sessions)
    """
    new_sessions = []
    existing_sessions = []
    
    print("\n" + "-"*80)
    print(f"{'PENGECEKAN DUPLIKASI SESI':^80}")
    print("-"*80)
    
    for i, session_info in enumerate(valid_sessions):
        start_time = session_info['start_time']
        end_time = session_info['end_time']
        
        print(f"\nMengecek Sesi Valid #{i+1}...")
        print(f"  Waktu mulai : {format_time_for_display(start_time)}")
        print(f"  Waktu akhir : {format_time_for_display(end_time)}")
        
        # Cek apakah sesi sudah ada
        check_result = check_session_exists(conn, start_time, end_time)
        
        if check_result is None:
            print(f"  Error saat mengecek duplikasi. Sesi akan dilewati.")
            continue
        
        if check_result['exists']:
            print(f"  Status      : SUDAH ADA (File: {check_result['filename']})")
            existing_sessions.append({
                'session_info': session_info,
                'existing_file': check_result
            })
        else:
            print(f"  Status      : BARU - Akan disimpan")
            new_sessions.append(session_info)
    
    return new_sessions, existing_sessions

def display_duplication_summary(new_sessions, existing_sessions):
    """
    Menampilkan ringkasan hasil pengecekan duplikasi.
    """
    print("\n" + "="*80)
    print(f"{'RINGKASAN PENGECEKAN DUPLIKASI':^80}")
    print("="*80)
    
    print(f"\nSesi baru yang akan disimpan: {len(new_sessions)}")
    print(f"Sesi yang sudah ada di database: {len(existing_sessions)}")
    
    if existing_sessions:
        print("\n" + "-"*60)
        print("SESI YANG SUDAH ADA DI DATABASE:")
        print("-"*60)
        
        for i, item in enumerate(existing_sessions):
            session_info = item['session_info']
            existing_file = item['existing_file']
            
            print(f"\n{i+1}. Sesi yang sudah ada:")
            print(f"   Waktu mulai : {format_time_for_display(session_info['start_time'])}")
            print(f"   Waktu akhir : {format_time_for_display(session_info['end_time'])}")
            print(f"   File di DB  : {existing_file['filename']}")
    
    if new_sessions:
        print("\n" + "-"*60)
        print("SESI BARU YANG AKAN DISIMPAN:")
        print("-"*60)
        
        for i, session_info in enumerate(new_sessions):
            print(f"\n{i+1}. Sesi baru:")
            print(f"   Waktu mulai : {format_time_for_display(session_info['start_time'])}")
            print(f"   Waktu akhir : {format_time_for_display(session_info['end_time'])}")

def process_sessions_with_duplicate_check(conn, sessions):
    """
    Memproses setiap sesi dengan pengecekan duplikasi dan menyimpan file MSEED ke dalam database.
    Versi yang sudah diperbaiki dari fungsi process_sessions().
    """
    # Tampilkan informasi sesi dan dapatkan daftar sesi valid
    valid_sessions = display_sessions_info(sessions)
    
    if not valid_sessions:
        print("\nTidak ada sesi yang dapat diproses. Program selesai.")
        return 0
    
    # Filter sesi yang belum ada di database
    new_sessions, existing_sessions = filter_new_sessions(conn, valid_sessions)
    
    # Tampilkan ringkasan duplikasi
    display_duplication_summary(new_sessions, existing_sessions)
    
    if not new_sessions:
        print("\nSemua sesi sudah ada di database. Tidak ada yang perlu disimpan.")
        return 0
    
    # Konfirmasi dengan pengguna
    print("\n" + "-"*80)
    while True:
        choice = input(f"\nApakah Anda ingin melanjutkan penyimpanan {len(new_sessions)} sesi baru ke database? (y/n): ").lower()
        if choice in ['y', 'n']:
            break
        print("Input tidak valid. Masukkan 'y' untuk Ya atau 'n' untuk Tidak.")
    
    if choice == 'n':
        print("\nPenyimpanan MSEED ke database dibatalkan oleh pengguna.")
        return 0
    
    # Proses sesi baru dan simpan file MSEED ke database
    print("\n" + "-"*80)
    print(f"{'PROSES PENYIMPANAN MSEED BARU KE DATABASE':^80}")
    print("-"*80)
    
    saved_sessions = []
    
    for i, session_info in enumerate(new_sessions):
        session_number = len(existing_sessions) + i + 1  # Nomor sesi yang disesuaikan
        start_time = session_info['start_time']
        end_time = session_info['end_time']
        
        print(f"\nMemproses Sesi Baru #{i+1}...")
        print(f"  Waktu mulai : {format_time_for_display(start_time)}")
        print(f"  Waktu akhir : {format_time_for_display(end_time)}")
        
        # Buat binary MSEED
        mseed_binary = create_mseed_binary(session_info['data'])
        if not mseed_binary:
            print(f"  Gagal membuat data MSEED untuk sesi #{i+1}")
            continue
        
        # Simpan ke database
        success = insert_mseed_to_database(conn, session_number, start_time, end_time, mseed_binary)
        if success:
            print(f"  Berhasil menyimpan data MSEED ke database untuk sesi #{i+1}")
            saved_sessions.append({
                'number': session_number,
                'start_time': start_time,
                'end_time': end_time
            })
        else:
            print(f"  Gagal menyimpan data MSEED ke database untuk sesi #{i+1}")
    
    # Tampilkan ringkasan sesi yang berhasil disimpan
    print("\n" + "="*80)
    print(f"{'RINGKASAN HASIL PENYIMPANAN MSEED KE DATABASE':^80}")
    print("="*80)
    
    total_existing = len(existing_sessions)
    total_new_saved = len(saved_sessions)
    
    if total_existing > 0:
        print(f"\nSesi yang sudah ada sebelumnya: {total_existing}")
    
    if saved_sessions:
        print(f"\nTotal {total_new_saved} data MSEED baru berhasil disimpan ke tabel {MSEED_TABLE}")
        print("\nDaftar sesi baru yang berhasil disimpan:")
        for i, session in enumerate(saved_sessions):
            print(f"  {i+1}. SESI {session['number']} - {NETWORK}.{STATION}.{CHANNEL} "
                  f"({format_time_for_display(session['start_time'])} - {format_time_for_display(session['end_time'])}).mseed")
    else:
        print("\nTidak ada data MSEED baru yang berhasil disimpan ke database.")
    
    return total_new_saved

# Modifikasi fungsi main() untuk menggunakan fungsi yang sudah diperbaiki
def main():
    """
    Fungsi main yang sudah diperbaiki dengan pengecekan duplikasi.
    Ganti pemanggilan process_sessions() dengan process_sessions_with_duplicate_check()
    """
    print_fancy_header()
    
    # Koneksi ke database
    print("\nMenghubungkan ke database MySQL menggunakan PyMySQL...")
    conn = connect_to_mysql()
    if not conn:
        print("Gagal terhubung ke database. Program berhenti.")
        return
    
    print("Koneksi database berhasil!")
    
    # Periksa apakah tabel mseed_files ada
    if not check_mseed_table_exists(conn):
        print(f"\nTabel {MSEED_TABLE} tidak ditemukan di database.")
        print("Pastikan tabel sudah dibuat dengan skema yang sesuai:")
        print("""
    CREATE TABLE mseed_files (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        filename VARCHAR(255),
        start_time TIMESTAMP,
        end_time TIMESTAMP,
        content LONGBLOB,
        created_at TIMESTAMP,
        updated_at TIMESTAMP
    );
        """)
        conn.close()
        return
    
    # Baca metadata dari stationXML dengan path tetap
    print("\nMembaca metadata stasiun seismik...")
    read_station_metadata(STATION_XML_FILE)
    
    # Tampilkan progress
    print("\nMengambil data dari database...")
    data_records = fetch_all_geophone_data(conn)
    
    if not data_records:
        print("Tidak ada data yang ditemukan dalam database.")
        conn.close()
        return
    
    print(f"Berhasil mengambil {len(data_records)} records dari database.")
    
    # Parse data adc_counts dan reading_times
    print("\nMemproses dan mengonversi data...")
    parsed_data = parse_adc_counts(data_records)
    
    if not parsed_data:
        print("Tidak ada data yang berhasil diproses. Pastikan format data benar.")
        conn.close()
        return
        
    print(f"Berhasil memproses {len(parsed_data)} records.")
    
    # Deteksi sesi pengiriman data
    print("\nMendeteksi sesi pengiriman data berdasarkan selisih waktu...")
    sessions = detect_sessions(parsed_data)
    
    if not sessions:
        print("Tidak ada sesi yang terdeteksi. Program berhenti.")
        conn.close()
        return
    
    # Proses setiap sesi dengan pengecekan duplikasi
    process_sessions_with_duplicate_check(conn, sessions)
    
    conn.close()
    print("\n" + "="*80)
    print(f"{'PROGRAM SELESAI':^80}")
    print("="*80)

if __name__ == "__main__":
    main()