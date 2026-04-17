import pymysql
import io
from PIL import Image
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from datetime import datetime
import os

class PPSDViewer:
    def __init__(self, db_config):
        """
        Initialize PPSD Viewer
        
        Args:
            db_config (dict): Database configuration with keys: host, user, password, database
        """
        self.db_config = db_config
        
    def connect_db(self):
        """Create database connection"""
        return pymysql.connect(
            host=self.db_config['host'],
            user=self.db_config['user'],
            password=self.db_config['password'],
            database=self.db_config['database'],
            charset='utf8mb4'
        )
    
    def list_ppsd_files(self):
        """List all PPSD files in database"""
        connection = self.connect_db()
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT id, filename, start_time, end_time, created_at 
                    FROM ppsd_files 
                    ORDER BY created_at DESC
                """)
                files = cursor.fetchall()
                
                if not files:
                    print("No PPSD files found in database.")
                    return []
                
                print("📋 Available PPSD Files:")
                print("-" * 80)
                print(f"{'ID':<5} {'Filename':<40} {'Start Time':<20} {'End Time':<20}")
                print("-" * 80)
                
                for file_id, filename, start_time, end_time, created_at in files:
                    print(f"{file_id:<5} {filename:<40} {start_time} {end_time}")
                
                return files
        finally:
            connection.close()
    
    def get_ppsd_by_id(self, ppsd_id):
        """Get PPSD file by ID"""
        connection = self.connect_db()
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT id, filename, start_time, end_time, content 
                    FROM ppsd_files 
                    WHERE id = %s
                """, (ppsd_id,))
                return cursor.fetchone()
        finally:
            connection.close()
    
    def get_ppsd_by_filename(self, filename):
        """Get PPSD file by filename"""
        connection = self.connect_db()
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT id, filename, start_time, end_time, content 
                    FROM ppsd_files 
                    WHERE filename LIKE %s
                """, (f"%{filename}%",))
                return cursor.fetchall()
        finally:
            connection.close()
    
    def display_ppsd(self, ppsd_data):
        """
        Display PPSD image from database
        
        Args:
            ppsd_data (tuple): Database row containing PPSD data
        """
        if not ppsd_data:
            print("❌ PPSD data not found!")
            return
        
        ppsd_id, filename, start_time, end_time, content = ppsd_data
        
        try:
            # Convert binary data to image
            image_buffer = io.BytesIO(content)
            image = Image.open(image_buffer)
            
            # Display using matplotlib
            plt.figure(figsize=(15, 10))
            plt.imshow(image)
            plt.axis('off')
            plt.title(f'PPSD: {filename}\nTime: {start_time} - {end_time}', 
                     fontsize=12, pad=20)
            plt.tight_layout()
            plt.show()
            
            print(f"✅ Displayed PPSD for: {filename}")
            
        except Exception as e:
            print(f"❌ Error displaying PPSD: {e}")
    
    def save_ppsd_to_file(self, ppsd_data, output_path=None):
        """
        Save PPSD image from database to file
        
        Args:
            ppsd_data (tuple): Database row containing PPSD data
            output_path (str): Path to save the image (optional)
        """
        if not ppsd_data:
            print("❌ PPSD data not found!")
            return
        
        ppsd_id, filename, start_time, end_time, content = ppsd_data
        
        try:
            # Generate output filename if not provided
            if output_path is None:
                base_name = os.path.splitext(filename)[0]
                output_dir = "ppsd_output"
                os.makedirs(output_dir, exist_ok=True)
                output_path = os.path.join(output_dir, f"{base_name}_ppsd.png")

            
            # Convert binary data to image and save
            image_buffer = io.BytesIO(content)
            image = Image.open(image_buffer)
            image.save(output_path)
            
            print(f"✅ PPSD saved to: {output_path}")
            return output_path
            
        except Exception as e:
            print(f"❌ Error saving PPSD: {e}")
            return None
    
    def search_ppsd(self, search_term):
        """Search PPSD files by filename"""
        print(f"🔍 Searching for: '{search_term}'")
        results = self.get_ppsd_by_filename(search_term)
        
        if not results:
            print("❌ No PPSD files found matching the search term.")
            return []
        
        print(f"✅ Found {len(results)} matching files:")
        print("-" * 80)
        print(f"{'ID':<5} {'Filename':<40} {'Start Time':<20} {'End Time':<20}")
        print("-" * 80)
        
        for ppsd_id, filename, start_time, end_time, _ in results:
            print(f"{ppsd_id:<5} {filename:<40} {start_time} {end_time}")
        
        return results

def main():
    # Database configuration
    db_config = {
        'host': 'localhost',
        'user': 'root', 
        'password': 'Raihan@3012',
        'database': 'seismic_monitoring',
        'charset': 'utf8mb4',
        'cursorclass': pymysql.cursors.DictCursor
    }
    
    # Create PPSD viewer instance
    viewer = PPSDViewer(db_config)
    
    while True:
        print("\n" + "="*60)
        print("🖼️  PPSD Database Viewer")
        print("="*60)
        print("1. List all PPSD files")
        print("2. Display PPSD by ID")
        print("3. Search PPSD by filename")
        print("4. Save PPSD to file")
        print("5. Exit")
        print("-"*60)
        
        choice = input("Select option (1-5): ").strip()
        
        if choice == '1':
            print("\n📋 Listing all PPSD files...")
            viewer.list_ppsd_files()
            
        elif choice == '2':
            try:
                ppsd_id = int(input("Enter PPSD ID: "))
                ppsd_data = viewer.get_ppsd_by_id(ppsd_id)
                if ppsd_data:
                    print(f"\n🖼️  Displaying PPSD ID: {ppsd_id}")
                    viewer.display_ppsd(ppsd_data)
                else:
                    print(f"❌ PPSD with ID {ppsd_id} not found!")
            except ValueError:
                print("❌ Invalid ID! Please enter a number.")
                
        elif choice == '3':
            search_term = input("Enter filename to search: ").strip()
            if search_term:
                results = viewer.search_ppsd(search_term)
                if results:
                    try:
                        ppsd_id = int(input("\nEnter ID to display (or 0 to cancel): "))
                        if ppsd_id > 0:
                            ppsd_data = viewer.get_ppsd_by_id(ppsd_id)
                            if ppsd_data:
                                viewer.display_ppsd(ppsd_data)
                            else:
                                print(f"❌ PPSD with ID {ppsd_id} not found!")
                    except ValueError:
                        print("❌ Invalid ID!")
            else:
                print("❌ Please enter a search term!")
                
        elif choice == '4':
            try:
                ppsd_id = int(input("Enter PPSD ID to save: "))
                ppsd_data = viewer.get_ppsd_by_id(ppsd_id)
                if ppsd_data:
                    output_path = input("Enter output path (or press Enter for default): ").strip()
                    if not output_path:
                        output_path = None
                    viewer.save_ppsd_to_file(ppsd_data, output_path)
                else:
                    print(f"❌ PPSD with ID {ppsd_id} not found!")
            except ValueError:
                print("❌ Invalid ID! Please enter a number.")
                
        elif choice == '5':
            print("👋 Goodbye!")
            break
            
        else:
            print("❌ Invalid option! Please select 1-5.")

# Example functions for direct usage
def quick_display_by_id(db_config, ppsd_id):
    """Quick function to display PPSD by ID"""
    viewer = PPSDViewer(db_config)
    ppsd_data = viewer.get_ppsd_by_id(ppsd_id)
    viewer.display_ppsd(ppsd_data)

def quick_save_by_id(db_config, ppsd_id, output_path=None):
    """Quick function to save PPSD by ID"""
    viewer = PPSDViewer(db_config)
    ppsd_data = viewer.get_ppsd_by_id(ppsd_id)
    return viewer.save_ppsd_to_file(ppsd_data, output_path)

if __name__ == "__main__":
    main()