# SMS alerts: SIM800C + Arduino + ASCLEPIUS desktop app

When the desktop app finds a lesion above the confidence you set, it sends the line `ALERT 0.93` to the Arduino over USB. The Arduino then has the SIM800C text a phone number.

```
Webcam / image ──► PC (ASCLEPIUS app, runs the model)
                        │ USB: "ALERT 0.93"
                        ▼
                   Arduino Uno/Nano ──► SIM800C ──► SMS to your phone
```

The model can't run on the Arduino itself. It is about 10 MB, and an Uno has 32 KB of memory. So the PC does the detection and the Arduino only sends the SMS.

Wiring diagram: https://claude.ai/artifact/JeJVysPeKQkXZ7ittyUwNh (private; open it from your own Claude account).

---

## 1. What you need

| Part | Notes |
| --- | --- |
| Arduino Uno or Nano | plus its USB cable to the PC |
| SIM800C board | the one with VCC_IN, GND, V_M, TXD, RXD, PWR pins |
| GSM antenna | screw it on before powering the module |
| Micro-SIM card | with load/credit, **PIN lock off** |
| 5 V, 2 A phone charger | e.g. Xiaomi MDY-09-EW (5.0 V ⎓ 2.0 A, USB-A) |
| Spare USB cable | it gets cut; don't use your phone's cable |
| Jumper wires | male-to-female for Uno; female-to-female for a Nano with pins |
| 1000 µF capacitor, 10 V+ | optional, add it if the module restarts while sending |
| Multimeter | to check + and − on the charger wires |
| Soldering iron, heat-shrink or tape | to make the power wires solid |

**Before you start:** put the SIM in a phone and confirm it can send an SMS without asking for a PIN. Also check that your carrier still runs **2G** where you are, because the SIM800C only works on 2G (GSM).

---

## 2. SIM800C pins

Only six pins are used. Leave the rest unconnected.

| SIM800C pin | Connect to | Purpose |
| --- | --- | --- |
| **VCC_IN** | Charger **+5V** | Powers the module |
| **GND** | Charger **GND** | Power ground |
| **GND** (the other one) | Arduino **GND** | Shared ground; required |
| **V_M** | Arduino **5V** | Sets the board's signals to 5 V to match the Arduino. Carries almost no current. |
| **TXD** | Arduino **D7** | Module → Arduino |
| **RXD** | Arduino **D8** | Arduino → module |
| **PWR** | nothing (see step 5) | Power button. Touch to GND for 1–2 s if the module doesn't start. |

**Leave unconnected:** BAT (Li-ion input; never use it together with VCC_IN), MC+ / SPP / SPN (microphone and speaker), ADC, RI, DTR, U2_R, U2_T.

The top VCC_IN/GND pair and the side pair are connected to each other, so you can use either.

---

## 3. Power: the charger, not the Arduino

**Do not power the SIM800C from the Arduino's 5V or 3.3V pin.** The module draws bursts of up to 2 A while sending, and the Arduino can supply only about 0.5 A. The voltage dips, and the module or the Arduino resets right when the SMS should go out. The Arduino's 5V pin only goes to **V_M**, which is just a logic-level reference.

### Make the charger lead

1. Cut the small (phone) end off the spare USB cable. Strip about 1 cm of the outer jacket.
2. Inside you'll usually find **red**, **black**, **green** and **white** wires.
   - Red is normally **+5V** and black is **GND**.
   - Green and white are data wires. Cut them short and tape each one separately.
3. Strip the red and black ends, twist each one tight, and tin it with solder.
4. **Check + and − with a multimeter.** Cheap cables don't always follow the colors.
   - Set the meter to DC volts (20 V range). Keep the bare ends apart and plug in the charger.
   - Red probe on the red wire, black probe on the black wire: **+5 V** means the colors are right, **−5 V** means they're swapped.
   - Unplug the charger before continuing.
