import json
import os
import pandas as pd
import sys

_DIR = os.path.dirname(os.path.abspath(__file__))

_REPO_ROOT = os.path.dirname(_DIR)  # parent of host_computer
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

#from Pi3_Bplus.data_collection_starter import read_waveform_definitions, read_brake_definitions
from utilities.file_access import read_waveform_definitions, read_brake_definitions

def generate_all_runs_init_csv_file():
    parent_folder = os.path.dirname(_DIR)  # one folder above this script file

    dataset_folder = os.path.join(parent_folder, "Pi3_Bplus", "dataset")
    manifests_folder = os.path.join(dataset_folder, "manifests")
    
    if not os.path.exists(manifests_folder):
        os.makedirs(manifests_folder)

    out_filepath = os.path.join(manifests_folder, "all_runs_init.csv")

    in_waveform_folder = os.path.join(parent_folder, "common")
    in_brake_folder = os.path.join(parent_folder, "common")

    waveforms_dict = read_waveform_definitions(in_waveform_folder)
    brake_dict = read_brake_definitions(in_brake_folder)

    # all_runs.csv header columns
    columns = ["run_id", "wave_group", "wave_id", "brake_id"]

    df = pd.DataFrame(columns=columns)

    cur_run_id = 1

    # IMPORTANT: The following assumes the waveform group and wave id are the same in both waveform and brake definitions !!
    for wave_group in waveforms_dict.keys():
        for wave_id in waveforms_dict[wave_group].keys():
            for brake_mode in brake_dict[wave_group][wave_id].keys():
                #"Fail" or "No_Fail"
                for brake_pattern in brake_dict[wave_group][wave_id][brake_mode].keys():
                    #"0, 1, 2, 3, 4" as pattern idx of Fail or No Fail
                    num_repeats = brake_dict[wave_group][wave_id][brake_mode][brake_pattern]["repeat"]  # number of times the pattern needs to be repeated
                    
                    for _ in range(num_repeats):
                        # SAME BRAKE ACTION needs to be repeated in separate runs
                        # as per json file definition.
                        brake_id = f"{brake_mode}-{brake_pattern}"
                        df.loc[len(df)] = [f"{cur_run_id:04d}", wave_group, wave_id, brake_id]
                        cur_run_id += 1

    # Write full run recipe to csv
    df.to_csv(out_filepath, index=False)




if __name__ == "__main__":
    
    generate_all_runs_init_csv_file()  # STEP 1: Generate the all_runs_init.csv file
    #generate_all_run_medatdata_json_files()  # STEP 2: Generate the all_run_medatdata.json files using all_runs_init.csv
