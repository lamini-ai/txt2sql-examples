import os
import yaml
import json
import sqlite3

from lamini.generation.base_prompt_object import PromptObject

def read_jsonl(file_path):
    """Read JSONL file and return list of JSON objects."""
    data = []
    with open(file_path, 'r') as f:
        for line in f:
            if line.strip():
                data.append(json.loads(line))
    return data

def get_schema(db_path):
    """Get schema for all tables from SQLite database with error handling."""
    try:
        if not os.path.exists(db_path):
            print(f"Database file not found at: {db_path}")
            return ""
            
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get all table names
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
        tables = cursor.fetchall()
        print("Tables found in database:", tables)
        
        if not tables:
            print("No tables found in the database")
            return ""
        
        # Build complete schema for all tables
        full_schema = []
        for table in tables:
            table_name = table[0]
            cursor.execute(f"PRAGMA table_info({table_name});")
            columns = cursor.fetchall()
            
            # Format the table schema
            columns_info = [f"{col[1]} {col[2]}" for col in columns]
            table_schema = f"CREATE TABLE {table_name} (\n  " + ",\n  ".join(columns_info) + "\n);"
            full_schema.append(table_schema)
        
        conn.close()
        return "\n\n".join(full_schema)
        
    except sqlite3.Error as e:
        print(f"SQLite error occurred: {e}")
        return ""
    except Exception as e:
        print(f"An error occurred: {e}")
        return ""

def format_glossary(glossary_entries):
    """Format glossary entries into a readable string."""
    formatted = []
    for entry in glossary_entries:
        formatted.append(f"{entry['key']}: {entry['value']}")
    return "\n".join(formatted)

def save_results_to_jsonl(data, output_path):
    """Save results to a JSONL file - handles both lists and dictionaries."""
    try:
        if isinstance(data, list):
            print(f"Saving list data with {len(data)} items")
            with open(output_path, 'w') as f:
                json.dump(data, f, indent=2)
        else:
            print(f"Saving dictionary data with keys: {list(data.keys())}")
            with open(output_path, 'w') as f:
                json.dump(data, f, indent=2)
        print(f"Successfully saved data to {output_path}")
    except Exception as e:
        print(f"Error saving data: {str(e)}")
        print(f"Data type: {type(data)}")

def save_results(results, output_path, append=True):
    mode = 'a' if append else 'w'
    with open(output_path, mode) as f:
        for result in results:
            f.write(json.dumps(result) + '\n')
            
def process_variation(variation, generator, sql_gen, sql_validator, sql_debugger, schema, glossary, is_subq=False, original_question=None, original_sql=None):
    """
    Process a single variation through the pipeline: SQL generation, validation, and debugging.
    """
    # Extract the question text based on whether it's a subquestion or not
    question_key = "sub_question" if is_subq else "question"
    
    if isinstance(variation, str):
        question_text = variation
    elif hasattr(variation, 'data') and isinstance(variation.data, dict):  
        question_text = variation.data.get(question_key, "")
    elif hasattr(variation, 'get'):  
        question_text = variation.get(question_key, "")
    else:
        question_text = ""
    
    if not question_text:
        return None
    
    print(f"Processing {'sub-question' if is_subq else 'variation'}: {question_text}")
    
    # Generate SQL for the variation
    sql_prompt = PromptObject("", data={
        "question": question_text,  
        "sub_question": question_text, 
        "schema": schema,
        "glossary": glossary,
        "original_question": original_question, 
        "original_sql": original_sql 
    })
    
    sql_result = sql_gen(sql_prompt)
    if not sql_result or "sql_query" not in sql_result.response:
        return None
    
    # Create result object
    result = {
        question_key: question_text,
        "generated_sql": sql_result.response["sql_query"]
    }
    
    # Validate SQL
    validation_prompt = PromptObject("", data={
        "sql_query": result["generated_sql"],
        "schema": schema,
        "glossary": glossary
    })
    validation_result = sql_validator(validation_prompt)
    
    if validation_result and validation_result.response:
        if not validation_result.response.get("is_valid", False):
            # Debug invalid SQL
            debug_prompt = PromptObject("", data={
                "error_message": validation_result.response.get("error", ""),
                "error_explanation": validation_result.response.get("explanation", ""),
                "error_sql": result["generated_sql"],
                "sub_question": question_text,
                "schema": schema,
                "glossary": glossary
            })
            
            debug_result = sql_debugger(debug_prompt)
            if debug_result and debug_result.response and "corrected_sql" in debug_result.response:
                result["corrected_sql"] = debug_result.response["corrected_sql"]
                
                # Validate corrected SQL
                corrected_validation = sql_validator(PromptObject("", data={
                    "sql_query": debug_result.response["corrected_sql"],
                    "schema": schema,
                    "glossary": glossary
                }))
                result["final_validation"] = corrected_validation.response
            else:
                result["validation"] = validation_result.response
        else:
            result["validation"] = validation_result.response
            result['generated_sql'] = validation_result.data['sql_query']
    
    return result

