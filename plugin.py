"""
<?xml version="1.0" encoding="UTF-8"?>
<plugin key="RaspiWatch" name="Raspi Watch (SSH)" author="Alex" version="0.1.2">
    <description>
        Monitors a remote Raspberry Pi via SSH from this Domoticz host.
        Creates one Switch device: ON = reachable, OFF = down.
        Optional Telegram notifications on state changes.
    </description>

    <params>
        <param field="Address" label="Monitored Raspi IP/Hostname" width="200px" required="true" default="192.168.178.50"/>
        <param field="Port" label="(unused) Port" width="60px" required="false" default="0"/>

        <param field="Mode1" label="SSH User" width="150px" required="true" default="schurgan"/>
        <param field="Mode2" label="Retries" width="60px" required="true" default="3"/>
        <param field="Mode3" label="SSH Timeout (s)" width="60px" required="true" default="3"/>

        <param field="Mode4" label="Telegram Bot Token (optional)" width="350px" required="false" default=""/>
        <param field="Mode5" label="Telegram Chat ID (optional)" width="200px" required="false" default=""/>
        <param field="Mode6" label="Telegram Cooldown (s)" width="80px" required="true" default="1800"/>
        <param field="Mode7" label="Check remote Domoticz (0/1)" width="60px" required="true" default="1"/>
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
        self.last_domo_state = None   # None/True/False
        self.last_alert_ts = 0
        self.ssh_check_interval = 60        # z.B. 60s (oder 30/120)
        self.domoticz_check_interval = 65  # z.B. 5 Minuten

        self.next_ssh_check_ts = 0
        self.next_domo_check_ts = 0

        self.auto_restart_domoticz = True
        self.domo_restart_interval = 600   # mindestens 10 Minuten
        self.domo_restart_max = 2           # max. Versuche
        self.domo_restart_count = 0
        self.next_domo_restart_ts = 0

        # Down-Filter (gegen nächtliche Zwangstrennung)
        self.down_since = None
        self.down_alarm_sent = False
        self.down_alarm_threshold = 30  # Sekunden (z.B. 180 = 3 Minuten)

    def onStart(self):
        Domoticz.Log("RaspiWatch: onStart")

        # Domoticz Parameters ist NICHT immer ein dict -> kein .get() verwenden
        def _p(key, default=""):
            try:
                return Parameters[key]
            except Exception:
                return default

        self.host = str(_p("Address", "")).strip()
        self.port = str(_p("Port", "0")).strip()  # unused
        self.user = str(_p("Mode1", "schurgan")).strip()

        try:
            self.retries = int(_p("Mode2", "3"))
        except Exception:
            self.retries = 3

        try:
            self.timeout = int(_p("Mode3", "3"))
        except Exception:
            self.timeout = 3

        # Telegram
        self.tg_token = str(_p("Mode4", "")).strip()
        self.tg_chatid = str(_p("Mode5", "")).strip()

        try:
            self.cooldown = int(_p("Mode6", "1800"))
        except Exception:
            self.cooldown = 1800

        self.check_remote_domoticz = str(_p("Mode7", "1")).strip() == "1"

        if not self.host:
            Domoticz.Error("RaspiWatch: No Address configured.")
            self.enabled = False
            return

        # Device Unit 1: SSH reachable
        if 1 not in Devices:
            Domoticz.Device(Name="Monitored Raspi", Unit=1, TypeName="Switch", Used=1).Create()

        # Device Unit 2: Remote Domoticz running
        if 2 not in Devices:
            Domoticz.Device(Name="Remote Domoticz Running", Unit=2, TypeName="Switch", Used=1).Create()

        # Heartbeat small (Domoticz stability)
        Domoticz.Heartbeat(30)

        Domoticz.Log(
            "RaspiWatch: Monitoring {}@{}, retries={}, timeout={}s, telegram={}".format(
                self.user,
                self.host,
                self.retries,
                self.timeout,
                "on" if (self.tg_token and self.tg_chatid) else "off",
            )
        )

    def onStop(self):
        Domoticz.Log("RaspiWatch: onStop")

    def onHeartbeat(self):
        if not self.enabled:
            return

        if 1 not in Devices:
            return

        now = time.time()

        # Decide whether checks are due
        do_ssh = now >= self.next_ssh_check_ts
        do_domo = now >= self.next_domo_check_ts

        if not do_ssh and not do_domo:
            return

        # Determine current SSH state (ok)
        if do_ssh:
            ok = self._check_ssh()
            self.next_ssh_check_ts = now + self.ssh_check_interval

            # Update Unit 1
            dev1 = Devices[1]
            if ok:
                if dev1.nValue != 1:
                    dev1.Update(nValue=1, sValue="On")
            else:
                if dev1.nValue != 0:
                    dev1.Update(nValue=0, sValue="Off")

            # --- Down-Filter + Telegram (nur wenn wir wirklich neu gecheckt haben) ---
            now_ts = time.time()

            if ok:
                # Reset DOWN tracking
                self.down_since = None
                self.down_alarm_sent = False

                # UP Telegram nur wenn vorher "down" war
                if self.last_state is False:
                    self._maybe_send_telegram(
                        "🟢 WIEDER OK\nMonitored Raspi ({}) ist wieder erreichbar.\nZeit: {}".format(
                            self.host, time.strftime("%d.%m.%Y %H:%M:%S")
                        ),
                        bypass_cooldown=True
                    )
                self.last_state = True

            else:
                # Start/continue DOWN tracking
                if self.down_since is None:
                    self.down_since = now_ts
                    self.down_alarm_sent = False

                down_for = int(now_ts - self.down_since)

                # DOWN Telegram erst nach Threshold und nur einmal
                if (down_for >= self.down_alarm_threshold) and (not self.down_alarm_sent):
                    self._maybe_send_telegram(
                        "🚨 ALARM 🚨\nMonitored Raspi ({}) seit {}s NICHT erreichbar (SSH).\nZeit: {}".format(
                            self.host, down_for, time.strftime("%d.%m.%Y %H:%M:%S")
                        ),
                        bypass_cooldown=True
                    )
                    self.down_alarm_sent = True

                self.last_state = False

        else:
            # No new SSH check -> use current device state
            ok = (Devices[1].nValue == 1)

        # Remote Domoticz check (independent schedule), only if enabled and host is reachable
        if self.check_remote_domoticz and (2 in Devices):
            dev2 = Devices[2]

            if ok and do_domo:
                domo_ok = self._check_remote_domoticz()
                self.next_domo_check_ts = now + self.domoticz_check_interval

                # Update Unit 2 switch
                if domo_ok:
                    if dev2.nValue != 1:
                        dev2.Update(nValue=1, sValue="On")
                else:
                    if dev2.nValue != 0:
                        dev2.Update(nValue=0, sValue="Off")

                # Telegram for Domoticz service transitions
                prev_d = self.last_domo_state
                if prev_d is None:
                    self.last_domo_state = domo_ok
                else:
                    if domo_ok != prev_d:
                        if domo_ok:
                            self._maybe_send_telegram(
                                "🟢 DOMOTICZ OK\nRemote Domoticz auf {} läuft wieder.\nZeit: {}".format(
                                    self.host, time.strftime("%d.%m.%Y %H:%M:%S")
                                ),
                                bypass_cooldown=True,
                            )
                            self.domo_restart_count = 0
                            self.next_domo_restart_ts = 0
                        else:
                            self._maybe_send_telegram(
                                "🚨 DOMOTICZ DOWN 🚨\nRemote Domoticz auf {} läuft NICHT.\nZeit: {}".format(
                                    self.host, time.strftime("%d.%m.%Y %H:%M:%S")
                                ),
                                bypass_cooldown=True,
                            )

                            # Auto-Restart versuchen (begrenzt)
                            now2 = time.time()
                            if self.auto_restart_domoticz:
                                if (self.domo_restart_count < self.domo_restart_max) and (now2 >= self.next_domo_restart_ts):
                                    self._maybe_send_telegram(
                                        "🔄 Neustartversuch Domoticz auf {}\nZeit: {}".format(
                                            self.host, time.strftime("%d.%m.%Y %H:%M:%S")
                                        ),
                                        bypass_cooldown=True,
                                    )
                                    self._restart_remote_domoticz()
                                    self.domo_restart_count += 1
                                    self.next_domo_restart_ts = now2 + self.domo_restart_interval

                        self.last_domo_state = domo_ok

            elif not ok:
                if dev2.nValue != 0:
                    dev2.Update(nValue=0, sValue="Off")
                self.last_domo_state = None
                self.domo_restart_count = 0
                self.next_domo_restart_ts = 0

    # ---------------- internals ----------------

    def _check_remote_domoticz(self) -> bool:
        """
        Prüft auf dem entfernten Raspi via SSH, ob der Domoticz-Dienst läuft (systemd).
        return True  -> domoticz ist active
        return False -> domoticz ist nicht active / Befehl fehlgeschlagen
        """
        cmd = [
            "ssh",
            "-o", "BatchMode=yes",
            "-o", f"ConnectTimeout={self.timeout}",
            "-o", "ConnectionAttempts=1",
            "-o", "ServerAliveInterval=2",
            "-o", "ServerAliveCountMax=1",
            f"{self.user}@{self.host}",
            "systemctl is-active --quiet domoticz"
        ]

        for _ in range(1, self.retries + 1):
            p = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if p.returncode == 0:
                return True
            time.sleep(2)

        return False

    def _restart_remote_domoticz(self):
        cmd = [
            "ssh",
            "-o", "BatchMode=yes",
            "-o", f"ConnectTimeout={self.timeout}",
            "-o", "ConnectionAttempts=1",
            "-o", "ServerAliveInterval=2",
            "-o", "ServerAliveCountMax=1",
            f"{self.user}@{self.host}",
            "sudo systemctl restart domoticz"
        ]

        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

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
