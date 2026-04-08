import json

if __name__ == "__main__":
    
    with open("./Pi3_Bplus/waveform_definitions.json", "r", encoding="utf-8") as f:
        waveform_defs = json.load(f)

    with open("./Pi3_Bplus/brake_definitions.json", "r", encoding="utf-8") as f:
        brake_defs = json.load(f)

    print(f"Waveform Definitions: {waveform_defs}")
    print(f"Brake Definitions: {brake_defs}")
