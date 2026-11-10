// Receives "ALERT <score>" lines over USB from scripts/predict_onnx.py --serial
// and sends an SMS through a SIM800C. Board: Uno / Nano (any AVR with SoftwareSerial).
//
// Wiring: SIM800C TXD -> pin 7, SIM800C RXD -> pin 8, GND -> GND (shared),
// SIM800C V_M (logic level pin) -> Arduino 5V.
// Power the SIM800C from its own 5V / 2A supply into VCC_IN, not the
// Arduino 5V pin: it draws 2A bursts while transmitting and will brown out the Arduino.

#include <SoftwareSerial.h>

const char PHONE[] = "+639XXXXXXXXX";               // CHANGE ME: number that gets the SMS
const unsigned long COOLDOWN_MS = 10UL * 60 * 1000;  // at most one SMS per 10 minutes

SoftwareSerial sim(7, 8);  // RX, TX
unsigned long lastSent = 0;
bool sentBefore = false;

// Forward whatever the SIM800C replied so it shows up on the PC.
void echoSim(unsigned long ms) {
  unsigned long start = millis();
  while (millis() - start < ms) {
    while (sim.available()) Serial.write(sim.read());
  }
}

void sendSms(const String &text) {
  sim.print("AT+CMGS=\"");
  sim.print(PHONE);
  sim.println("\"");
  echoSim(500);
  sim.print(text);
  sim.write(26);  // Ctrl+Z sends the message
  echoSim(5000);  // look for "+CMGS:" (sent) or "ERROR" in the output
}

void setup() {
  Serial.begin(9600);
  sim.begin(9600);
  echoSim(3000);  // give the module time to boot and register on the network
  sim.println("AT");
  echoSim(500);
  sim.println("AT+CMGF=1");  // text mode
  echoSim(500);
  Serial.println("READY");
}

void loop() {
  if (!Serial.available()) return;
  String line = Serial.readStringUntil('\n');
  line.trim();
  if (!line.startsWith("ALERT")) return;

  if (sentBefore && millis() - lastSent < COOLDOWN_MS) {
    Serial.println("COOLDOWN");
    return;
  }
  sendSms("ASCLEPIUS: possible BCC detected, confidence " + line.substring(6));
  lastSent = millis();
  sentBefore = true;
  Serial.println("SENT");
}
