#!/usr/bin/env python3
"""
PPSD Generator Service - Modified for systemd background execution
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
from pathlib import Path
import configparser

class PPSDGenerator:
    def __init__(self, config_file=None):
        """
        Initialize PPSD Generator
        
        Args:
            config_file (str): Path to configuration file
        """
        self.config_file = config_file or "/etc/ppsd-generator/config.ini"
        self.config = self.load_config()
        self.db_config = self.config['database']
        self.xml_file_path = self.config['paths']['station_xml']
        self.running = True
        
        # Setup logging
        self.setup_logging()
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self.signal_handler)
        signal.signal(signal.SIGINT, self.signal_handler)
        
    def load_config(self):
        """Load configuration from file with fallback to defaults"""
        config = configparser.ConfigParser()
        
        # Default configuration
        defaults = {
            'database': {
                'host': 'localhost',
                'user': 'kurniawan',
                'password': 'b3349ewt',
                'database': 'seismic_monitoring',
                'charset': 'utf8mb4'
            },
            'paths': {
                'station_xml': '/opt/seismic-service/config/IA.STMKG.xml',
                'log_file': '/var/log/seismic-servic/ppsd-generator.log'
            },
            'service': {
                'check_interval': '300',  # 5 minutes
                'batch_size': '10'
            }
        }
        
        try:
            if os.path.exists(self.config_file):
                config.read(self.config_file)
                logging.info(f"Configuration loaded from {self.config_file}")
            else:
                logging.warning(f"Config file {self.config_file} not found, using defaults")
                
            # Merge with defaults
            result = {}
            for section, values in defaults.items():
                result[section] = {}
                for key, default_value in values.items():
                    try:
                        if section == 'service' and key in ['check_interval', 'batch_size']:
                            result[section][key] = int(config.get(section, key, fallback=default_value))
                        else:
                            result[section][key] = config.get(section, key, fallback=default_value)
                    except (configparser.NoSectionError, configparser.NoOptionError):
                        result[section][key] = default_value
                        
            return result
            
        except Exception as e:
            logging.error(f"Error loading configuration: {e}")
            return defaults
    
    def setup_logging(self):
        """Setup logging configuration"""
        try:
            log_file = self.config['paths']['log_file']
            log_dir = os.path.dirname(log_file)
            
            # Create log directory if it doesn't exist
            os.makedirs(log_dir, exist_ok=True)
            
            # Configure logging
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                handlers=[
                    logging.FileHandler(log_file),
                    logging.StreamHandler(sys.stdout)  # Also log to stdout for systemd journal
                ]
            )
            
            self.logger = logging.getLogger('PPSDGenerator')
            
        except Exception as e:
            # Fallback to basic logging if file logging fails
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                handlers=[logging.StreamHandler(sys.stdout)]
            )
            self.logger = logging.getLogger('PPSDGenerator')
            self.logger.warning(f"Could not setup file logging: {e}")
    
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
                sql = """
                SELECT m.id, m.filename, m.start_time, m.end_time, m.content 
                FROM mseed_files m 
                LEFT JOIN ppsd_files p ON m.id = p.mseed_file_id 
                WHERE p.id IS NULL
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
        else:
            # For very long files, use 1800 (30 minutes)
            return 1800
    
    def generate_ppsd_filename(self, original_filename):
        """
        Generate PPSD filename based on original mseed filename
        
        Args:
            original_filename (str): Original mseed filename
            
        Returns:
            str: Generated PPSD filename
        """
        # Remove file extension and add _ppsd.png
        base_name = os.path.splitext(original_filename)[0]
        return f"PPSD_{base_name}.png"
    
    def save_ppsd_to_db(self, mseed_file_id, original_filename, start_time, end_time, ppsd_image_data):
        """Save PPSD image to database with foreign key reference"""
        connection = self.connect_db()
        try:
            with connection.cursor() as cursor:
                # Generate PPSD filename
                ppsd_filename = self.generate_ppsd_filename(original_filename)
                
                # Insert new PPSD
                sql = """INSERT INTO ppsd_files (mseed_file_id, filename, start_time, end_time, content, created_at, updated_at) 
                         VALUES (%s, %s, %s, %s, %s, NOW(), NOW())"""
                cursor.execute(sql, (mseed_file_id, ppsd_filename, start_time, end_time, ppsd_image_data))
                
                connection.commit()
                self.logger.info(f"PPSD saved to database for {ppsd_filename} (mseed_file_id: {mseed_file_id})")
                
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
            batch_size = self.config['service']['batch_size']
            
            # Get files that need processing
            mseed_files = self.get_mseed_files(limit=batch_size)
            
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
                
                # Create PPSD
                ppsd_image_data = self.create_ppsd(filename, start_time, end_time, mseed_content)
                
                if ppsd_image_data:
                    # Save to database
                    self.save_ppsd_to_db(file_id, filename, start_time, end_time, ppsd_image_data)
                    success_count += 1
                else:
                    self.logger.error(f"Failed to create PPSD for {filename}")
            
            self.logger.info(f"Batch completed. Processed {success_count}/{len(mseed_files)} files successfully")
            return success_count
            
        except Exception as e:
            self.logger.error(f"Error in batch processing: {e}")
            return 0
    
    def run_service(self):
        """Main service loop"""
        self.logger.info("PPSD Generator Service started")
        
        check_interval = self.config['service']['check_interval']
        
        while self.running:
            try:
                processed = self.process_batch()
                
                if processed > 0:
                    self.logger.info(f"Processed {processed} files, checking for more...")
                    # If we processed files, check immediately for more
                    continue
                else:
                    # No files to process, wait for the configured interval
                    self.logger.debug(f"Waiting {check_interval} seconds before next check...")
                    
                    # Sleep with periodic checks for shutdown signal
                    for _ in range(check_interval):
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

def main():
    """Main entry point"""
    try:
        # Get config file path from command line or use default
        config_file = sys.argv[1] if len(sys.argv) > 1 else None
        
        # Create and run the service
        generator = PPSDGenerator(config_file)
        generator.run_service()
        
    except Exception as e:
        logging.error(f"Failed to start service: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()