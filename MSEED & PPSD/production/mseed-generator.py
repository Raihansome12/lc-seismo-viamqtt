import pymysql
import numpy as np
import os
import io
import time
import signal
import sys
import logging
from logging.handlers import RotatingFileHandler
from obspy.core import UTCDateTime, Stream, Trace
from obspy import read_inventory
from datetime import datetime, timedelta

# Setup logging untuk service
def setup_logging():
    """Setup logging configuration untuk service mode"""
    log_dir = '/var/log/seismic-service'  # Atau sesuaikan dengan kebutuhan
    os.makedirs(log_dir, exist_ok=True)
    
    log_file = os.path.join(log_dir, 'seismic-processor.log')
    
    # Setup rotating file handler
    handler = RotatingFileHandler(
        log_file, 
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    handler.setLevel(logging.ERROR)
    
    # Setup formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler.setFormatter(formatter)
    
    # Setup logger
    logger = logging.getLogger('seismic_processor')
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    
    # Also log to console if not running as service
    if os.isatty(sys.stdout.fileno()):
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    return logger

# Global logger
logger = setup_logging()

# Konfigurasi database MySQL
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'user': os.getenv('DB_USER', 'kurniawan'),
    'password': os.getenv('DB_PASSWORD', 'b3349ewt'),
    'database': os.getenv('DB_NAME', 'seismic-monitoring'),
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}

# Konfigurasi tabel dan stationXML path
READINGS_TABLE = os.getenv('READINGS_TABLE', 'seismic_readings')
MSEED_TABLE = os.getenv('MSEED_TABLE', 'mseed_files')
STATION_XML_FILE = os.getenv('STATION_XML_FILE', "/opt/seismic-service/config/IA.STMKG.xml")

# Konfigurasi service
SERVICE_CONFIG = {
    'check_interval': int(os.getenv('CHECK_INTERVAL', 300)),  # 5 menit default
    'batch_size': int(os.getenv('BATCH_SIZE', 1000)),
    'max_retries': int(os.getenv('MAX_RETRIES', 3)),
    'retry_delay': int(os.getenv('RETRY_DELAY', 60))
}

# Variabel global untuk metadata seismik
STATION = "STMKG"
NETWORK = "IA"
CHANNEL = "SHZ"
LOCATION = "00"
SAMPLING_RATE = 50
MIN_SESSION_DURATION = 60

# Variable untuk graceful shutdown
running = True

def signal_handler(signum, frame):
    """Handler untuk graceful shutdown"""
    global running
    logger.info(f"Received signal {signum}. Initiating graceful shutdown...")
    running = False

def setup_signal_handlers():
    """Setup signal handlers untuk graceful shutdown"""
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

def read_station_metadata(xml_file):
    """Membaca metadata seismik dari file stationXML"""
    global STATION, NETWORK, CHANNEL, LOCATION, SAMPLING_RATE
    
    try:
        if not os.path.exists(xml_file):
            logger.warning(f"File stationXML '{xml_file}' tidak ditemukan. Menggunakan nilai default.")
            return False
            
        logger.info(f"Membaca metadata dari stationXML: {xml_file}")
        inventory = read_inventory(xml_file)
        
        if inventory and inventory[0]:
            NETWORK = inventory[0].code
            if inventory[0][0]:
                STATION = inventory[0][0].code
                if inventory[0][0][0]:
                    channel_obj = inventory[0][0][0]
                    CHANNEL = channel_obj.code
                    LOCATION = channel_obj.location_code
                    SAMPLING_RATE = channel_obj.sample_rate
                    
        logger.info(f"Metadata loaded - Network: {NETWORK}, Station: {STATION}, Channel: {CHANNEL}, Location: {LOCATION}, Sampling Rate: {SAMPLING_RATE} Hz")
        return True
        
    except Exception as e:
        logger.error(f"Error saat membaca stationXML: {e}")
        logger.info("Menggunakan nilai metadata default.")
        return False

def connect_to_mysql_with_retry():
    """Membuat koneksi ke database MySQL dengan retry mechanism"""
    for attempt in range(SERVICE_CONFIG['max_retries']):
        try:
            conn = pymysql.connect(**DB_CONFIG)
            logger.info("Database connection established successfully")
            return conn
        except pymysql.Error as e:
            logger.error(f"Database connection attempt {attempt + 1} failed: {e}")
            if attempt < SERVICE_CONFIG['max_retries'] - 1:
                logger.info(f"Retrying in {SERVICE_CONFIG['retry_delay']} seconds...")
                time.sleep(SERVICE_CONFIG['retry_delay'])
            else:
                logger.error("All database connection attempts failed")
                return None

