Energy Consumption Metrics with INA219 for Edge-AI Workloads

Short functionality description:

- edge_application.py : the main script, responsible for connecting to the cloud, inferencing and reporting back (for more see: https://github.com/aws-samples/ml-edge-getting-started/tree/main/samples/onnx_accelerator_sample1), 
added log_event(event) function to push events (inference start / end) to shared queue with power_monitoring thread
- power_monitoring.py : initializes INA219 sensor bus for communication via i2c, continuously updates pandas dataframe with measurements along with event tags 
- controller.py : initializes edge_application and power_monitoring threads, when interrupted saves the power log to .csv 

