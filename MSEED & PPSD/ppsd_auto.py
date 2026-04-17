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
from datetime import datetime
import traceback

class PPSDGenerator:
    def __init__(self, db_config):
        """
        Initialize PPSD Generator
        
        Args:
            db_config (dict): Database configuration with keys: host, user, password, database
        """
        self.db_config = db_config
        self.xml_file_path = r"C:\Users\raiha\OneDrive\Desktop\Program Skripsi\MSEED & PPSD\stationXML\IA.STMKG.xml"
        
    def connect_db(self):
        """Create database connection"""
        return pymysql.connect(
            host=self.db_config['host'],
            user=self.db_config['user'],
            password=self.db_config['password'],
            database=self.db_config['database'],
            charset='utf8mb4'
        )
    
    def get_mseed_files(self):
        """Get all mseed files from database"""
        connection = self.connect_db()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id, filename, start_time, end_time, content FROM mseed_files")
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
        elif 7200 <= duration_seconds < 10800:
            return 7200
        elif 10800 <= duration_seconds < 14400:
            return 10800
        elif 14400 <= duration_seconds < 18000:
            return 14400
        elif 18000 <= duration_seconds < 21600:
            return 18000
        else:
            return 21600  # Default to 21600 seconds (6 hours)
    
    def check_ppsd_exists(self, mseed_file_id):
        """Check if PPSD already exists for this mseed file ID (one-to-one relationship)"""
        connection = self.connect_db()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id FROM ppsd_files WHERE mseed_file_id = %s LIMIT 1", (mseed_file_id,))
                result = cursor.fetchone()
                return result is not None
        finally:
            connection.close()
    
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
        """Save PPSD image to database with foreign key reference (one-to-one relationship)"""
        connection = self.connect_db()
        try:
            with connection.cursor() as cursor:
                # Generate PPSD filename
                ppsd_filename = self.generate_ppsd_filename(original_filename)
                
                # Check if PPSD already exists for this mseed_file_id
                cursor.execute("SELECT id FROM ppsd_files WHERE mseed_file_id = %s", (mseed_file_id,))
                existing = cursor.fetchone()
                
                if existing:
                    # Update existing PPSD (in case of reprocessing)
                    sql = """UPDATE ppsd_files 
                             SET filename = %s, start_time = %s, end_time = %s, content = %s, updated_at = NOW()
                             WHERE mseed_file_id = %s"""
                    cursor.execute(sql, (ppsd_filename, start_time, end_time, ppsd_image_data, mseed_file_id))
                    print(f"PPSD updated in database for {ppsd_filename} (mseed_file_id: {mseed_file_id})")
                else:
                    # Insert new PPSD
                    sql = """INSERT INTO ppsd_files (mseed_file_id, filename, start_time, end_time, content, created_at, updated_at) 
                             VALUES (%s, %s, %s, %s, %s, NOW(), NOW())"""
                    cursor.execute(sql, (mseed_file_id, ppsd_filename, start_time, end_time, ppsd_image_data))
                    print(f"PPSD saved to database for {ppsd_filename} (mseed_file_id: {mseed_file_id})")
                
                connection.commit()
        except Exception as e:
            print(f"Error saving to database: {e}")
            connection.rollback()
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
            print(f"Reading mseed from database: {filename}")
            
            # Create a BytesIO object from the binary content
            mseed_buffer = io.BytesIO(mseed_content)
            st = read(mseed_buffer)
            
            # Read station metadata
            if not os.path.exists(self.xml_file_path):
                print(f"Station XML file not found: {self.xml_file_path}")
                return None
                
            inv = read_inventory(self.xml_file_path)
            st.attach_response(inv)
            
            # Select the trace
            tr = st.select(id="IA.STMKG.00.SHZ")[0]
            
            # Calculate duration and determine PPSD length
            duration = self.calculate_duration_seconds(start_time, end_time)
            ppsd_length = self.determine_ppsd_length(duration)
            
            print(f"Duration: {duration}s, PPSD Length: {ppsd_length}s")
            
            # Create PPSD
            ppsd = PPSD(tr.stats, metadata=inv, ppsd_length=ppsd_length)
            ppsd.add(tr)
            
            # Create the plot
            fig = plt.figure(figsize=(12, 8))
            ppsd.plot(cmap=pqlx, show=False)
            # plt.title(f'PPSD - {filename}')
            
            # Save plot to bytes
            img_buffer = io.BytesIO()
            plt.savefig(img_buffer, format='png', dpi=300, bbox_inches='tight')
            img_buffer.seek(0)
            image_data = img_buffer.getvalue()
            
            plt.close(fig)  # Close the figure to free memory
            img_buffer.close()
            mseed_buffer.close()
            
            print(f"PPSD created successfully for {filename}")
            return image_data
            
        except Exception as e:
            print(f"Error creating PPSD for {filename}: {e}")
            print(f"Traceback: {traceback.format_exc()}")
            return None
    
    def process_all_files(self, skip_existing=True):
        """
        Process all mseed files and create PPSD images
        
        Args:
            skip_existing (bool): Skip files that already have PPSD in database
        """
        print("Starting PPSD generation process...")
        
        # Get all mseed files from database
        mseed_files = self.get_mseed_files()
        print(f"Found {len(mseed_files)} mseed files in database")
        
        success_count = 0
        skip_count = 0
        error_count = 0
        
        for file_id, filename, start_time, end_time, mseed_content in mseed_files:
            print(f"\nProcessing: {filename} (ID: {file_id})")
            
            # Check if PPSD already exists using mseed_file_id
            if skip_existing and self.check_ppsd_exists(file_id):
                print(f"PPSD already exists for {filename} (ID: {file_id}), skipping...")
                skip_count += 1
                continue
            
            # Create PPSD
            ppsd_image_data = self.create_ppsd(filename, start_time, end_time, mseed_content)
            
            if ppsd_image_data:
                # Save to database with mseed_file_id as foreign key
                self.save_ppsd_to_db(file_id, filename, start_time, end_time, ppsd_image_data)
                success_count += 1
            else:
                error_count += 1
        
        # Print summary
        print(f"\nProcessing Summary:")
        print(f"Successful: {success_count}")
        print(f"Skipped: {skip_count}")
        print(f"Errors: {error_count}")
        print(f"Total files: {len(mseed_files)}")

def main():
    # Database configuration
    db_config = {
        'host': 'localhost',
        'user': 'kurniawan', 
        'password': 'b3349ewt',
        'database': 'seismic-monitoring',
        'charset': 'utf8mb4',
        'cursorclass': pymysql.cursors.DictCursor
    }
    
    # Create PPSD generator instance
    generator = PPSDGenerator(db_config)
    
    # Process all files
    generator.process_all_files(skip_existing=True)

if __name__ == "__main__":
    main()