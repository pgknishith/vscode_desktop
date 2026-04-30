import openai
import sqlite3
import json
import os
from typing import Optional, Dict, Any
from dataclasses import dataclass
import logging
from dotenv import load_dotenv  # For loading .env files (optional)

# Set up logging for professional error handling
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables from .env file (if exists)
load_dotenv()  # This loads .env automatically

# Keep API key out of source control. Use .env or system environment variables.
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Validate API key
def validate_openai_api_key(key: str) -> bool:
    """Validate OpenAI API key format without exposing it."""
    if not key or not key.startswith("sk-"):
        logger.error("Invalid OpenAI API key format. It should start with 'sk-'.")
        return False
    logger.info("OpenAI API key validated successfully (format checked).")
    return True

if not OPENAI_API_KEY:
    raise ValueError(
        "OPENAI_API_KEY not found. "
        "Set it in a .env file or as a system environment variable. "
        "See https://platform.openai.com/docs/api-reference for details."
    )
if not validate_openai_api_key(OPENAI_API_KEY):
    raise ValueError("Invalid OPENAI_API_KEY format from environment.")

# Set OpenAI API key
openai.api_key = OPENAI_API_KEY

@dataclass
class SQLBotConfig:
    """Configuration for the SQL Bot."""
    model: str = "gpt-3.5-turbo"  # Default to accessible model
    fallback_models: list = None  # Fallback GPT-4 models
    temperature: float = 0.1  # Low temperature for deterministic SQL generation
    max_tokens: int = 1000
    database_path: str = "sample.db"  # Path to SQLite database

    def __post_init__(self):
        # Initialize fallback models
        self.fallback_models = ["gpt-4o", "gpt-4-turbo", "gpt-4"]

