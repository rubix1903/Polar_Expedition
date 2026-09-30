#Creates the tables and loads the sample data into the database named by DATABASE_URL.
from contextlib import closing

from . import db, seed

def main():
    with closing(db.connect()) as conn:
        db.create_schema(conn)
        conn.commit()
        print("Sample data loaded" if seed.load(conn) else "Database already has data, nothing changed")
        conn.commit()

if __name__ == "__main__":
    main()
