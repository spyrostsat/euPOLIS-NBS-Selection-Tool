import mysql.connector

my_db = mysql.connector.connect(
    host="localhost",
    user="root",
    passwd="spyrosTSAT123!"
)

my_cursor = my_db.cursor()

# my_cursor.execute("CREATE DATABASE mysqlsite")
# my_cursor.execute("DROP DATABASE mysqlsite")

# After I create the database from this script, I have to open the terminal and do db.create_all() to really create the db

my_cursor.execute("SHOW DATABASES")

for db in my_cursor:
    print(db)
