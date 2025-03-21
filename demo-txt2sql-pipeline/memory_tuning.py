import os
import yaml
import lamini
from lamini import Lamini
from helpers import read_jsonl

def load_config(config_path="config.yml"):
    """Load configuration from YAML file"""
    with open(config_path, 'r') as file:
        return yaml.safe_load(file)

def main(config_path="config.yml"):
    config = load_config(config_path)
    
    lamini_api_url = config['api']['url']
    lamini_api_key = config['api']['key']
    
    lamini.api_url = lamini_api_url
    lamini.api_key = lamini_api_key
    
    os.environ["LAMINI_API_URL"] = lamini_api_url
    os.environ["LAMINI_API_KEY"] = lamini_api_key
    
    input_file = input("Enter the path to the input flattened JSONL file: ")
    
    model_name = config['model']['memory_tuning']
    max_steps = config['memory_tuning']['max_steps']
    learning_rate = config['memory_tuning']['learning_rate']
    max_gpus = config['memory_tuning']['max_gpus']
    max_nodes = config['memory_tuning']['max_nodes']
    
    print("Reading data...")
    rows = read_jsonl(input_file)
    print(f"Read {len(rows)} rows")
    
    print("Submitting to Memory Tuning...")
    llm = Lamini(model_name=model_name)
    results = llm.tune(
        data_or_dataset_id=rows,
        finetune_args={
            "max_steps": max_steps,
            "learning_rate": learning_rate,
        },
        gpu_config={
            "max_gpus": max_gpus,
            "max_nodes": max_nodes
        }
    )
    
    print("Memory Tuning submitted successfully!")
    print(f"Results: {results}")
    return results

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Run memory tuning for Text-to-SQL model")
    parser.add_argument("--config", default="config.yml", help="Path to configuration file")
    
    args = parser.parse_args()
    main(args.config)