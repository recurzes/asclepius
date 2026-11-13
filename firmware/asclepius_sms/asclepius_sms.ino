// Receives "ALERT <score>" lines over USB from the ASCLEPIUS desktop app and sends an
// SMS through a SIM800C. Board: Uno / Nano (any AVR with SoftwareSerial).
//
// Wiring: SIM800C TXD -> pin 7, SIM800C RXD -> pin 8, GND -> GND (shared),
// SIM800C V_M (logic level pin) -> Arduino 5V.
// Power the SIM800C from its own 5V / 2A supply into VCC_IN, not the
// Arduino 5V pin: it draws 2A bursts while transmitting and will brown out the Arduino.
//
// Replies to the PC, one per line:
//   READY                 sketch started
//   NO MODULE <hint>      SIM800C did not answer at startup
//   SENT                  module confirmed the SMS (+CMGS)
//   FAILED <reason>       SMS not sent; the cooldown is not started
//   COOLDOWN              skipped, an SMS went out less than COOLDOWN_MS ago
// Everything the SIM800C says is forwarded too, so it shows in the app's activity log.

#include <SoftwareSerial.h>

const char PHONE[] = "+639XXXXXXXXX";               // CHANGE ME: number that gets the SMS
const unsigned long COOLDOWN_MS = 60UL * 1000;       // at most one SMS per minute

const char HINT_WIRING[] = "check SIM800C power (NET LED), TXD->D7, RXD->D8, shared GND, V_M->5V";

SoftwareSerial sim(7, 8);  // RX, TX
unsigned long lastSent = 0;
bool sentBefore = false;

// Forward the module's replies to the PC for up to `ms`, returning early once the
// reply contains "\nOK", "ERROR" or `until`. Returns what was received (last ~150
// chars); an empty string means the module said nothing at all.
String collect(unsigned long ms, const char *until = nullptr) {
  String reply;
  unsigned long start = millis(), lastByte = millis();
  bool done = false;
  while (millis() - start < ms) {
    while (sim.available()) {
      char c = sim.read();
      Serial.write(c);
      reply += c;
      if (reply.length() > 150) reply.remove(0, reply.length() - 150);
      lastByte = millis();
    }
    if (reply.indexOf("\nOK") >= 0 || reply.indexOf("ERROR") >= 0) done = true;
    if (until && reply.indexOf(until) >= 0) done = true;
    // After a match, keep reading until the line ends. SoftwareSerial can't receive
    // while it transmits, so sending the next command over the reply's trailing
    // "\r\n" garbles those bytes (they showed up as "?" in the log).
    if (done && millis() - lastByte > 20) break;
  }
  return reply;
}

String command(const char *cmd, unsigned long ms) {
  sim.println(cmd);
  return collect(ms);
}

// The line of `reply` starting at `key` (or at "ERROR"), for quoting the module's
// own answer in a FAILED message instead of guessing. Unreadable bytes become '?'.
String said(const String &reply, const char *key) {
  int at = reply.indexOf(key);
  if (at < 0) at = reply.indexOf("ERROR");
  if (at < 0) return "nothing";
  String line = reply.substring(at);
  int end = line.indexOf('\r');
  if (end >= 0) line.remove(end);
  for (unsigned int i = 0; i < line.length(); i++)
    if (line[i] < 32 || line[i] > 126) line[i] = '?';
  return line;
}

char failure[128];  // FAILED messages that quote the module

// Returns nullptr when the module confirmed the SMS, otherwise why it failed.
const char *sendSms(const String &text) {
  collect(50);  // flush anything left over from earlier

  String r = command("AT", 1000);
  if (r.length() == 0) return "no reply from SIM800C";

  // Check the SIM first: without one the module rejects every SMS command,
  // which would otherwise be reported as a confusing text-mode error.
  // Right after power-up the module answers "+CPIN: NOT READY" (or a bare ERROR)
  // for a while, so give it up to ~10 s before giving up.
  for (int attempt = 0; attempt < 5; attempt++) {
    if (attempt > 0) collect(2000);  // wait, still forwarding anything it says
    r = command("AT+CPIN?", 2000);
    if (r.indexOf("+CPIN: READY") >= 0) break;
    if (r.indexOf("SIM PIN") >= 0) return "SIM has PIN lock on (turn it off in a phone)";
    if (r.indexOf("SIM PUK") >= 0) return "SIM is PUK-locked (too many wrong PINs; unlock it in a phone)";
    if (r.indexOf("NOT INSERTED") >= 0 || r.indexOf("ERROR: 10") >= 0 || r.indexOf("ERROR: 13") >= 0)
      return "SIM not detected (check orientation and seating, then power-cycle the module)";
  }
  if (r.indexOf("+CPIN: READY") < 0) {
    snprintf(failure, sizeof failure, "SIM not ready after 10 s, module said: %s", said(r, "+CPIN").c_str());
    return failure;
  }

  // Right after power-up the SMS service needs a few seconds after the SIM is ready.
  if (command("AT+CMGF=1", 1000).indexOf("\nOK") < 0)
    return "SMS service not ready yet (wait ~10 s after power-up and retry)";

  // "+CREG: 0,1" = home network, "0,5" = roaming, "0,2" = still searching (normal for
  // up to a minute after power-up), "0,3" = network refused the SIM.
  bool registered = false;
  for (int attempt = 0; attempt < 20 && !registered; attempt++) {
    if (attempt > 0) collect(3000);
    r = command("AT+CREG?", 2000);
    registered = r.indexOf(",1") >= 0 || r.indexOf(",5") >= 0;
    if (r.indexOf(",3") >= 0) return "network refused the SIM (CREG 0,3): is the SIM active and registered?";
  }
  if (!registered) {
    String creg = said(r, "+CREG");
    String csq = said(command("AT+CSQ", 2000), "+CSQ");  // 99,99 = no signal at all
    snprintf(failure, sizeof failure, "not registered after 60 s (%s, signal %s): antenna, power, or no 2G here",
             creg.c_str(), csq.c_str());
    return failure;
  }

  sim.print("AT+CMGS=\"");
  sim.print(PHONE);
  sim.println("\"");
  if (collect(5000, ">").indexOf('>') < 0) {
    sim.write(27);  // ESC cancels the half-started command
    return "module did not accept the phone number";
  }
  sim.print(text);
  sim.write(26);  // Ctrl+Z sends the message

  r = collect(60000);  // the network can take a while to confirm
  if (r.indexOf("+CMGS:") >= 0) return nullptr;
  if (r.indexOf("ERROR") >= 0) return "network rejected the SMS (no credit? number format?)";
  return "no confirmation from the network within 60 s";
}

void setup() {
  Serial.begin(9600);
  sim.begin(9600);
  collect(3000);  // give the module time to boot
  if (command("AT", 1000).length() == 0) {
    Serial.print("NO MODULE ");
    Serial.println(HINT_WIRING);
  }
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
  const char *error = sendSms("ASCLEPIUS: possible BCC detected, confidence " + line.substring(6));
  Serial.println();  // module output may not end with a newline
  if (error) {
    Serial.print("FAILED ");
    Serial.print(error);
    if (strcmp(error, "no reply from SIM800C") == 0) {
      Serial.print(": ");
      Serial.print(HINT_WIRING);
    }
    Serial.println();
    return;
  }
  lastSent = millis();
  sentBefore = true;
  Serial.println("SENT");
}
