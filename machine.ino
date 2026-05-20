/*
  RGBDuino Sample Machine
  Adaptado para:
  - JC_Button
  - RGB Lamp onboard (NeoPixel)

  Estados:
  OFF
  ON
  WAITING
  DROP
*/

#include <JC_Button.h>
#include <Adafruit_NeoPixel.h>

// ======================================================
// RGBDuino Hardware
// ======================================================

// Botão onboard
#define BUTTON_PIN 2

// RGB Lamp onboard
#define RGB_PIN 12
#define RGB_COUNT 2

// ======================================================
// OBJETOS
// ======================================================

Button sampleButton(BUTTON_PIN, 25, true, true);

Adafruit_NeoPixel rgbLamp(
  RGB_COUNT,
  RGB_PIN,
  NEO_GRB + NEO_KHZ800
);

// ======================================================
// ESTADOS
// ======================================================

enum MachineState {
  OFF_STATE,
  ON_STATE,
  WAITING_STATE,
  DROP_STATE
};

MachineState currentState = OFF_STATE;

// ======================================================
// CONTROLE
// ======================================================

unsigned long waitingStart = 0;
const unsigned long WAITING_TIME = 20000;

bool onMessageSent = false;
String serialBuffer = "";

// ======================================================
// SETUP
// ======================================================

void setup() {

  Serial.begin(115200);
  Serial.setTimeout(50);

  sampleButton.begin();

  rgbLamp.begin();
  rgbLamp.show();

  enterState(OFF_STATE);
  Serial.println("ready");
}

// ======================================================
// LOOP
// ======================================================

void loop() {

  sampleButton.read();

  String cmd = readSerialCommand();

  handleCommand(cmd);

  switch (currentState) {

    // ==================================================
    // OFF
    // ==================================================

    case OFF_STATE:

      break;

    // ==================================================
    // ON
    // ==================================================

    case ON_STATE:

      if (!onMessageSent) {

        Serial.println("on");

        onMessageSent = true;
      }

      break;

    // ==================================================
    // WAITING
    // ==================================================

    case WAITING_STATE:

      // TODO FUNCTION TO WORK MACHINE

      // botão apertado
      if (sampleButton.wasPressed()) {

        enterState(DROP_STATE);
      }

      // timeout
      if (millis() - waitingStart >= WAITING_TIME) {

        enterState(ON_STATE);
      }

      break;

    // ==================================================
    // DROP
    // ==================================================

    case DROP_STATE:

      blinkBlue();

      Serial.println("dropped");

      enterState(ON_STATE);

      break;
  }
}

// ======================================================
// ENTRADA DE ESTADO
// ======================================================

void enterState(MachineState newState) {

  currentState = newState;

  switch (currentState) {

    case OFF_STATE:

      setColor(255, 0, 0); // vermelho

      break;

    case ON_STATE:

      setColor(0, 255, 0); // verde

      onMessageSent = false;

      break;

    case WAITING_STATE:

      setColor(255, 255, 0); // amarelo

      waitingStart = millis();

      break;

    case DROP_STATE:

      break;
  }
}

// ======================================================
// SERIAL
// ======================================================

String readSerialCommand() {

  while (Serial.available() > 0) {

    char ch = (char)Serial.read();

    if (ch == '\n' || ch == '\r') {

      String cmd = serialBuffer;
      serialBuffer = "";
      cmd.trim();
      cmd.toLowerCase();

      if (cmd.length() > 0) {
        return cmd;
      }
    } else if (serialBuffer.length() < 32) {

      serialBuffer += ch;
    } else {

      serialBuffer = "";
      Serial.println("error:command_too_long");
    }
  }

  return "";
}

void handleCommand(String cmd) {

  if (cmd.length() == 0) {
    return;
  }

  if (cmd == "on") {

    enterState(ON_STATE);
    return;
  }

  if (cmd == "off") {

    enterState(OFF_STATE);
    Serial.println("off");
    return;
  }

  if (cmd == "drop") {

    if (currentState == ON_STATE) {
      enterState(WAITING_STATE);
    } else {
      Serial.println("error:not_on");
    }
    return;
  }

  if (cmd == "reset") {

    enterState(ON_STATE);
    Serial.println("reset");
    return;
  }

  if (cmd == "status") {

    printStatus();
    return;
  }

  Serial.println("error:unknown_command");
}

void printStatus() {

  switch (currentState) {

    case OFF_STATE:
      Serial.println("status:off");
      break;

    case ON_STATE:
      Serial.println("status:on");
      break;

    case WAITING_STATE:
      Serial.println("status:waiting");
      break;

    case DROP_STATE:
      Serial.println("status:drop");
      break;
  }
}

// ======================================================
// RGB
// ======================================================

void setColor(uint8_t r, uint8_t g, uint8_t b) {

  for (int i = 0; i < RGB_COUNT; i++) {

    rgbLamp.setPixelColor(
      i,
      rgbLamp.Color(r, g, b)
    );
  }

  rgbLamp.show();
}

// ======================================================
// DROP EFFECT
// ======================================================

void blinkBlue() {

  for (int i = 0; i < 2; i++) {

    setColor(0, 0, 255);

    delay(200);

    setColor(0, 0, 0);

    delay(200);
  }
}
