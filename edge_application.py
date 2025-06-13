#!/usr/bin/python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of
# this software and associated documentation files (the "Software"), to deal in
# the Software without restriction, including without limitation the rights to
# use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
# the Software, and to permit persons to whom the Software is furnished to do so.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
# FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
# COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
# IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
import argparse
import logging
import time
import paho.mqtt.client as mqtt
import json
import numpy as np
import turbine
from queue import Queue
import onnxruntime as ort
from datetime import datetime

import pandas as pd
from threading import Thread


# buffer size required to process timeseries data
PREDICTIONS_INTERVAL = 0.1 # interval in seconds between the predictions
MIN_NUM_SAMPLES = 500         
INTERVAL = 5 # seconds
TIME_STEPS = 20 * INTERVAL
STEP = 10
FEATURES_IDX = [6,7,8,5,  3, 2, 4] # qX,qy,qz,qw  ,wind_seed_rps, rps, voltage 
NUM_RAW_FEATURES = 20
NUM_FEATURES = 6

connected = False

q=Queue()
tokens_q = Queue()

inference_log = pd.DataFrame(columns=["timestamp", "event"])


model_loaded = False
model_name = None
model_version = None
model_path = '.'
sess = None

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Connected to broker for raw data acquisition")
        client.connected_flag=True
        client.subscribe('turbine/raw')         
    else:
        print("Connection failed")

def on_message(client, userdata, msg):
    data = msg.payload.decode('utf8')
    try:
        tokens = np.array(data.split(','))
        # check if the format is correct
        if len(tokens) != NUM_RAW_FEATURES:
            print(data)
            logging.error('Wrong # of features. Expected: %d, Got: %d' % ( NUM_RAW_FEATURES, len(tokens)))
            return
        # add noise to raw data randomly
        if np.random.randint(50) == 0:
            print("adding noise to radians")
            tokens[FEATURES_IDX[0:4]] = np.random.rand(4) * 10 # out of the radians range
        if np.random.randint(20) == 0:
            print("adding noise to wind")
            tokens[FEATURES_IDX[5]] = np.random.rand(1)[0] * 10 # out of the normalized wind range
        if np.random.randint(50) == 0:
            print("adding noise to voltage")
            tokens[FEATURES_IDX[6]] = int(np.random.rand(1)[0] * 1000) # out of the normalized voltage range
    except Exception as e:
        logging.error(e)
        logging.error(data)
    ts = "%s+00:00" % datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3]
    tokens_q.put({'ts': ts, 'values': tokens.tolist()})
    # get only the used features
    data = [float(tokens[i]) for i in FEATURES_IDX]
    # compute the euler angles from the quaternion
    roll,pitch,yaw = turbine.euler_from_quaternion(data[0],data[1],data[2],data[3])
    data = np.array([roll,pitch,yaw, data[4], data[5], data[6]])
    
    q.put(data)




