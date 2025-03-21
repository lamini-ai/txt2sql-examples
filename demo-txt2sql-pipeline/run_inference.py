import json
import os
import yaml
import lamini
from lamini import Lamini
from helpers import save_results_to_jsonl, load_config
from lamini.experiment.error_analysis_eval import SQLExecutionPipeline

def read_test_set(file_path):
    """Read the test set file and extract questions and gold queries."""
    test_cases = []
    with open(file_path, 'r') as f:
        for line in f:
            try:
                data = json.loads(line.strip())
                test_cases.append({
                    'question': data['input'],
                    'gold_query': data.get('output', ''),  
                })
            except json.JSONDecodeError as e:
                print(f"Error parsing line: {line}")
                print(f"Error message: {e}")
            except KeyError:
                print(f"Missing required key in line: {line}")
    return test_cases

def run_inference(test_cases, model_id):
    """Run inference for each question and extract SQL query."""
    llm = Lamini(model_name=model_id)
    results = []
    
    for i, test_case in enumerate(test_cases, 1):
        question = test_case['question']
        prompt = f'''<|begin_of_text|><|start_header_id|>user<|end_header_id|> Output only SQL - {question}<|eot_id|><|start_header_id|>assistant<|end_header_id|>'''
        
        try:
            response = llm.generate(prompt)
            test_case['generated_query'] = response
            results.append(test_case)
            
            print(f"Processed question {i}/{len(test_cases)}")
        except Exception as e:
            print(f"Error processing question {i}: {str(e)}")
            test_case['generated_query'] = f"Error: {str(e)}"
            results.append(test_case)
    
    return results

def prepare_for_evaluation(inference_results):
    """Prepare inference results for SQL execution pipeline."""
    test_cases = []
    for result in inference_results:
        if result.get('generated_query', '').startswith('Error:'):
            continue
            
        test_case = {
            'question': result['question'],
            'gold_query': result.get('gold_query', ''),
            'generated_query': result.get('generated_query', '')
        }
        test_cases.append(test_case)
    
    return test_cases

def main(config_path="config.yml"):

    config = load_config(config_path)

    lamini_api_url = config['api']['url']
    lamini_api_key = config['api']['key']
    
    lamini.api_url = lamini_api_url
    lamini.api_key = lamini_api_key
    os.environ["LAMINI_API_URL"] = lamini_api_url
    os.environ["LAMINI_API_KEY"] = lamini_api_key

    test_set_path = config['paths']['gold_test_set']
    db_path = config['database']['path']

    model_id = input("Enter the model ID for inference (this is the output model ID from memory tuning): ")
    
    analysis_model = config['model']['default']
    
    results_dir = input("Enter the output directory to store results: ")
    os.makedirs(results_dir, exist_ok=True)
    
    inference_output_path = os.path.join(results_dir, "inference_results.json")
    analysis_output_path = os.path.join(results_dir, "analysis_results_with_data.json")
    report_output_path = os.path.join(results_dir, "analysis_report.md")
    
    db_connection_params = {
        "db_path": db_path
    }
    
    # Step 1: Read test set
    print("Reading test set...")
    test_cases = read_test_set(test_set_path)
    print(f"Found {len(test_cases)} test cases")
    
    # Step 2: Run inference
    print("Running inference...")
    inference_results = run_inference(test_cases, model_id)
    print("Saving inference results...")
    save_results_to_jsonl(inference_results, inference_output_path)
    
    # Step 3: Prepare for evaluation
    evaluation_test_cases = prepare_for_evaluation(inference_results)
    print(f"Prepared {len(evaluation_test_cases)} test cases for evaluation")
    
    # Step 4: Initialize SQL execution pipeline
    print("Initializing SQL execution pipeline...")
    pipeline = SQLExecutionPipeline(
        model=analysis_model,
        db_type="sqlite",
    )
    
    # Step 5: Run evaluation
    print("Running SQL execution and evaluation...")
    evaluation_results = pipeline.evaluate_queries(
        evaluation_test_cases,
        connection_params=db_connection_params
    )
    
    # Step 6: Save evaluation results
    print("Saving evaluation results with actual query data...")
    save_results_to_jsonl(evaluation_results, analysis_output_path)
    
    # Step 7: Generate and save report
    print("Generating report...")
    report = pipeline.generate_report(evaluation_results)
    with open(report_output_path, 'w') as f:
        f.write(report)
    
    print(f"Done! Results saved to:")
    print(f"- Inference results: {inference_output_path}")
    print(f"- Analysis results with data: {analysis_output_path}")
    print(f"- Analysis report: {report_output_path}")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Run inference and evaluation for Text-to-SQL model")
    parser.add_argument("--config", default="config.yml", help="Path to configuration file")
    
    args = parser.parse_args()
    main(args.config)