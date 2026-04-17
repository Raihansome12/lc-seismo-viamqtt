import pymysql

# Konfigurasi koneksi database
db_config = {
    'host': 'localhost',
    'user': 'root',    # Ganti dengan username MySQL Anda
    'password': 'Raihan@3012',  # Ganti dengan password MySQL Anda
    'database': 'seismic_monitoring',  # Ganti dengan nama database Anda
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}

# ID file yang ingin diambil
file_id = 5  # Ganti sesuai ID file_mseed yang ingin diambil

try:
    # Koneksi ke database
    connection = pymysql.connect(**db_config)

    with connection.cursor() as cursor:
        # Ambil file berdasarkan ID
        sql = "SELECT filename, content FROM mseed_files WHERE id = %s"
        cursor.execute(sql, (file_id,))
        row = cursor.fetchone()

        if row:
            filename = row['filename']
            content = row['content']

            # Simpan file ke disk
            with open(filename, 'wb') as f:
                f.write(content)

            print(f"✅ File '{filename}' berhasil disimpan.")
        else:
            print("❌ Data tidak ditemukan untuk ID tersebut.")

finally:
    connection.close()
