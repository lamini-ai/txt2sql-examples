import os
import json
import lamini
import pathlib
from typing import List, Dict
from lamini.experiment.error_analysis_concepts import ErrorAnalysis
from lamini.experiment.error_analysis_sql import SQLErrorAnalysis
from lamini.experiment.generators import (
    SchemaToSQLGenerator,
    SQLDebuggerGenerator
)
from lamini.experiment.validators import (
    SQLValidator
)

from helpers import (
    read_jsonl,
    get_schema,
    format_glossary,
    process_variation,
    get_user_input,
    extract_sql, 
    load_config
)

def analyze_topic_coverage(model: str, schema: str, glossary: str, 
                          gold_questions: List[Dict], generated_questions: List[Dict]) -> List:
    """Analyzes topic coverage and generates additional questions for missing topics."""
    error_analysis = ErrorAnalysis(
        model=model,
        schema=schema,
        glossary=glossary
    )
    
    coverage_analysis = error_analysis.analyze_topic_coverage(
        gold_questions=gold_questions,
        generated_questions=generated_questions
    )
    
    additional_questions = []
    if coverage_analysis["missing_topics"] or coverage_analysis["underrepresented_topics"]:
        num_questions = 2  
        additional_questions = error_analysis.generate_additional_questions(
            coverage_analysis=coverage_analysis,
            num_questions_per_topic=num_questions
        )
    
    return additional_questions

def analyze_sql_errors(model: str, results_data: List[Dict], output_path: str) -> None:
    """Analyzes SQL errors and saves analysis to file."""
    sql_error_analysis = SQLErrorAnalysis(model=model)
    
    failed_queries = sql_error_analysis.extract_failed_queries(results_data)
    
    if failed_queries:
        basic_stats = sql_error_analysis.extract_basic_statistics(failed_queries)
        
        analysis = sql_error_analysis.generate_llm_analysis(failed_queries, basic_stats)

        output_data = {
            "failed_queries": failed_queries,
            "basic_stats": basic_stats,
            "llm_analysis": analysis
        }
        with open(output_path, 'w') as f:
            json.dump(output_data, f, indent=2)

def generate_sql_for_questions(questions: List[Dict], model: str, schema: str, glossary: str, 
                              db_path: str, output_path: str) -> None:
    """Generates SQL queries for the given questions and saves them in the requested format."""

    sql_gen = SchemaToSQLGenerator(
        model=model,
        db_type="sqlite",
        db_params=str(db_path),
        schema=schema
    )
    
    sql_validator = SQLValidator(
        model=model,
        db_type="sqlite",
        db_params=str(db_path),
        name="SQLValidator",
        sql_key="sql_query",
        instruction="""
        Query to validate: {sql_query}
        Schema: {schema}
        Glossary: {glossary}
        
        Validate this SQL query against the provided schema.
        """
    )

    sql_debugger = SQLDebuggerGenerator(
        model=model,
        db_type="sqlite",
        db_params=str(db_path),
        schema=schema
    )
    
    simplified_results = []
    
    for i, question_data in enumerate(questions):
        question = question_data["question"]
        covered_topics = question_data.get("covered_topics", [])
        
        print(f"\nProcessing additional question {i+1}/{len(questions)}: {question}")
        
        variation = {
            "question": question,
            "covered_topics": covered_topics
        }
        
        result = process_variation(
            variation,
            None,  
            sql_gen,
            sql_validator,
            sql_debugger,
            schema,
            glossary,
            original_question=question,
            original_sql=None
        )
        
        if result:
            sql = extract_sql(result)
            
            if sql:
                simplified_result = {
                    "input": question,
                    "output": sql
                }
                simplified_results.append(simplified_result)
    
    if output_path and simplified_results:
        with open(output_path, 'w') as f:
            for result in simplified_results:
                f.write(json.dumps(result) + '\n')

def main(config_path="config.yml"):

    config = load_config(config_path)
    
    lamini_api_url = config['api']['url']
    lamini_api_key = config['api']['key']
    
    os.environ["LAMINI_API_URL"] = lamini_api_url
    os.environ["LAMINI_API_KEY"] = lamini_api_key
    
    lamini.api_url = lamini_api_url
    lamini.api_key = lamini_api_key
    
    model = config['model']['default']
    
    output_dir = get_user_input("Enter path to the output directory")
    output_dir = pathlib.Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    db_path = config['database']['path']
    gold_path = config['paths']['gold_test_set']
    glossary_path = config['paths']['glossary']
    
    generated_path = get_user_input("Enter path to flattened generated questions JSONL")
    results_path = get_user_input("Enter path to nested generated questions JSONL")
    
    if not os.path.exists(generated_path):
        print(f"Error: Flattened questions file not found at {generated_path}")
        return
    
    if not os.path.exists(results_path):
        print(f"Error: Nested results file not found at {results_path}")
        return
    
    gold_questions = read_jsonl(gold_path)
    generated_questions = read_jsonl(generated_path)
    glossary_entries = read_jsonl(glossary_path)
    formatted_glossary = format_glossary(glossary_entries)
    schema = get_schema(db_path)
    results_data = read_jsonl(results_path)
    
    sql_error_analysis_path = output_dir / "sql_error_analysis.json"
    additional_questions_with_sql_path = output_dir / "additional_questions_with_sql.jsonl"
    
    print("\nAnalyzing topic coverage...")
    additional_questions = analyze_topic_coverage(
        model=model,
        schema=schema,
        glossary=formatted_glossary,
        gold_questions=gold_questions,
        generated_questions=generated_questions
    )
    
    print("\nAnalyzing SQL errors...")
    analyze_sql_errors(
        model=model,
        results_data=results_data,
        output_path=str(sql_error_analysis_path)
    )
    
    if additional_questions:
        print(f"\nGenerating SQL for {len(additional_questions)} additional questions...")
        generate_sql_for_questions(
            questions=additional_questions,
            model=model,
            schema=schema,
            glossary=formatted_glossary,
            db_path=db_path,
            output_path=str(additional_questions_with_sql_path)
        )
    else:
        print("\nNo additional questions to generate SQL for.")
    
    print(f"\nAnalysis complete. Results saved to: {output_dir}")
    print(f"- SQL error analysis: {sql_error_analysis_path}")
    if additional_questions:
        print(f"- Additional questions with SQL: {additional_questions_with_sql_path}")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Analyze Text-to-SQL data")
    parser.add_argument("--config", default="config.yml", help="Path to configuration file")
    
    args = parser.parse_args()
    main(args.config)