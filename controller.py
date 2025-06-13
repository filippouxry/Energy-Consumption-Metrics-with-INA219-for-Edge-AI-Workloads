from threading import Thread
from queue import Queue
from power_monitoring import power_logger, power_df
from edge_application import run_inference, inference_log
from datetime import datetime

if __name__ == '__main__':
    import logging
    logging.basicConfig(level=logging.INFO)
    
    event_queue = Queue()

    try:
        power_thread = Thread(target=power_logger, args=(event_queue,), daemon=True)
        inference_thread = Thread(target=run_inference, args=(event_queue,), daemon=True)
        
        power_thread.start()
        inference_thread.start()

        inference_thread.join()
        power_thread.join()

    finally:
        date = datetime.now()
        event_queue.task_done()
        power_df.to_csv("power_log_{}.csv".format(date), index=False)
        inference_log.to_csv("inference_log_{}.csv".format(date), index=False)
        logging.info("Power log saved.")
        logging.info("Inference log saved.")
        
       

