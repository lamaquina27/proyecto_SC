#include <BH1750.h>
#include <DHT.h>
#include <Wire.h>

// -----------------------------
// CONFIGURACION DE PINES
// -----------------------------

#define DHT_PIN 4
#define DHT_TYPE DHT11

#define SOIL_PIN 5

#define SDA_PIN 8
#define SCL_PIN 9

// -----------------------------
// OBJETOS DE LOS SENSORES
// -----------------------------

DHT dht(DHT_PIN, DHT_TYPE);
BH1750 lightSensor;

// -----------------------------
// CONFIGURACION INICIAL
// -----------------------------

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println();
  Serial.println("================================");
  Serial.println("  COMPLEXNET - BALIZA ESP32 S3  ");
  Serial.println("================================");

  // Configurar sensor DHT11
  dht.begin();

  // Configurar sensor analogico
  analogReadResolution(12);

  // Configurar comunicacion I2C
  Wire.begin(SDA_PIN, SCL_PIN);

  // Iniciar GY-302 en direccion 0x23
  if (lightSensor.begin(BH1750::CONTINUOUS_HIGH_RES_MODE, 0x23, &Wire)) {
    Serial.println("GY-302: CONECTADO");
  } else {
    Serial.println("ERROR: GY-302 NO DETECTADO");
  }

  Serial.println("Sistema iniciado correctamente.");
  Serial.println("--------------------------------");
}

// -----------------------------
// LECTURA DE LOS SENSORES
// -----------------------------

void loop() {
  // Temperatura y humedad ambiental
  float temperatura = dht.readTemperature();
  float humedadAire = dht.readHumidity();

  // Humedad de la tierra (ADC 12 bits: 0 a 4095)
  int humedadTierra = analogRead(SOIL_PIN);

  // Intensidad de luz en lux
  float luz = lightSensor.readLightLevel();

  // Emision de datos en formato JSON para ComplexNet API
  Serial.print("{\"temp\": ");
  if (isnan(temperatura)) {
    Serial.print("null");
  } else {
    Serial.print(temperatura, 1);
  }

  Serial.print(", \"hum_aire\": ");
  if (isnan(humedadAire)) {
    Serial.print("null");
  } else {
    Serial.print(humedadAire, 1);
  }

  Serial.print(", \"suelo\": ");
  Serial.print(humedadTierra);

  Serial.print(", \"luz\": ");
  if (luz < 0) {
    Serial.print("null");
  } else {
    Serial.print(luz, 1);
  }
  Serial.println("}");

  delay(2000);
}
