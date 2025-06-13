import csv
from datetime import datetime, timedelta
import pandas as pd
import math
from statistics import stdev


def analyze_inference_csv(filename, power_offset=1.639, output_csv=None):
    inference_powers = {}         # {inference_id: [total_power, count]}
    inference_start_times = {}    # {inference_id: start_timestamp}
    inference_durations = {}      # {inference_id: duration}
    
    current_inference = None

    with open(filename, 'r') as file:
        reader = csv.reader(file)
        header = next(reader)  # skip header

        for row in reader:
            if not row or len(row) < 2:
                continue

            timestamp_str, power_str, *tag_parts = row              # assign row attributes
            tag = tag_parts[0].strip() if tag_parts else ""
            timestamp = datetime.fromisoformat(timestamp_str.strip())
            power = float(power_str.strip())

            real_power = power - power_offset

            if "inference no." in tag:
                tag_info = tag.split("inference no.")[1].strip()
                if "end" in tag_info:                               # intermediate measurement
                    if "end" not in previous_tag_info:              # if first meas. after inference -> log duration of prev. inf
                        duration = timestamp - inference_start_times[previous_inf_id]
                        inference_durations[previous_inf_id] = duration
                    current_inference = None
                else:                                                       
                    try:                                            # inference running measurement
                        inf_id = int(tag_info)
                        current_inference = inf_id
                        if inf_id not in inference_start_times:         #log inf start
                            inference_start_times[inf_id] = timestamp      
                    except ValueError:
                        current_inference = None

                if current_inference is not None:                       #log real power and count of current inf
                    if current_inference not in inference_powers:
                        inference_powers[current_inference] = [0.0, 0]
                    inference_powers[current_inference][0] += real_power
                    inference_powers[current_inference][1] += 1
                   
                previous_tag_info = tag_info
                previous_inf_id = inf_id

    #compute mean power for each inf
    mean_powers = {
        inf_id: total / count
        for inf_id, (total, count) in inference_powers.items()
    }

    #compute overall mean power/inference
    if mean_powers :
        overall_mean_power = sum(mean_powers.values()) / len(mean_powers)
    else:
        overall_mean_power = 0

    #compute mean absolute deviation + standard deviation of mean power/inf
    absdev_list = []
    abs_dev_sum = 0

    for power in mean_powers.values(): 
        absdev_list.append(abs(power-1.639))
    for abs_dev in absdev_list:
        abs_dev_sum = abs_dev_sum + abs_dev
    
    mead = abs_dev_sum/len(mean_powers)

    st_dev = stdev(mean_powers.values(), 1.639)


    #compute mean duration of inference
    if inference_durations:
        total_duration = sum(inference_durations.values(), timedelta())
        mean_inf_duration = total_duration.total_seconds() / len(inference_durations)
    else:
        mean_inf_duration = 0

    #compute mean energy/inference
    mean_epi = overall_mean_power*mean_inf_duration

    #compute performance
    if mean_inf_duration != 0:
        prf = math.floor(1/ mean_inf_duration)
    else:
        prf = 0

    #compute efficiency
    if overall_mean_power!=0:
        ef = prf/overall_mean_power
    else:
        ef = 0

    # save to CSV via pandas df
    results_df = None
    if output_csv:
        data = []
        for inf_id in sorted(inference_powers.keys()):
            total_power, count = inference_powers[inf_id]
            start_ts = inference_start_times.get(inf_id)
            duration = inference_durations.get(inf_id, timedelta(0)).total_seconds()
            data.append({
                "inference_id": inf_id,
                "start_timestamp": start_ts,
                "duration": duration,
                "total_power": total_power,
                "count": count
            })
        results_df = pd.DataFrame(data)
        results_df.to_csv(output_csv, index=False)

    return {
        "mean_power_per_inference": mean_powers,
        "overall_mean_power": overall_mean_power,
        "mead": mead,
        "stdev": st_dev,
        "mean_epi": mean_epi,
        "performance": prf,
        "efficiency": ef,
        # "inference_durations_seconds": {
        #     k: v.total_seconds() for k, v in inference_durations.items()
        # },
        "mean_inf_duration": mean_inf_duration,
        "summary_df": results_df if output_csv else None
    }


if __name__ == "__main__":
    file_path = "tag_conjoined_test1\power_log_2_6_25_18_10.csv" 

    results = analyze_inference_csv(file_path, output_csv="inference_summary_2_6_25_18_10.csv")
    print(f"Overall Mean Power/Inf : {results["overall_mean_power"]:.4f} Watts\n",
          f"MEAD Power/Inf : {results["mead"]:.4f} Watts\n",
          f"Stdev Power/Inf : {results["stdev"]:.4f} Watts\n",
          f"Mean Inference Duration : {results["mean_inf_duration"]:.4f} s\n",
          f"Mean Energy Consumption/Inf : {results["mean_epi"]:.4f} J\n",
          f"Performance : {results["performance"]} inferences/s\n",
          f"Efficiency (Performance per Watt) : {results["efficiency"]} ")

