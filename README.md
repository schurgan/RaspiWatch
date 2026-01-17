# RaspiWatch – Domoticz Raspberry Pi Monitor (SSH)

**RaspiWatch** ist ein Domoticz-Python-Plugin zur Überwachung eines entfernten Raspberry Pi per **SSH**.  
Es erstellt einen **Switch**:
- **ON** = Raspi erreichbar
- **OFF** = Raspi nicht erreichbar

Optional werden **Telegram-Benachrichtigungen** bei Zustandswechseln gesendet.

---

## Features
- SSH-basierter Health-Check (erkennt echte Hänger)
- Domoticz-Switch (Unit 1)
- Telegram-Alarm bei UP/DOWN
- **VPN-/FRITZ!Box-schonend**:
  - Domoticz-Heartbeat bleibt klein (stabil)
  - SSH-Checks werden intern gedrosselt (z. B. alle 5–10 Minuten)

---

## Voraussetzungen
- Domoticz mit **Python Plugin Support**
- SSH-Key-Auth **ohne Passwort**
- `ssh` und optional `curl` installiert
- Plugin läuft auf **Raspi 2** und überwacht **Raspi 1**

### SSH testen
```bash
ssh user@raspi1 "echo ok"
