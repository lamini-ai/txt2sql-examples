import os
import lamini
import pathlib
import datetime

from lamini.experiment.generators import (
    SchemaToSQLGenerator,
    SQLDebuggerGenerator,
    PatternQuestionGenerator,
    VariationQuestionGenerator,
    QuestionDecomposerGenerator
)
from lamini.experiment.validators import (
    SQLValidator
)

from helpers import (
    load_config,
    process_jsonl,
    read_jsonl, 
    get_schema, 
    format_glossary, 
    save_results, 
    generate_variations,
    process_variation
)

def main(config_path="config.yml"):
    config = load_config(config_path)

    lamini_api_url = config['api']['url']
    lamini_api_key = config['api']['key']
    
    lamini.api_url = lamini_api_url
    lamini.api_key = lamini_api_key
    
    os.environ["LAMINI_API_URL"] = lamini_api_url
    os.environ["LAMINI_API_KEY"] = lamini_api_key
    
    db_path = config['database']['path']
    eval_path = config['paths']['gold_test_set']
    glossary_path = config['paths']['glossary']

    model = config['model'].get('default')
 
    script_dir = pathlib.Path(os.path.dirname(os.path.abspath(__file__)))
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = script_dir / f"results_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Results will be saved to: {output_dir}")

    default_output_filename = f"nested_results_{timestamp}.jsonl"
    output_file = default_output_filename
    flattened_filename = f"flattened_{timestamp}.jsonl"
    
    output_paths = {
        "combined": output_dir / output_file,
        "flattened": output_dir / flattened_filename
    }
    
    schema = get_schema(db_path)
    print(schema)
    
    eval_questions = read_jsonl(eval_path)
    print(f"Loaded {len(eval_questions)} evaluation questions")
    
    glossary_entries = read_jsonl(glossary_path)
    formatted_glossary = format_glossary(glossary_entries)
    print(f"Loaded glossary with {len(glossary_entries)} entries")
    
    generators = {
        "pattern": PatternQuestionGenerator(model=model),
        "variation": VariationQuestionGenerator(model=model),
        "decomposer": QuestionDecomposerGenerator(model=model)
    }
    
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
    
    all_results = []
    
    for eval_data in eval_questions:
        eval_question = eval_data["input"]
        eval_sql = eval_data["output"]
        
        print(f"\nProcessing question: {eval_question}")

        result = {
            "original_question": eval_question,
            "original_sql": eval_sql,
            "pattern_variations": [],
            "structural_variations": [],
            "sub_questions": []
        }

        base_prompt_data = {
            "question": eval_question,
            "sql": eval_sql,
            "schema": schema,
            "glossary": formatted_glossary
        }

        # 1. Generate Pattern-based Questions
        print("Generating pattern variations...")
        pattern_variations = generate_variations(
            generators["pattern"], 
            base_prompt_data, 
            "variations"
        )
        
        for variation in pattern_variations:
            variation_result = process_variation(
                variation, 
                generators["pattern"],
                sql_gen, 
                sql_validator, 
                sql_debugger, 
                schema, 
                formatted_glossary,
                original_question=eval_question,  
                original_sql=eval_sql  
            )
            if variation_result:
                result["pattern_variations"].append(variation_result)

        # 2. Generate Structural Variations
        print("\nGenerating structural variations...")
        structural_variations = generate_variations(
            generators["variation"], 
            base_prompt_data, 
            "variations"
        )
        
        for variation in structural_variations:
            variation_result = process_variation(
                variation, 
                generators["variation"],
                sql_gen, 
                sql_validator, 
                sql_debugger, 
                schema, 
                formatted_glossary,
                original_question=eval_question,  
                original_sql=eval_sql 
            )
            if variation_result:
                result["structural_variations"].append(variation_result)

        # 3. Generate Decompositions
        print("\nGenerating decompositions...")
        sub_questions = generate_variations(
            generators["decomposer"], 
            base_prompt_data, 
            "sub_questions"
        )
        
        for sub_q in sub_questions:
            sub_q_result = process_variation(
                sub_q, 
                generators["decomposer"],
                sql_gen, 
                sql_validator, 
                sql_debugger, 
                schema, 
                formatted_glossary,
                is_subq=True,
                original_question=eval_question,  
                original_sql=eval_sql 
            )
            if sub_q_result:
                result["sub_questions"].append(sub_q_result)
        
        all_results.append(result)
        save_results([result], output_paths["combined"])
        
        print(f"\nResults for question: {eval_question}")
        print(f"Generated {len(result['pattern_variations'])} pattern variations")
        print(f"Generated {len(result['structural_variations'])} structural variations")
        print(f"Generated {len(result['sub_questions'])} sub-questions")
        print("-" * 80)
    
    print("\nCreating flattened results file...")
    flattened_results = process_jsonl(str(output_paths["combined"]), str(output_paths["flattened"]))
    print(f"Flattened {len(flattened_results)} question-SQL pairs")
    
    print("\nProcessing complete!")
    print(f"Results have been saved to:")
    for key, path in output_paths.items():
        print(f"- {key}: {path}")
    
    return all_results

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate data for Text-to-SQL model training")
    parser.add_argument("--config", default="config.yml", help="Path to configuration file")
    
    args = parser.parse_args()
    main(args.config)