def fetch_unprocessed_data(conn, last_processed_time=None):
    """Mengambil data yang belum diproses dari database"""
    try:
        with conn.cursor() as cursor:
            if last_processed_time:
                query = f"""
                    SELECT adc_counts, reading_times 
                    FROM {READINGS_TABLE} 
                    WHERE reading_times > %s 
                    ORDER BY reading_times ASC 
                    LIMIT %s
                """
                cursor.execute(query, (last_processed_time, SERVICE_CONFIG['batch_size']))
            else:
                query = f"""
                    SELECT adc_counts, reading_times 
                    FROM {READINGS_TABLE} 
                    ORDER BY reading_times ASC 
                    LIMIT %s
                """
                cursor.execute(query, (SERVICE_CONFIG['batch_size'],))
            
            records = cursor.fetchall()
            return records
    except pymysql.Error as e:
        logger.error(f"Error fetching data: {e}")
        return []

def parse_adc_counts(records):
    """Parse data adc_counts dan reading_times dari record database"""
    parsed_data = []

    for record in records:
        try:
            adc_counts_str = record['adc_counts']
            adc_counts_str = adc_counts_str.strip('"\'[]')
            adc_counts = [float(x.strip()) for x in adc_counts_str.split(',')]
            reading_time = record['reading_times']
            
            parsed_data.append({
                'time': reading_time,
                'data': adc_counts
            })
            
        except Exception as e:
            logger.error(f"Error parsing record: {e}")
            continue
    
    return parsed_data

def detect_sessions(parsed_data):
    """Mendeteksi sesi pengiriman data berdasarkan selisih waktu"""
    if not parsed_data:
        return []
        
    sessions = []
    current_session = [parsed_data[0]]
    
    EXPECTED_DIFF = timedelta(seconds=0.5)
    MAX_DIFF = timedelta(seconds=1.0)
    
    for i in range(1, len(parsed_data)):
        current_time = parsed_data[i]['time']
        prev_time = parsed_data[i-1]['time']
        time_diff = current_time - prev_time
        
        if time_diff > MAX_DIFF:
            if current_session:
                sessions.append(current_session)
            current_session = [parsed_data[i]]
        else:
            current_session.append(parsed_data[i])
    
    if current_session:
        sessions.append(current_session)
    
    return sessions

def create_mseed_binary(session):
    """Membuat binary MSEED dari data sesi tertentu"""
    if not session:
        logger.error("Tidak ada data dalam sesi yang diberikan.")
        return None
    
    try:
        st = Stream()
        all_data = []
        start_time = UTCDateTime(session[0]['time'])
        
        for item in session:
            all_data.extend(item['data'])
        
        trace = Trace(data=np.array(all_data))
        trace.stats.network = NETWORK
        trace.stats.station = STATION
        trace.stats.location = LOCATION
        trace.stats.channel = CHANNEL
        trace.stats.starttime = start_time
        trace.stats.sampling_rate = SAMPLING_RATE
        
        st.append(trace)
        
        buffer = io.BytesIO()
        st.write(buffer, format="MSEED")
        buffer.seek(0)
        
        return buffer.read()
    except Exception as e:
        logger.error(f"Error creating MSEED binary: {e}")
        return None

def check_session_exists(conn, start_time, end_time, tolerance_seconds=5):
    """Mengecek apakah sesi sudah ada di database"""
    try:
        with conn.cursor() as cursor:
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
        logger.error(f"Error checking session existence: {e}")
        return None

def insert_mseed_to_database(conn, session_number, start_time, end_time, mseed_binary):
    """Menyimpan file MSEED ke dalam database"""
    try:
        with conn.cursor() as cursor:
            formatted_start = start_time.strftime('%Y%m%d.%H%M%S')
            formatted_end = end_time.strftime('%H%M%S')
            filename = f"{NETWORK}.{STATION}.{CHANNEL}_{formatted_start}-{formatted_end}.mseed"
            
            query = f"""
                INSERT INTO {MSEED_TABLE} (filename, start_time, end_time, content, created_at, updated_at)
                VALUES (%s, %s, %s, %s, NOW(), NOW())
            """
            
            cursor.execute(query, (filename, start_time, end_time, mseed_binary))
            conn.commit()
            
            logger.info(f"MSEED saved successfully: {filename}")
            return True
    except pymysql.Error as e:
        logger.error(f"Error saving MSEED to database: {e}")
        return False