class AdvancedSQLBot:
    """
    An advanced SQL chatbot powered by OpenAI's GPT models.
    Features:
    - Natural language to SQL query generation with schema awareness.
    - Safe execution with query validation and error handling.
    - Conversational context maintenance for follow-up queries.
    - Advanced features: Query optimization suggestions, data visualization prompts.
    - Professional logging and configurable via dataclass.
    """
    
    def __init__(self, config: SQLBotConfig):
        self.config = config
        self.db_conn = sqlite3.connect(config.database_path)
        self.cursor = self.db_conn.cursor()
        self.conversation_history = []  # Maintains context for multi-turn chats
        self.schema = self._extract_schema()
        logger.info(f"Initialized SQLBot with DB: {config.database_path}")
    
    def _extract_schema(self) -> str:
        """Extract database schema for inclusion in prompts."""
        self.cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in self.cursor.fetchall()]
        
        schema_prompt = "Database Schema:\n"
        for table in tables:
            self.cursor.execute(f"PRAGMA table_info({table});")
            columns = [row[1] for row in self.cursor.fetchall()]
            schema_prompt += f"Table {table}: {', '.join(columns)}\n"
        
        return schema_prompt
    
    def _generate_sql_prompt(self, user_query: str) -> str:
        """Craft a detailed prompt for GPT to generate SQL."""
        base_prompt = f"""
You are an expert SQL engineer. Given a natural language query, generate a valid, efficient SQL query for SQLite.
Use the following database schema: {self.schema}

Rules:
- Always use SELECT for queries unless explicitly asked to modify data (and warn if so).
- Optimize for performance: Use indexes if implied, avoid SELECT *.
- Handle edge cases: NULLs, dates, aggregations.
- If the query is ambiguous, ask for clarification.
- Output ONLY the SQL query in a code block, followed by a brief explanation.

User Query: {user_query}
"""
        
        # Append conversation history for context
        if self.conversation_history:
            history = "\n".join([f"Previous: {h}" for h in self.conversation_history[-3:]])  # Last 3 turns
            base_prompt += f"\nConversation Context: {history}"
        
        return base_prompt
    
    def _validate_and_optimize_sql(self, sql: str) -> Optional[str]:
        """Basic SQL validation and simple optimization."""
        sql_upper = sql.upper()
        forbidden = ["DROP", "DELETE", "UPDATE", "INSERT"]  # Safety: Read-only by default
        if any(f in sql_upper for f in forbidden):
            return None  # Reject modifications
        
        # Simple optimization: Suggest EXPLAIN if complex
        if "JOIN" in sql_upper or "GROUP BY" in sql_upper:
            logger.info("Complex query detected; optimization suggested.")
        
        return sql.strip().rstrip(';')  # Clean up
    
    def validate_input(self, user_query: str, is_advanced: bool = False) -> bool:
        """Validate user input to ensure it's a meaningful query."""
        if not user_query.strip():
            logger.warning("Empty input detected.")
            return False
        if not is_advanced and user_query.strip().isdigit():
            logger.warning(f"Invalid input detected: {user_query}")
            return False
        return True
    
    def generate_sql(self, user_query: str) -> Dict[str, Any]:
        """Generate SQL from natural language using GPT."""
        if not self.validate_input(user_query):
            return {
                "error": "Invalid query. Please provide a meaningful natural language query, e.g., 'How many orders does Alice have?' or 'Show users older than 30.'",
                "sql": None,
                "success": False
            }
        
        prompt = self._generate_sql_prompt(user_query)
        models = [self.config.model] + self.config.fallback_models
        
        for model in models:
            try:
                response = openai.chat.completions.create(
                    model=model,
                    messages=[{"role": "system", "content": prompt}],
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens
                )
                
                full_response = response.choices[0].message.content
                # Extract SQL from code block (assuming ```sql
                if "```sql" in full_response:
                    sql_start = full_response.find("```sql") + 6
                    sql_end = full_response.find("```", sql_start)
                    sql = full_response[sql_start:sql_end].strip()
                    explanation = full_response[sql_end + 3:].strip() if sql_end != -1 else ""
                else:
                    sql = full_response  # Fallback
                    explanation = ""
                
                validated_sql = self._validate_and_optimize_sql(sql)
                if not validated_sql:
                    return {"error": "Query rejected for safety reasons (modifications not allowed).", "sql": None}
                
                return {
                    "sql": validated_sql,
                    "explanation": explanation,
                    "success": True
                }
            
            except Exception as e:
                logger.warning(f"Model {model} failed: {e}")
                if "model_not_found" in str(e).lower():
                    logger.info(f"Model {model} not available, trying next model.")
                    continue
                return {"error": str(e), "sql": None, "success": False}
        
        return {
            "error": "All models failed. Please check your OpenAI account for model access at https://platform.openai.com/docs/models.",
            "sql": None,
            "success": False
        }
    
    def execute_sql(self, sql: str) -> Dict[str, Any]:
        """Execute SQL safely and return results."""
        try:
            self.cursor.execute(sql)
            results = self.cursor.fetchall()
            columns = [desc[0] for desc in self.cursor.description]
            
            # Format results as JSON for easy handling
            formatted_results = []
            for row in results:
                formatted_results.append(dict(zip(columns, row)))
            
            self.db_conn.commit()  # For any non-query ops, but we avoid them
            return {
                "results": formatted_results,
                "columns": columns,
                "row_count": len(results),
                "success": True
            }
        
        except Exception as e:
            logger.error(f"SQL execution error: {e}")
            return {"error": str(e), "success": False}
    
    def chat(self, user_input: str) -> str:
        """Main chat method: Process input, generate SQL, execute, and respond."""
        self.conversation_history.append(f"User: {user_input}")
        
        # Generate SQL
        gen_result = self.generate_sql(user_input)
        if not gen_result["success"]:
            response = f"Error generating SQL: {gen_result['error']}"
            self.conversation_history.append(f"Bot: {response}")
            return response
        
        sql = gen_result["sql"]
        explanation = gen_result["explanation"]
        
        # Execute SQL
        exec_result = self.execute_sql(sql)
        if not exec_result["success"]:
            response = f"Error executing SQL: {exec_result['error']}\nGenerated SQL: {sql}"
        else:
            # Format response
            if exec_result["row_count"] > 0:
                results_str = json.dumps(exec_result["results"], indent=2)
                response = f"Results ({exec_result['row_count']} rows):\n{results_str}\n\nExplanation: {explanation}"
            else:
                response = f"No results returned.\nExplanation: {explanation}"
            
            response += f"\n\nExecuted SQL: ```sql\n{sql}\n```"
        
        self.conversation_history.append(f"Bot: {response}")
        logger.info(f"Chat response generated for: {user_input[:50]}...")
        return response
    
    def advanced_features(self, user_query: str) -> Dict[str, Any]:
        """
        Advanced mode: Includes query optimization, visualization suggestions, and data insights.
        Example usage: bot.advanced_features("Analyze sales trends")
        """
        if not self.validate_input(user_query, is_advanced=True):
            return {
                "error": "Invalid query. Please provide a meaningful analysis query, e.g., 'Analyze sales trends' or 'Summarize order amounts by user.'"
            }
        
        # Extend prompt for advanced analysis
        adv_prompt = self._generate_sql_prompt(user_query) + """
Advanced: Suggest optimizations, potential visualizations (e.g., bar chart), and key insights.
Output in JSON: {"optimized_sql": "...", "visualization": "...", "insights": ["...", "..."]}
"""
        
        models = [self.config.model] + self.config.fallback_models
        
        for model in models:
            try:
                response = openai.chat.completions.create(
                    model=model,
                    messages=[{"role": "system", "content": adv_prompt}],
                    temperature=0.3,  # Slightly higher for creative insights
                    max_tokens=1500
                )
                
                adv_response = response.choices[0].message.content
                parsed = json.loads(adv_response)  # Assume JSON output
                return parsed
            
            except (json.JSONDecodeError, Exception) as e:
                logger.warning(f"Model {model} failed in advanced mode: {e}")
                if "model_not_found" in str(e).lower():
                    logger.info(f"Model {model} not available, trying next model.")
                    continue
                return {"error": str(e)}
        
        return {
            "error": "All models failed. Please check your OpenAI account for model access at https://platform.openai.com/docs/models."
        }
    
    def close(self):
        """Close database connection."""
        self.db_conn.close()
        logger.info("SQLBot connection closed.")

