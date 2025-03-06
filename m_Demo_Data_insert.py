import psycopg2
import os


# Database connection parameters
db_params = {
    'dbname': 'grpr_db',
    'user': os.getenv('POSTGRES_USER'),
    'password': os.getenv('POSTGRES_PASSWORD'), 
    'host': 'localhost',
    'port': '5432'
}

# Connect to the PostgreSQL database
conn = psycopg2.connect(**db_params)
cursor = conn.cursor()

# List of tables to generate INSERT statements for
tables = ['Courses', 'Crews', 'Players', 'Xdates']

# Function to generate INSERT statements
def generate_insert_statements(table_name):
    cursor.execute(f'SELECT * FROM "{table_name}"')
    rows = cursor.fetchall()
    colnames = [desc[0] for desc in cursor.description]

    insert_statements = []
    for row in rows:
        values = ', '.join(["'{}'".format(str(value).replace("'", "''")) if value is not None else 'NULL' for value in row])
        insert_statement = 'INSERT INTO "{}" ({}) VALUES ({});'.format(table_name, ", ".join(colnames), values)
        insert_statements.append(insert_statement)

    return insert_statements

# Generate and save INSERT statements for each table
for table in tables:
    insert_statements = generate_insert_statements(table)
    with open(f'{table}_insert_statements.sql', 'w') as f:
        f.write('\n'.join(insert_statements))

# Close the database connection
cursor.close()
conn.close()

print("INSERT statements generated and saved to files.")