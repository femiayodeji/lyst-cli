import unittest
from app.llm import extract_sql


class TestExtractSql(unittest.TestCase):
    """Tests for the extract_sql() function."""

    def test_extract_from_sql_code_block(self):
        """Extract SQL from ```sql ... ``` block."""
        response = """Here's the query:

```sql
SELECT COUNT(*) FROM users WHERE EXTRACT(YEAR FROM "createdAt") = 2024
```

This will count users created this year."""
        
        result = extract_sql(response)
        self.assertEqual(result, 'SELECT COUNT(*) FROM users WHERE EXTRACT(YEAR FROM "createdAt") = 2024')

    def test_extract_from_generic_code_block(self):
        """Extract SQL from generic ``` ... ``` block."""
        response = """```
SELECT * FROM orders LIMIT 10
```"""
        
        result = extract_sql(response)
        self.assertEqual(result, "SELECT * FROM orders LIMIT 10")

    def test_raw_sql_starting_with_keyword(self):
        """Return raw SQL if it starts with SQL keyword."""
        response = "SELECT id, name FROM users WHERE active = true"
        
        result = extract_sql(response)
        self.assertEqual(result, "SELECT id, name FROM users WHERE active = true")

    def test_raw_sql_with_with_clause(self):
        """Handle WITH (CTE) queries."""
        response = """WITH active_users AS (
    SELECT * FROM users WHERE active = true
)
SELECT COUNT(*) FROM active_users"""
        
        result = extract_sql(response)
        self.assertIn("WITH active_users AS", result)

    def test_error_message_returned_as_is(self):
        """Non-SQL responses are returned as-is."""
        response = "I cannot answer this question because the 'revenue' table doesn't exist in the schema."
        
        result = extract_sql(response)
        self.assertEqual(result, response)

    def test_empty_string(self):
        """Handle empty strings."""
        result = extract_sql("")
        self.assertEqual(result, "")

    def test_none_input(self):
        """Handle None input."""
        result = extract_sql(None)
        self.assertIsNone(result)

    def test_whitespace_only(self):
        """Handle whitespace-only strings."""
        result = extract_sql("   \n\t  ")
        self.assertEqual(result, "   \n\t  ")

    def test_multiline_sql_in_code_block(self):
        """Extract multiline SQL from code block."""
        response = """```sql
SELECT 
    u.id,
    u.name,
    COUNT(o.id) as order_count
FROM users u
LEFT JOIN orders o ON u.id = o.user_id
GROUP BY u.id, u.name
ORDER BY order_count DESC
LIMIT 10
```"""
        
        result = extract_sql(response)
        self.assertIn("SELECT", result)
        self.assertIn("LEFT JOIN orders", result)
        self.assertIn("LIMIT 10", result)

    def test_multiple_code_blocks_takes_first_sql(self):
        """When multiple code blocks exist, extract from first sql block."""
        response = """First query:
```sql
SELECT * FROM users
```

Second query:
```sql
SELECT * FROM orders
```"""
        
        result = extract_sql(response)
        self.assertEqual(result, "SELECT * FROM users")

    def test_sql_with_quoted_identifiers(self):
        """Handle SQL with quoted identifiers (PostgreSQL style)."""
        response = '''```sql
SELECT "userId", "createdAt" FROM "UserAccounts" WHERE "isActive" = true
```'''
        
        result = extract_sql(response)
        self.assertIn('"userId"', result)
        self.assertIn('"createdAt"', result)

    def test_sql_with_backtick_identifiers(self):
        """Handle SQL with backtick identifiers (MySQL style)."""
        response = """```sql
SELECT `user_id`, `created_at` FROM `user_accounts` WHERE `is_active` = 1
```"""
        
        result = extract_sql(response)
        self.assertIn("`user_id`", result)

    def test_delete_statement(self):
        """Handle DELETE statements."""
        response = "DELETE FROM sessions WHERE expires_at < NOW()"
        
        result = extract_sql(response)
        self.assertIn("DELETE FROM sessions", result)

    def test_update_statement(self):
        """Handle UPDATE statements."""
        response = """```sql
UPDATE users SET last_login = NOW() WHERE id = 123
```"""
        
        result = extract_sql(response)
        self.assertIn("UPDATE users", result)

    def test_insert_statement(self):
        """Handle INSERT statements."""
        response = "INSERT INTO logs (message, level) VALUES ('test', 'info')"
        
        result = extract_sql(response)
        self.assertIn("INSERT INTO logs", result)


if __name__ == "__main__":
    unittest.main()
