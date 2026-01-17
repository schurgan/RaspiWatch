"""
<?xml version="1.0" encoding="UTF-8"?>
<plugin key="RaspiWatch" name="Raspi Watch (SSH)" author="Alex" version="0.1.0">
    <description>
        Monitors a remote Raspberry Pi via SSH from this Domoticz host.
        Creates one Switch device: ON = reachable, OFF = down.
        Optional Telegram notifications on state changes.
    </description>

    <params>
        <param field="Address" label="Raspi Garten IP/Hostname" width="200px" required="true" default="192.168.178.50"/>
        <param field="Port" label="(unused) Port" width="60px" required="false" default="0"/>

        <param field="Mode1" label="SSH User" width="150px" required="true" default="schurgan"/>
        <param field="Mode2" label="Retries" width="60px" required="true" default="3"/>
        <param field="Mode3" label="SSH Timeout (s)" width="60px" required="true" default="3"/>

        <param field="Mode4" label="Telegram Bot Token (optional)" width="350px" required="false" default=""/>
        <param field="Mode5" label="Telegram Chat ID (optional)" width="200px" required="false" default=""/>
        <param field="Mode6" label="Telegram Cooldown (s)" width="80px" required="true" default="1800"/>
    </params>
</plugin>
"""

import Domoticz
import subprocess
import time
import os

class BasePlugin:
    def __init__(self):
        self.enabled = True
        self.last_state = None        # None/True/False
        self.last_alert_ts = 0
        self.fast_start = True
        self.check_interval = 300     # echter SSH-Check alle 5 Minuten
        self.next_check_ts = 0
        self.fast_start = True        # beim Start einmal schnell prüfen

    def onStart(self):
        Domoticz.Log("RaspiWatch: onStart")

        # Parameters
        self.host = Parameters.get("Address", "").strip()          # Raspi Garten IP/hostname
        self.port = Parameters.get("Port", "").strip()             # not used (kept for UI)
        self.user = Parameters.get("Mode1", "schurgan").strip()    # SSH user
        self.retries = int(Parameters.get("Mode2", "3"))           # tries per check
        self.timeout = int(Parameters.get("Mode3", "3"))           # seconds per ssh connect timeout

        # Telegram (optional)
        self.tg_token = Parameters.get("Mode4", "").strip()
        self.tg_chatid = Parameters.get("Mode5", "").strip()
        self.cooldown = int(Parameters.get("Mode6", "1800"))       # seconds

        if not self.host:
            Domoticz.Error("RaspiWatch: No Address configured (Raspi Garten IP/hostname).")
            self.enabled = False
            return

        # Create device if missing
        # Unit 1 = Switch
        if 1 not in Devices:
            Domoticz.Device(
                Name="Raspi Garten Reachable",
                Unit=1,
                TypeName="Switch",
                Used=1
            ).Create()

        # Heartbeat interval in seconds
        Domoticz.Heartbeat(30)  # check every 30s (change if you want)

        Domoticz.Log(
            f"RaspiWatch: Monitoring {self.user}@{self.host}, retries={self.retries}, timeout={self.timeout}s, telegram={'on' if self.tg_token and self.tg_chatid else 'off'}"
        )

    def onStop(self):
        Domoticz.Log("RaspiWatch: onStop")

    def onHeartbeat(self):
        if not self.enabled:
            return
        
        if 1 not in Devices:
                return
        now = time.time()

        # beim Start einmal sofort prüfen, danach nur alle check_interval Sekunden
        if self.fast_start:
            self.fast_start = False
        else:
            if now < self.next_check_ts:
                return

        self.next_check_ts = now + self.check_interval
        
        ok = self._check_ssh()

        # Update switch: On=reachable, Off=down
        new_level = 1 if ok else 0
        dev = Devices[1]
        if dev.nValue != new_level:
            dev.Update(nValue=new_level, sValue=str(new_level))
            Domoticz.Log(f"RaspiWatch: State changed -> {'UP' if ok else 'DOWN'}")

        # Telegram on transitions (UP->DOWN and DOWN->UP)
        if self.last_state is None:
            self.last_state = ok
            return

        if ok != self.last_state:
            if ok:
                self._maybe_send_telegram(f"🟢 WIEDER OK\nRaspi Garten ({self.host}) ist wieder erreichbar.\nZeit: {time.strftime('%d.%m.%Y %H:%M:%S')}", bypass_cooldown=True)
            else:
                self._maybe_send_telegram(f"🚨 ALARM 🚨\nRaspi Garten ({self.host}) reagiert NICHT auf SSH.\nZeit: {time.strftime('%d.%m.%Y %H:%M:%S')}", bypass_cooldown=False)
            self.last_state = ok

    # ---------------- internals ----------------

    def _check_ssh(self) -> bool:
        """
        Uses system ssh client with strict timeouts.
        Requires key-based auth already configured: ssh user@host "echo ok" without password.
        """
        cmd = [
            "ssh",
            "-o", "BatchMode=yes",
            "-o", f"ConnectTimeout={self.timeout}",
            "-o", "ConnectionAttempts=1",
            "-o", "ServerAliveInterval=2",
            "-o", "ServerAliveCountMax=1",
            f"{self.user}@{self.host}",
            "echo ok"
        ]

        for attempt in range(1, self.retries + 1):
            try:
                p = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if p.returncode == 0:
                    return True
            except Exception as e:
                Domoticz.Error(f"RaspiWatch: SSH check exception: {e}")
            time.sleep(2)

        return False

    def _maybe_send_telegram(self, msg: str, bypass_cooldown: bool = False):
        if not (self.tg_token and self.tg_chatid):
            return

        now = int(time.time())
        if (not bypass_cooldown) and (now - self.last_alert_ts < self.cooldown):
            return

        # Use curl to avoid python requests dependency
        cmd = [
            "curl", "-s", "-X", "POST",
            f"https://api.telegram.org/bot{self.tg_token}/sendMessage",
            "-d", f"chat_id={self.tg_chatid}",
            "-d", f"text={msg}"
        ]
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.last_alert_ts = now
        except Exception as e:
            Domoticz.Error(f"RaspiWatch: Telegram send failed: {e}")


global _plugin
_plugin = BasePlugin()

def onStart():
    _plugin.onStart()

def onStop():
    _plugin.onStop()

def onHeartbeat():
    _plugin.onHeartbeat()