# Sample usage and setup
def setup_sample_database():
    """Create a sample SQLite DB for demo."""
    conn = sqlite3.connect("sample.db")
    cursor = conn.cursor()
    
    # Create tables
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        email TEXT UNIQUE,
        age INTEGER
    );
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY,
        user_id INTEGER,
        product TEXT,
        amount REAL,
        order_date DATE,
        FOREIGN KEY (user_id) REFERENCES users (id)
    );
    """)
    
    # Insert sample data
    cursor.executemany("INSERT OR IGNORE INTO users (id, name, email, age) VALUES (?, ?, ?, ?)",
                       [(1, 'Alice', 'alice@example.com', 30),
                        (2, 'Bob', 'bob@example.com', 25),
                        (3, 'Charlie', 'charlie@example.com', 35)])
    
    cursor.executemany("INSERT OR IGNORE INTO orders (id, user_id, product, amount, order_date) VALUES (?, ?, ?, ?, ?)",
                       [(1, 1, 'Laptop', 999.99, '2023-01-15'),
                        (2, 1, 'Mouse', 29.99, '2023-02-20'),
                        (3, 2, 'Keyboard', 59.99, '2023-03-10'),
                        (4, 3, 'Monitor', 199.99, '2023-04-05')])
    
    conn.commit()
    conn.close()
    print("Sample database created: sample.db")

# Interactive chat loop
def run_interactive_bot():
    """Run the bot in an interactive console mode."""
    setup_sample_database()
    config = SQLBotConfig()
    bot = AdvancedSQLBot(config)
    
    print("Advanced SQL Bot initialized! Type 'quit' to exit, 'advanced <query>' for advanced mode.")
    print("Example: 'How many orders does Alice have?'")
    print("Advanced Example: 'advanced Analyze average order amount by user.'")
    
    while True:
        user_input = input("\nYou: ").strip()
        if user_input.lower() == 'quit':
            break
        if user_input.startswith('advanced '):
            adv_query = user_input[9:].strip()
            result = bot.advanced_features(adv_query)
            print("Bot (Advanced):", json.dumps(result, indent=2))
        else:
            response = bot.chat(user_input)
            print("Bot:", response)
    
    bot.close()

if __name__ == "__main__":
    run_interactive_bot()
