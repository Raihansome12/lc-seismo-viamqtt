#!/usr/bin/env python3
"""
PPSD Generator Service - Using environment variables from systemd
"""

import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
from obspy import read, UTCDateTime
from obspy.io.xseed import Parser
from obspy.signal import PPSD
from obspy import read_inventory
from obspy.imaging.cm import pqlx
import pymysql
import io
import os
import sys
import signal
import time
import logging
from datetime import datetime
import traceback
import argparse

class PPSDGenerator:
    def __init__(self):
        """
        Initialize PPSD Generator using environment variables
        """
        # Load configuration from environment variables
        self.db_config = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'user': os.getenv('DB_USER', 'kurniawan'),
            'password': os.getenv('DB_PASSWORD', 'b3349ewt'),
            'database': os.getenv('DB_NAME', 'seismic-monitoring'),
            'charset': 'utf8mb4'
        }
        
        # Service configuration
        self.ppsd_table = os.getenv('PPSD_TABLE', 'ppsd_files')
        self.mseed_table = os.getenv('MSEED_TABLE', 'mseed_files')
        self.xml_file_path = os.getenv('STATION_XML_FILE', '/opt/seismic-service/config/IA.STMKG.xml')
        self.check_interval = int(os.getenv('CHECK_INTERVAL', '300'))
        self.batch_size = int(os.getenv('BATCH_SIZE', '10'))
        self.max_retries = int(os.getenv('MAX_RETRIES', '3'))
        self.retry_delay = int(os.getenv('RETRY_DELAY', '60'))
        
        self.running = True
        
        # Setup logging
        self.setup_logging()
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self.signal_handler)
        signal.signal(signal.SIGINT, self.signal_handler)
        
        # Log configuration
        self.logger.info("PPSD Generator initialized with configuration:")
        self.logger.info(f"Database: {self.db_config['host']}/{self.db_config['database']}")
        self.logger.info(f"Station XML: {self.xml_file_path}")
        self.logger.info(f"Check interval: {self.check_interval}s")
        self.logger.info(f"Batch size: {self.batch_size}")
    
    def setup_logging(self):
        """Setup logging configuration"""
        log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        log_file = '/var/log/ppsd_generator.log'

        # Formatter
        formatter = logging.Formatter(log_format)

        # Handler untuk stdout (INFO ke atas)
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setLevel(logging.INFO)
        stream_handler.setFormatter(formatter)

        # Handler untuk file log (hanya ERROR ke atas)
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.ERROR)
        file_handler.setFormatter(formatter)

        # Dapatkan logger
        self.logger = logging.getLogger('PPSDGenerator')
        self.logger.setLevel(logging.INFO)  # Tetapkan level dasar logger
        self.logger.addHandler(stream_handler)
        self.logger.addHandler(file_handler)

    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        self.logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.running = False
    
    def connect_db(self):
        """Create database connection with error handling"""
        try:
            return pymysql.connect(
                host=self.db_config['host'],
                user=self.db_config['user'],
                password=self.db_config['password'],
                database=self.db_config['database'],
                charset=self.db_config['charset']
            )
        except Exception as e:
            self.logger.error(f"Database connection failed: {e}")
            raise
    
    def get_mseed_files(self, limit=None):
        """Get mseed files from database that don't have PPSD yet"""
        connection = self.connect_db()
        try:
            with connection.cursor() as cursor:
                # Only get files that don't have PPSD yet
                sql = f"""
                SELECT m.id, m.filename, m.start_time, m.end_time, m.content 
                FROM {self.mseed_table} m 
                LEFT JOIN {self.ppsd_table} p ON m.id = p.mseed_file_id 
                WHERE p.id IS NULL
                ORDER BY m.created_at ASC
                """
                if limit:
                    sql += f" LIMIT {limit}"
                    
                cursor.execute(sql)
                return cursor.fetchall()
        finally:
            connection.close()
    
    def calculate_duration_seconds(self, start_time, end_time):
        """Calculate duration in seconds between start and end time"""
        if isinstance(start_time, str):
            start_time = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
        if isinstance(end_time, str):
            end_time = datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
        
        duration = (end_time - start_time).total_seconds()
        return int(duration)
    
    def determine_ppsd_length(self, duration_seconds):
        """
        Determine PPSD length based on file duration
        
        Args:
            duration_seconds (int): Duration in seconds
            
        Returns:
            int: PPSD length value
        """
        if 60 <= duration_seconds < 120:
            return 60
        elif 120 <= duration_seconds < 240:
            return 120
        elif 240 <= duration_seconds < 480:
            return 240
        elif 480 <= duration_seconds < 960:
            return 480
        elif 960 <= duration_seconds < 1920:
            return 960
        elif 1920 <= duration_seconds < 3600:
            return 1920
        elif 3600 <= duration_seconds < 7200:
            return 3600
        elif 7200 <= duration_seconds < 14400:
            return 7200
        elif 14400 <= duration_seconds < 28800:
            return 14400
        else:
            return 28800  # 8 hours in seconds
    
    def generate_ppsd_filename(self, original_filename):
        """
        Generate PPSD filename based on original mseed filename
        
        Args:
            original_filename (str): Original mseed filename
            
        Returns:
            str: Generated PPSD filename
        """
        # Remove file extension
        base_name = os.path.splitext(original_filename)[0]
        return f"PPSD_{base_name}.png"
    
    def save_ppsd_to_db(self, mseed_file_id, original_filename, start_time, end_time, ppsd_image_data):
        """Save PPSD image to database with foreign key reference"""
        connection = self.connect_db()
        try:
            with connection.cursor() as cursor:
                # Generate PPSD filename
                ppsd_filename = self.generate_ppsd_filename(original_filename)
                
                # Check if PPSD already exists for this mseed_file_id
                cursor.execute(f"SELECT id FROM {self.ppsd_table} WHERE mseed_file_id = %s", (mseed_file_id,))
                existing = cursor.fetchone()
                
                if existing:
                    # Update existing PPSD (in case of reprocessing)
                    sql = f"""UPDATE {self.ppsd_table} 
                             SET filename = %s, start_time = %s, end_time = %s, content = %s, updated_at = NOW()
                             WHERE mseed_file_id = %s"""
                    cursor.execute(sql, (ppsd_filename, start_time, end_time, ppsd_image_data, mseed_file_id))
                    self.logger.info(f"PPSD updated in database for {ppsd_filename} (mseed_file_id: {mseed_file_id})")
                else:
                    # Insert new PPSD
                    sql = f"""INSERT INTO {self.ppsd_table} (mseed_file_id, filename, start_time, end_time, content, created_at, updated_at) 
                             VALUES (%s, %s, %s, %s, %s, NOW(), NOW())"""
                    cursor.execute(sql, (mseed_file_id, ppsd_filename, start_time, end_time, ppsd_image_data))
                    self.logger.info(f"PPSD saved to database for {ppsd_filename} (mseed_file_id: {mseed_file_id})")
                
                connection.commit()
                
        except Exception as e:
            self.logger.error(f"Error saving to database: {e}")
            connection.rollback()
            raise
        finally:
            connection.close()
    
    def create_ppsd(self, filename, start_time, end_time, mseed_content):
        """
        Create PPSD for a specific mseed file from database content
        
        Args:
            filename (str): Name of the mseed file
            start_time: Start time of the recording
            end_time: End time of the recording
            mseed_content (bytes): Binary content of mseed file
            
        Returns:
            bytes: PPSD image data or None if failed
        """
        try:
            # Read the mseed from binary data
            self.logger.debug(f"Reading mseed from database: {filename}")
            
            # Create a BytesIO object from the binary content
            mseed_buffer = io.BytesIO(mseed_content)
            st = read(mseed_buffer)
            
            # Read station metadata
            if not os.path.exists(self.xml_file_path):
                self.logger.error(f"Station XML file not found: {self.xml_file_path}")
                return None
                
            inv = read_inventory(self.xml_file_path)
            st.attach_response(inv)
            
            # Select the trace
            tr = st.select(id="IA.STMKG.00.SHZ")[0]
            
            # Calculate duration and determine PPSD length
            duration = self.calculate_duration_seconds(start_time, end_time)
            ppsd_length = self.determine_ppsd_length(duration)
            
            self.logger.debug(f"Duration: {duration}s, PPSD Length: {ppsd_length}s")
            
            # Create PPSD
            ppsd = PPSD(tr.stats, metadata=inv, ppsd_length=ppsd_length)
            ppsd.add(tr)
            
            # Create the plot
            fig = plt.figure(figsize=(12, 8))
            ppsd.plot(cmap=pqlx, show=False)
            
            # Save plot to bytes
            img_buffer = io.BytesIO()
            plt.savefig(img_buffer, format='png', dpi=300, bbox_inches='tight')
            img_buffer.seek(0)
            image_data = img_buffer.getvalue()
            
            plt.close(fig)  # Close the figure to free memory
            img_buffer.close()
            mseed_buffer.close()
            
            self.logger.debug(f"PPSD created successfully for {filename}")
            return image_data
            
        except Exception as e:
            self.logger.error(f"Error creating PPSD for {filename}: {e}")
            self.logger.debug(f"Traceback: {traceback.format_exc()}")
            return None
    
    def process_batch(self):
        """Process a batch of mseed files"""
        try:
            # Get files that need processing
            mseed_files = self.get_mseed_files(limit=self.batch_size)
            
            if not mseed_files:
                self.logger.debug("No new files to process")
                return 0
            
            self.logger.info(f"Processing batch of {len(mseed_files)} files")
            
            success_count = 0
            
            for file_id, filename, start_time, end_time, mseed_content in mseed_files:
                if not self.running:
                    self.logger.info("Shutdown requested, stopping batch processing")
                    break
                    
                self.logger.info(f"Processing: {filename} (ID: {file_id})")
                
                # Create PPSD with retry logic
                ppsd_image_data = None
                for attempt in range(self.max_retries):
                    try:
                        ppsd_image_data = self.create_ppsd(filename, start_time, end_time, mseed_content)
                        if ppsd_image_data:
                            break
                    except Exception as e:
                        self.logger.warning(f"Attempt {attempt + 1} failed for {filename}: {e}")
                        if attempt < self.max_retries - 1:
                            time.sleep(self.retry_delay)
                
                if ppsd_image_data:
                    # Save to database with retry logic
                    for attempt in range(self.max_retries):
                        try:
                            self.save_ppsd_to_db(file_id, filename, start_time, end_time, ppsd_image_data)
                            success_count += 1
                            break
                        except Exception as e:
                            self.logger.warning(f"Database save attempt {attempt + 1} failed for {filename}: {e}")
                            if attempt < self.max_retries - 1:
                                time.sleep(self.retry_delay)
                            else:
                                self.logger.error(f"Failed to save PPSD for {filename} after {self.max_retries} attempts")
                else:
                    self.logger.error(f"Failed to create PPSD for {filename} after {self.max_retries} attempts")
            
            self.logger.info(f"Batch completed. Processed {success_count}/{len(mseed_files)} files successfully")
            return success_count
            
        except Exception as e:
            self.logger.error(f"Error in batch processing: {e}")
            return 0
    
    def run_service(self):
        """Main service loop"""
        self.logger.info("PPSD Generator Service started")
        
        while self.running:
            try:
                processed = self.process_batch()
                
                if processed > 0:
                    self.logger.info(f"Processed {processed} files, checking for more...")
                    # If we processed files, check immediately for more
                    continue
                else:
                    # No files to process, wait for the configured interval
                    self.logger.debug(f"Waiting {self.check_interval} seconds before next check...")
                    
                    # Sleep with periodic checks for shutdown signal
                    for _ in range(self.check_interval):
                        if not self.running:
                            break
                        time.sleep(1)
                        
            except KeyboardInterrupt:
                self.logger.info("Received keyboard interrupt")
                break
            except Exception as e:
                self.logger.error(f"Unexpected error in service loop: {e}")
                self.logger.debug(f"Traceback: {traceback.format_exc()}")
                # Wait a bit before retrying to avoid rapid error loops
                time.sleep(30)
        
        self.logger.info("PPSD Generator Service stopped")
    
    def process_once(self):
        """Process all files once (for manual execution)"""
        self.logger.info("Starting one-time PPSD generation process...")
        
        total_processed = 0
        while True:
            processed = self.process_batch()
            total_processed += processed
            
            if processed == 0:
                break
        
        self.logger.info(f"One-time processing completed. Total files processed: {total_processed}")

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='PPSD Generator')
    parser.add_argument('--service', action='store_true', 
                       help='Run as a service (continuous loop)')
    parser.add_argument('--once', action='store_true', 
                       help='Process all files once and exit')
    
    args = parser.parse_args()
    
    try:
        generator = PPSDGenerator()
        
        if args.service:
            generator.run_service()
        elif args.once:
            generator.process_once()
        else:
            # Default behavior - process once
            generator.process_once()
            
    except Exception as e:
        logging.error(f"Failed to start PPSD generator: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()