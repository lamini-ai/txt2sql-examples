# Text-to-SQL Memory Experiment

This repository demonstrates how to build a text-to-SQL system using Lamini's Memory Experiment framework. The system generates training data, fine-tunes a language model, and evaluates its performance at converting natural language questions to SQL queries for a bakery database.

## Overview

This repository provides a complete pipeline for creating a custom text-to-SQL model that understands domain-specific terminology and database structure.

The pipeline includes:

1. **Data Generation**: Create diverse training examples from a small set of sample questions
2. **Data Validation**: Ensure generated SQL queries are valid and executable
3. **Coverage Analysis**: Identify and fill gaps in SQL concept coverage
4. **Memory Tuning**: Fine-tune a language model on the generated data
5. **Performance Evaluation**: Test the model against a held-out evaluation set

## Bakery Dataset

This example uses the Bakery dataset from the Spider benchmark collection. The dataset contains information about sales for a small bakery shop, with the following structure:

### Database Schema

The database consists of four tables:

#### customers
- `Id`: Unique customer identifier
- `LastName`: Customer's last name
- `FirstName`: Customer's first name

#### goods
- `Id`: Unique identifier of the baked good
- `Flavor`: Flavor/type (e.g., "chocolate", "lemon")
- `Food`: Category (e.g., "cake", "tart")
- `Price`: Price in dollars

#### items
- `Reciept`: Receipt number (foreign key to receipts.RecieptNumber)
- `Ordinal`: Position of the purchased item on the receipt
- `Item`: Identifier of the item purchased (foreign key to goods.Id)

#### receipts
- `RecieptNumber`: Unique identifier of the receipt
- `Date`: Date of purchase (DD-Mon-YYYY format)
- `CustomerId`: Customer ID (foreign key to customers.Id)

### Sample Questions

Example natural language questions for this database:
- "What is the average price of chocolate cakes?"
- "Which customer made the most purchases in January?"
- "List all flavors of tarts available in the bakery"
- "How many different items did customer with ID 15 purchase?"

## Getting Started

### Prerequisites

- Python 3.7+
- Lamini API key (get yours at [app.lamini.ai](https://app.lamini.ai))
- SQLite database with the bakery schema

### Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/lamini-ai/txt2sql-examples.git
   cd txt2sql-examples
   ```

2. Install required packages:
   ```bash
   pip install lamini
   ```

3. Fill the `config.yml` file 


## Pipeline Components

The repository contains the following core scripts:

### generate_data.py
Generates training questions and their corresponding SQL queries based on your evaluation set.

### analyze_generated_data.py
Analyzes concept coverage and generates additional questions for missing SQL concepts. This step is optional but recommended for comprehensive coverage.

### memory_tuning.py
Fine-tunes a language model on the generated data using Lamini's Memory Tuning feature.

### run_inference.py
Evaluates the fine-tuned model by comparing generated queries against gold standard queries.

### helpers.py
Contains utility functions used across scripts:
- Reading and writing JSONL files
- Getting user input with default values
- Formatting database schema and glossary
- Processing variations and saving results

## Usage

### 1. Prepare Your Glossary

Create a glossary file that defines domain-specific terms and provides additional context about the database

### 2. Create Evaluation Set

Prepare an evaluation set with example questions and their corresponding SQL queries

### 3. Run the Pipeline

#### Generate Training Data

```bash
python generate_data.py
```

This script:
- Takes a test set of questions and their corresponding SQL queries
- Generates pattern-based variations of questions (similar questions with different patterns)
- Creates structural variations (questions with different structures but similar intent)
- Decomposes complex questions into simpler sub-questions
- Ensures all generated variations include their corresponding SQL queries
- Outputs two files: 
  - flattened.jsonl (only the question and query pairs)
  - nested_results.jsonl (detailed information including question, query, validation status, original question, and original query)

#### Analyze Coverage and Generate Additional Data

```bash
python analyze_generated_data.py
```

This script (optional but recommended):
- Takes the flattened.jsonl and nested_results.jsonl as input
- Identifies SQL concepts not covered in the generated data
- Generates 2 additional questions for each missing concept
- Validates the SQL queries and passes them through a debugger if needed
- Collects all failed queries from both stages for analysis
- Provides a detailed analysis of why certain queries failed
- Outputs additional_questions.jsonl for enhancing your training data

Note: This step may take a few minutes to complete and can be skipped if time-constrained.

#### Fine-tune a Model

```bash
python memory_tuning.py
```

This script:
- Takes the flattened JSONL file of question-SQL pairs
- Configures training parameters like max_steps, learning_rate, etc.
- Submits the tuning job to Lamini's API
- Displays the tuning job information

Important: After the job completes, you'll need to get the model ID from the Lamini app environment for the next step.

#### Evaluate the Model

```bash
python run_inference.py
```

This script:
- Reads test questions from your evaluation JSONL file
- Runs inference using your fine-tuned model to generate SQL queries
- Executes both the generated queries and gold standard queries
- Compares the results to determine functional equivalence
- Generates a detailed performance report with metrics and error analysis
- Produces three output files:
  - inference_results.json: Raw inference outputs
  - analysis_results_with_data.json: Detailed comparison data
  - analysis_report.md: Human-readable performance summary

## Input Requirements

To use this pipeline, you'll need to prepare:

1. **Database**: SQLite database with the bakery schema
2. **Test/Evaluation Set**: JSONL file with example questions and their gold SQL queries
3. **Glossary**: JSONL file with term definitions to help the model understand domain-specific terminology

## Output Files

Running the pipeline will generate:

1. **Nested Results**: Generated questions and SQL stored in a JSONL file along with the original questions, SQL queries, and validation information
2. **Flattened Results**: Generated questions and SQL pairs in a simpler JSONL format for training
3. **Tuned Model**: A model ID returned by Lamini's API that can be used for inference
4. **Evaluation Results**: JSON file with detailed comparison of generated queries vs. gold standard
5. **Analysis Report**: Markdown report summarizing the model's performance
