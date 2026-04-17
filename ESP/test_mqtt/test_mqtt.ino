#include <ESP8266WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <TimeLib.h>

// Konfigurasi WiFi
const char* ssid = "Bani Widiyatno";
const char* password = "alhamdulillah";

// Konfigurasi HiveMQ Cloud (Ganti sesuai akun HiveMQ Cloud kamu)
const char* mqtt_server = "240fa9ad32cb44929936ab704925afa5.s1.eu.hivemq.cloud";  // <- ganti sesuai cluster
const int mqtt_port = 8883;  // TLS Port
const char* mqtt_user = "project-kuliah";    // <- ganti sesuai akun HiveMQ Cloud
const char* mqtt_password = "Raihan@3012"; // <- ganti sesuai akun HiveMQ Cloud

WiFiClientSecure espClient;
PubSubClient client(espClient);

// Fungsi untuk menghubungkan ke WiFi
void setup_wifi() {
  delay(10);
  Serial.println();
  Serial.print("Menghubungkan ke WiFi: ");
  Serial.println(ssid);

  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {
    delay(1000);
    Serial.print(".");
  }

  Serial.println("");
  Serial.println("WiFi terhubung");
  Serial.println("Alamat IP: ");
  Serial.println(WiFi.localIP());
}

// Fungsi untuk menghubungkan ke broker MQTT
void reconnect() {
  while (!client.connected()) {
    Serial.print("Menghubungkan ke broker MQTT...");
    if (client.connect("NodeMCUClient", mqtt_user, mqtt_password)) {
      Serial.println("Terhubung");
    } else {
      Serial.print("Gagal, rc=");
      Serial.print(client.state());
      Serial.println(" Coba lagi dalam 5 detik...");
      delay(5000);
    }
  }
}

// Fungsi untuk menghasilkan data dummy
String generateDummyData() {
  StaticJsonDocument<200> jsonDoc;
  jsonDoc["longitude"] = random(-180, 180); // Longitude acak
  jsonDoc["latitude"] = random(-90, 90);   // Latitude acak
  
  // Mendapatkan waktu dalam format Y-m-d H:i:s
  char timeBuffer[20];
  sprintf(timeBuffer, "%04d-%02d-%02d %02d:%02d:%02d", 
          year(), month(), day(), hour(), minute(), second());
  jsonDoc["reading_times"] = timeBuffer; // Format waktu sebagai string

  String payload;
  serializeJson(jsonDoc, payload);
  return payload;
}

void setup() {
  Serial.begin(115200);
  setup_wifi();

  // Konfigurasi koneksi TLS
  espClient.setInsecure(); // Nonaktifkan verifikasi sertifikat (untuk testing)

  client.setServer(mqtt_server, mqtt_port);
}

void loop() {
  if (!client.connected()) {
    reconnect();
  }
  client.loop();

  // Kirim data setiap 10 detik
  static unsigned long lastSend = 0;
  if (millis() - lastSend > 10000) {
    lastSend = millis();

    String payload = generateDummyData();
    Serial.print("Mengirim payload: ");
    Serial.println(payload);

    // Publis ke topik MQTT
    if (client.publish("sensors/gps", payload.c_str())) {
      Serial.println("Payload terkirim");
    } else {
      Serial.println("Gagal mengirim payload");
    }
  }
}