def generate_variations(generator, prompt_data, result_key):
    """
    Generate variations using the specified generator
    """
    from lamini.generation.base_prompt_object import PromptObject
    
    prompt = PromptObject("", data=prompt_data)
    result = generator(prompt)
    
    if not result:
        print(f"Warning: Generator returned None or empty result")
        return []
        
    if hasattr(result, 'response') and isinstance(result.response, dict):
        # Get the list of variations from the response using the result_key
        variations = result.response.get(result_key, [])
        print(f"Generated {len(variations)} {result_key}")
        return variations
    
    print(f"Warning: Unexpected result format: {type(result)}")
    return []

def extract_sql(variation):
    """Extract the correct SQL based on validation status."""
    if 'corrected_sql' in variation and 'final_validation' in variation:
        if variation['final_validation'].get('is_valid', True):
            return variation['corrected_sql']
        return None  
    
    if 'generated_sql' in variation:
        if 'validation' in variation:
            if variation['validation'].get('is_valid', True):
                return variation['generated_sql']
            return None  
        return variation['generated_sql']
        
    return None

def process_jsonl(input_file, output_file=None, input_key="input", output_key="output"):
    """Process JSONL file and create flattened JSONL output with just question and SQL."""
    rows = []
    
    with open(input_file, 'r') as file:
        for line in file:
            try:
                data = json.loads(line.strip())
                for var in data['pattern_variations']:
                    if 'question' in var:
                        sql = extract_sql(var)
                        if sql:  
                            rows.append({
                                input_key: var['question'],
                                output_key: sql
                            })
                for var in data['structural_variations']:
                    if 'question' in var:
                        sql = extract_sql(var)
                        if sql:  
                            rows.append({
                                input_key: var['question'],
                                output_key: sql
                            })
                for q in data['sub_questions']:
                    if 'sub_question' in q:
                        sql = extract_sql(q)
                        if sql: 
                            rows.append({
                                input_key: q['sub_question'],
                                output_key: sql
                            })
            except json.JSONDecodeError as e:
                print(f"Error parsing JSON line: {e}")
            except Exception as e:
                print(f"Error processing line: {e}")

    if output_file:
        with open(output_file, 'w') as file:
            for row in rows:
                json.dump(row, file)
                file.write('\n')

    print(f"Total rows processed: {len(rows)}")
    return rows

def jsonl_to_string(jsonl_file, input_key="input", output_key="output"):
    """Format JSONL file, e.g. glossary, into a readable string."""
    rows = read_jsonl(jsonl_file)
    formatted = []
    for row in rows:
        formatted.append(f"{row[input_key]}: {row[output_key]}")
    return "\n".join(formatted)

def get_user_input(prompt, default=None):
    if default:
        user_input = input(f"{prompt} [default: {default}]: ")
        return user_input if user_input.strip() else default
    else:
        return input(f"{prompt}: ")
    
def load_config(config_path="config.yml"):
    """Load configuration from YAML file"""
    with open(config_path, 'r') as file:
        return yaml.safe_load(file)