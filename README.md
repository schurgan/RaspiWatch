# RaspiWatch (Domoticz Plugin)

RaspiWatch ist ein Domoticz-Plugin zur Überwachung eines entfernten Raspberry Pi
über SSH.  
Zusätzlich kann der Status eines **remote Domoticz-Dienstes** geprüft,
per Telegram gemeldet und bei Bedarf automatisch neu gestartet werden.

## Funktionen

### 1. Erreichbarkeit des Raspberry Pi
- Prüfung per SSH (key-based, ohne Passwort)
- Darstellung als Domoticz-Schalter
  - **ON** = Raspi erreichbar
  - **OFF** = Raspi nicht erreichbar
- Telegram-Benachrichtigung bei Statuswechsel (UP / DOWN)

### 2. Überwachung des Remote-Domoticz-Dienstes
- Prüfung per  
  `systemctl is-active domoticz`
- Separater Domoticz-Schalter:
  - **ON** = Domoticz läuft
  - **OFF** = Domoticz gestoppt / fehlgeschlagen
- Telegram-Benachrichtigung bei:
  - Domoticz DOWN
  - Domoticz wieder OK

### 3. Automatischer Neustart von Domoticz (optional)
- Wenn Domoticz DOWN erkannt wird:
  - begrenzte Anzahl von Neustart-Versuchen
  - Mindestabstand zwischen Neustarts
- Neustart erfolgt per SSH:
  `sudo systemctl restart domoticz`
- Neustart-Zähler wird zurückgesetzt, sobald Domoticz wieder läuft
- Kein Neustart, wenn der Raspberry Pi selbst nicht erreichbar ist

### 4. Schutz vor Spam / Endlosschleifen
- Separate Intervalle für:
  - SSH-Erreichbarkeitsprüfung
  - Domoticz-Dienstprüfung
- Telegram nur bei echten Zustandswechseln
- Restart-Versuche strikt limitiert

---

## Voraussetzungen

- Domoticz läuft auf dem überwachenden Raspberry Pi
- SSH-Key-Login **ohne Passwort** vom Domoticz-User (oft `root`)
- Auf dem überwachten Raspberry Pi:
  ```bash
  sudo visudo
