import json
import os
import pandas as pd


_DIR = os.path.dirname(os.path.abspath(__file__))

def generate_all_runs_init_csv_file():
    parent_folder = os.path.dirname(_DIR)  # one above this script file

    dataset_folder = os.path.join(parent_folder, "Pi3_Bplus", "dataset")
    manifests_folder = os.path.join(dataset_folder, "manifests")
    
    if not os.path.exists(manifests_folder):
        os.makedirs(manifests_folder)

    out_filepath = os.path.join(manifests_folder, "all_runs_init.csv")

    in_waveform_filepath = os.path.join(parent_folder, "Pi3_Bplus", "waveform_definitions.json")
    in_brake_filepath = os.path.join(parent_folder, "Pi3_Bplus", "brake_definitions.json")

    with open(in_waveform_filepath, "r", encoding="utf-8") as f:
        waveforms_dict = json.load(f) 

    with open(in_brake_filepath, "r", encoding="utf-8") as f:
        brake_dict = json.load(f)

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
    
    generate_all_runs_init_csv_file()