5. Cut a **red** jumper and a **black** jumper so that each keeps its **female** end (the end with a hole, not a pin).
6. Solder (or tightly twist) charger **+5V → red jumper** and charger **GND → black jumper**. Cover each joint with heat-shrink or tape so they can't touch.
7. Tug on each joint gently. It must not slip, because a loose power wire is the most common cause of resets mid-SMS.

Jumper colors don't matter electrically, but stick to a convention: **red = +5V, black = every GND**, any other color for TXD, RXD and V_M.

---

## 4. Wire it up (everything unplugged)

| From | Wire | To |
| --- | --- | --- |
| Charger +5V (red jumper, female end) | red | SIM800C **VCC_IN** |
| Charger GND (black jumper, female end) | black | SIM800C **GND** |
| Arduino **GND** | black | SIM800C other **GND** |
| Arduino **5V** | any | SIM800C **V_M** |
| Arduino **D7** | any (e.g. green) | SIM800C **TXD** |
| Arduino **D8** | any (e.g. yellow) | SIM800C **RXD** |
| Arduino USB | USB cable | PC |

Female ends go on the SIM800C's pins (they stick up). Male ends go into the Uno's header holes.

**Optional capacitor (1000 µF):** add it only if the module restarts while sending. Twist its legs in with the charger wires before they go into the jumpers: **long leg with +5V**, **striped (short) leg with GND**. Reversed, it can pop.

Double-check VCC_IN and GND before powering. Reversing them can destroy the module.

---

## 5. Program the Arduino

