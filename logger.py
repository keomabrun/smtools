# =========================== adjust path =====================================

import sys
import os
import json
import time
from datetime import datetime
import threading

if __name__ == "__main__":
    here = sys.path[0]
    sys.path.insert(0, os.path.join(here, '../', 'smartmeshsdk', 'libs'))

from SmartMeshSDK.utils import JsonManager

# =========================== define ==========================================

MANAGER_PORT = "/dev/ttyUSB3"
LOG_FILE  = "sm.log"

# =========================== main ============================================

lock = threading.RLock()

def main():
    # initialize JsonManager
    jsonManager = JsonManager.JsonManager(
        autoaddmgr      = False,
        autodeletemgr   = False,
        serialport      = MANAGER_PORT,
        notifCb         = notif_cb,
    )

    # create or empty file
    with open(LOG_FILE, 'w') as f:
        pass

    # wait for manager to be connected
    while jsonManager.managerHandlers == {}:
        time.sleep(1)
    while jsonManager.managerHandlers[jsonManager.managerHandlers.keys()[0]].connector is None:
        time.sleep(1)
    time.sleep(1)

    # run snapshot periodically
    while True:
        jsonManager.snapshot_POST(MANAGER_PORT)
        time.sleep(60*60)

def notif_cb(notifName, notifJson):
    with lock:
        # add notif name if not present
        if 'name' not in notifJson:
            notifJson['name'] = notifName

        # add datetime
        if 'datetime' not in notifJson:
            notifJson['datetime'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        else:
            print "datetime already present"

        # write to file
        with open(LOG_FILE, 'a') as f:
            f.write(json.dumps(notifJson) + "\n")

if __name__ == "__main__":
    main()