#if __name__ == '__main__':
def run_inference(event_queue):
    logging.basicConfig(level=logging.INFO )

    

    # load the json file containing configuration
    iot_params = json.loads(open("config.json", 'r').read())

    # Connect to the broker to acquire simulated data
    logging.info("Connecting to MQTT broker...")
    client = mqtt.Client(iot_params['client_id'])
    client.connected_flag=False
    client.on_connect = on_connect
    client.on_message = on_message
    client.loop_start()
    client.connect(iot_params['broker'], iot_params['port'])
    while not client.connected_flag: #wait in loop
        print("Waiting to connect")
        time.sleep(1)
    logging.info("Connected")
    
    
    def log_event(event):
        inference_log.loc[len(inference_log)] = [datetime.now(), event]
        if event_queue is not None:
            event_queue.put(event)

    ## Initialize the OTA Model Manager
    

   

    def model_update_callback(name, version):
        global model_loaded, model_version, model_name, sess
        if name is not None and version is not None:
            if name is not model_name and model_version is not version:
                model_version=str(version)
                model_name = name
                logging.info('New model deployed: %s - %s' % (name, version))
                if sess is not None:
                    del sess
                sess = ort.InferenceSession(name+".onnx")
            else:
                logging.info("Job update failed - keeping current model running")
            model_loaded = True

    def starting_model_update_callback():
        global model_loaded, sess
        logging.info("Starting a new model update, stopping current inference session")
        
        model_loaded = False

    cloud_connector = turbine.CloudConnector(iot_params, starting_model_update_callback, model_update_callback, model_path)
    
    # Some constants used for data prep + compare the results
    thresholds = np.load('statistics/thresholds.npy')
    raw_std = np.load('statistics/raw_std.npy')
    mean = np.load('statistics/mean.npy')
    std = np.load('statistics/std.npy')
    
    inference_num = 0
    
    try:
        while True:

            cloud_connector.publish_logs(tokens_q.get())

            if not model_loaded:
                logging.info("Waiting for the model...")
                time.sleep(5)
                continue

            if q.qsize() <= MIN_NUM_SAMPLES:
                if q.qsize() % 10 == 0:
                    logging.info('Buffering %d/%d... please wait' % (q.qsize(), MIN_NUM_SAMPLES))
                    time.sleep(1)
                # buffering
                continue
            
            #start_total = time.time()

            # prep the data for the model
            #start_pre = time.time()
            #log_event("preprocessing start")
            inference_num += 1 
            log_event("inference no.{} start".format(inference_num))

            li = list(q.queue)
            data = np.array(li) # create a copy
            q.get() # remove the oldest sample            
            data = np.array([turbine.wavelet_denoise(data[:,i], raw_std[i], 'db6') for i in range(NUM_FEATURES)])
            data = data.transpose((1,0))
            data -= mean
            data /= std
            data = data[-(TIME_STEPS+STEP):]
            #end_pre = time.time()
            #log_event("preprocessing end")


            #start_dataset = time.time()
            #log_event("dataset creation start")
            x = turbine.create_dataset(data, TIME_STEPS, STEP)
            x = np.transpose(x, (0, 2, 1)).reshape(x.shape[0], NUM_FEATURES, 10, 10).astype(np.float32)
            #end_dataset = time.time()
            #log_event("dataset creation end")


            # Now we can run our model using the loaded data
            # The run command lets you specify which outputs you want to get returned. it only has one output.
            
            #start_infer = time.time()
            #log_event("inference start")
            ptemp = sess.run(None, {"input": x})
            #end_infer = time.time()
            #log_event("inference end")


            # We are converting the prediction output to a numpy array so that we can convert it into
            # something human readable
            
            #start_post = time.time()
            #log_event("postprocessing start")
            p = np.asarray(ptemp[0])

            a = x.reshape(x.shape[0], NUM_FEATURES, 100).transpose((0,2,1))
            b = p.reshape(p.shape[0], NUM_FEATURES, 100).transpose((0,2,1))
            
            # check the anomalies
            pred_mae_loss = np.mean(np.abs(b - a), axis=1).transpose((1,0))
            values = np.mean(pred_mae_loss, axis=1)
            anomalies = (values > thresholds)
            
            # publish data to visualize in dashboard
            ts = "%s+00:00" % datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3]
            cloud_connector.publish_inference(anomalies.astype(np.float32), values.astype(np.float32), model_name, model_version, ts)

            if anomalies.any():
                logging.info("Anomaly detected: %s" % anomalies)
            else:
                logging.info("Ok")
            #end_post = time.time()
            #log_event("postprocessing end")
            log_event("inference no.{} end".format(inference_num))

            # 🔍 Log profiling results
            # total_time = time.time() - start_total
            # logging.info(f"Time breakdown (ms): Pre={1000*(end_pre - start_pre):.1f}, "
            #          f"Dataset_creation_reshaping={1000*(end_dataset - start_dataset):.1f}, "
            #          f"Inference={1000*(end_infer - start_infer):.1f}, "
            #          f"Post_processing={1000*(end_post - start_post):.1f}, "
            #          f"Total={1000*total_time:.1f}")

            time.sleep(PREDICTIONS_INTERVAL)
    except KeyboardInterrupt as e:
        pass
    except Exception as e:
        logging.error(e)

    logging.info("Shutting down")
    client.loop_stop()
    client.disconnect()
    cloud_connector.exit("Done")

if __name__ == '__main__':
    run_inference()