def process_sessions_service(conn, sessions):
    """Memproses sesi untuk service mode (tanpa interaksi user)"""
    if not sessions:
        return 0
    
    valid_sessions = []
    processed_count = 0
    
    # Filter sesi yang valid
    for session in sessions:
        start_time = session[0]['time']
        end_time = session[-1]['time']
        duration = (end_time - start_time).total_seconds()
        
        if duration >= MIN_SESSION_DURATION:
            valid_sessions.append({
                'start_time': start_time,
                'end_time': end_time,
                'duration': duration,
                'data': session
            })
    
    logger.info(f"Found {len(valid_sessions)} valid sessions to process")
    
    # Proses setiap sesi valid
    for i, session_info in enumerate(valid_sessions):
        start_time = session_info['start_time']
        end_time = session_info['end_time']
        
        # Cek apakah sesi sudah ada
        check_result = check_session_exists(conn, start_time, end_time)
        
        if check_result is None:
            logger.error(f"Error checking session existence for session {i+1}")
            continue
        
        if check_result['exists']:
            logger.info(f"Session {i+1} already exists: {check_result['filename']}")
            continue
        
        # Buat dan simpan MSEED
        mseed_binary = create_mseed_binary(session_info['data'])
        if not mseed_binary:
            logger.error(f"Failed to create MSEED binary for session {i+1}")
            continue
        
        success = insert_mseed_to_database(conn, i+1, start_time, end_time, mseed_binary)
        if success:
            processed_count += 1
            logger.info(f"Successfully processed session {i+1} ({start_time} - {end_time})")
        else:
            logger.error(f"Failed to save session {i+1} to database")
    
    return processed_count

def service_main_loop():
    """Main loop untuk service mode"""
    logger.info("Starting seismic data processor service")
    
    # Setup signal handlers
    setup_signal_handlers()
    
    # Load metadata
    read_station_metadata(STATION_XML_FILE)
    
    last_processed_time = None
    
    while running:
        try:
            # Connect to database
            conn = connect_to_mysql_with_retry()
            if not conn:
                logger.error("Failed to connect to database. Waiting before retry...")
                time.sleep(SERVICE_CONFIG['retry_delay'])
                continue
            
            # Fetch and process data
            logger.info("Fetching new seismic data...")
            data_records = fetch_unprocessed_data(conn, last_processed_time)
            
            if data_records:
                logger.info(f"Processing {len(data_records)} new records")
                
                # Parse data
                parsed_data = parse_adc_counts(data_records)
                
                if parsed_data:
                    # Update last processed time
                    last_processed_time = parsed_data[-1]['time']
                    
                    # Detect sessions
                    sessions = detect_sessions(parsed_data)
                    
                    if sessions:
                        processed_count = process_sessions_service(conn, sessions)
                        logger.info(f"Processed {processed_count} new sessions successfully")
                    else:
                        logger.info("No sessions detected in current batch")
                else:
                    logger.warning("No valid data parsed from records")
            else:
                logger.info("No new data to process")
            
            conn.close()
            
            # Wait before next check
            if running:
                logger.info(f"Waiting {SERVICE_CONFIG['check_interval']} seconds before next check...")
                time.sleep(SERVICE_CONFIG['check_interval'])
                
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
            break
        except Exception as e:
            logger.error(f"Unexpected error in main loop: {e}")
            time.sleep(SERVICE_CONFIG['retry_delay'])
    
    logger.info("Seismic data processor service stopped")

def interactive_main():
    """Fungsi main untuk mode interaktif (seperti sebelumnya)"""
    # Implementasi fungsi main() yang original di sini
    # untuk backward compatibility ketika dijalankan manual
    pass

if __name__ == "__main__":
    # Deteksi apakah dijalankan sebagai service atau interaktif
    if len(sys.argv) > 1 and sys.argv[1] == '--service':
        service_main_loop()
    else:
        # Mode interaktif untuk testing
        print("Running in interactive mode...")
        print("To run as service, use: python script.py --service")
        interactive_main()