1. Install the [Arduino IDE](https://www.arduino.cc/en/software).
2. Open `firmware/asclepius_sms/asclepius_sms.ino`.
3. Change the phone number at the top to the one that should receive alerts, in international format:
   ```cpp
   const char PHONE[] = "+639XXXXXXXXX";               // CHANGE ME
   ```
   Optional: `COOLDOWN_MS` sets the minimum time between SMS (default 1 minute).
4. Plug the Arduino into the PC. In the IDE, choose **Tools → Board → Arduino Uno** (or Nano) and **Tools → Port → COMx**.
5. Click **Upload**.

No extra libraries are needed. `SoftwareSerial` comes with the IDE.

---

## 6. Power up and check the network

1. Antenna on, SIM in, wiring checked.
2. Arduino USB plugged into the PC.
3. Plug in the charger.
4. Watch the SIM800C's **NET LED**:

| NET LED | Meaning |
| --- | --- |
| dark | Module is off. Touch **PWR** to **GND** for 1–2 s. Still dark: check VCC_IN power and polarity. |
| blinks about every **1 s** | Searching for the network. SMS will fail. Wait up to a minute. |
| blinks about every **3 s** | Registered. Ready to send. |

---

## 7. Test the SMS without the app (optional)

1. In the Arduino IDE open **Tools → Serial Monitor**. Set **9600 baud** and **Newline** line ending.
2. Wait for `READY`.
3. Type `ALERT 0.99` and press Enter.
4. You should see the module's replies and then `SENT`, which the sketch only prints after the module confirms with **`+CMGS:`**. Otherwise it prints `FAILED <reason>` (see troubleshooting below).
5. **Close the Serial Monitor** afterwards. Only one program can use the COM port, and the app needs it.

Sending again within 1 minute shows `COOLDOWN`. That is the sketch's limit working, not an error.

---

## 8. Run the desktop app

Needs the [.NET 10 SDK](https://dotnet.microsoft.com/download). From the project folder:

```powershell
dotnet run --project desktop
```

Or open `desktop/desktop.slnx` in Visual Studio and press F5.

### Using it

1. **SMS ALERTS** card: pick the Arduino's COM port and click **Connect**.
   - Connecting restarts the Arduino. After a few seconds the status changes to **Ready to send SMS**.
   - If it says `Cannot open COMx`, the Arduino IDE's Serial Monitor is probably still open.
2. **SOURCE** card: choose one.
   - **Start camera**, with Camera 0/1/2/3 if you have several cameras. Click again to stop.
   - **Open image…**, or drag an image onto the viewer.
3. **DETECTION** card: **Minimum confidence** (default 0.50) decides what counts as a detection.
   - Any lesion at or above it gets a box **and triggers an SMS alert**.
   - Lower values catch more lesions but text you about ordinary moles more often.
4. When an alert goes out, the SMS ALERTS card shows **SMS sent at HH:MM:SS**, **SMS skipped (1 min cooldown)**, or **SMS failed at HH:MM:SS: <reason>** in red. A failed SMS doesn't start the cooldown.
5. **Activity log** (bottom of the sidebar) shows everything the Arduino and SIM800C reply, including `+CMGS:` or `ERROR`.

Alert limits:
- **Camera mode:** the app sends at most one alert line every 5 seconds.
- **Sketch:** the Arduino sends at most one SMS per minute, whatever the app sends.
- **Opened images:** each image you open sends an alert right away (still subject to the 1-minute SMS limit).

**Quick end-to-end test:** connect, then open `datasets/bcc/test/images/ISIC_0024331.jpg`. It scores 0.70, above the default 0.50, so it should trigger an SMS.

---

## 9. Troubleshooting

| Symptom | Likely cause / fix |
| --- | --- |
| NET LED dark | Touch PWR to GND for 1–2 s. Check charger polarity on VCC_IN/GND. |
| NET LED blinks every 1 s forever | No network: antenna loose, SIM not seated, or no 2G coverage from your carrier. |
| `Cannot open COMx` in the app | Close the Arduino IDE Serial Monitor. Pick the right port; unplug and replug to see which one appears. |
| Status never says *Ready to send SMS* | Wrong COM port, or the sketch isn't uploaded. Wait about 5 s after Connect. |
| `NO MODULE …` at connect, or `FAILED no reply from SIM800C` | The Arduino hears nothing from the module. Check the NET LED (module on?), TXD→D7 and RXD→D8 (not swapped), the shared GND, and V_M→5V. |
| `FAILED SIM has PIN lock on` (log shows `+CPIN: SIM PIN`) | Put the SIM in a phone and turn off the SIM PIN lock, then put it back and power-cycle the module. |
| `FAILED SIM not detected` (log shows `+CME ERROR: 10`) | SIM upside down, loose in its adapter, or inserted while powered. Reseat it with the power off. |
| `FAILED SIM not detected` (log shows `+CPIN: NOT INSERTED`) | Same as above: the module can't see the SIM. |
| `FAILED SIM not ready after 10 s, module said: …` | The module's own answer is quoted. `+CPIN: NOT READY` that never clears usually means a bad SIM contact or a power dip; reseat the SIM and check the charger wiring. Garbled text means the serial signal is unreliable: check the shared GND and V_M. |
| `FAILED not registered after 60 s (+CREG: 0,2, signal +CSQ: …)` | The module searched for a minute and found no usable network. `+CSQ: 99,99` means no 2G signal at all: check the antenna, try near a window, add the 1000 µF capacitor. Run `AT+COPS=?` (takes up to 3 min) to list the 2G networks in range; an empty list means no 2G here. |
| `FAILED network refused the SIM (CREG 0,3)` | The SIM is inactive, has no government SIM registration, or the carrier blocks it. Test it in a phone. |
| `FAILED network rejected the SMS` | No credit, or phone number not in `+63…` international format. |
| `UNDER-VOLTAGE WARNNING` (sic), or the module restarts mid-send | Loose power joint, or charger too weak. Re-solder and add the 1000 µF capacitor. |
| Arduino restarts (status drops back, `READY` again) when sending | SIM800C is getting power from the Arduino. Power it from the charger only. |
| Garbled characters in the log | GND not shared between Arduino and SIM800C, or V_M not connected to Arduino 5V. |
| `SMS skipped (1 min cooldown)` | Working as designed. Lower `COOLDOWN_MS` in the sketch if you need more frequent texts. |
| Alerts for ordinary moles | The model finds lesions in general, not BCC specifically. Raise **Minimum confidence**. |

---

ASCLEPIUS is a screening aid, not a diagnosis. Refer suspicious lesions to a dermatologist.
