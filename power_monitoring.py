import pandas as pd
import time
from datetime import datetime
from adafruit_ina219 import INA219
import board
import logging

power_df = pd.DataFrame(columns=["timestamp", "power", "tag"])

def power_logger(event_queue):
    i2c_bus = board.I2C()  # uses board.SCL and board.SDA
    ina219 = INA219(i2c_bus)
    ina219.set_calibration_16V_2_5A()
    
    current_tag = None
    
    while True:
        delimiter = " "
        while not event_queue.empty():
            try:
                event = event_queue.get_nowait()
                if event.endswith("start"):
                    current_tag = delimiter.join(event.split()[:-1])
                else:
                    current_tag = event
            except Exception:
                pass
        power = ina219.power
        power_to_df = "{:6.3f}".format(power)
        ts = datetime.now()
        power_df.loc[len(power_df)] = [ts, power_to_df, current_tag]
        
            #time.sleep(2)
        #except:
        #    power_df.to_csv("idle_power_log_{}.csv".format(datetime.now()), index=False)
        #    logging.info("Power log saved.")
        #    break

if __name__ == '__main__':
    power_logger()


