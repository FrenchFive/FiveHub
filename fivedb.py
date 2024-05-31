import os
import sqlite3
import uuid

scrpt_dir = os.path.dirname(os.path.abspath(__file__))
folder_name = 'db/hub.db'
database_path = os.path.join(scrpt_dir, folder_name)

if not os.path.exists(os.path.dirname(database_path)):
    os.makedirs(os.path.dirname(database_path))

CONNECTION = sqlite3.connect(database_path)
CURSOR = CONNECTION.cursor()
CURSOR.execute('''
CREATE TABLE IF NOT EXISTS "ASSET" (
    "id"	TEXT NOT NULL UNIQUE,
    "name"	TEXT,
    "project"	TEXT,
    PRIMARY KEY("id")
);
''')

def add_asset(name, project):
    id = str(uuid.uuid4())
    CURSOR.execute("INSERT INTO ASSET (id, name, project) VALUES (?, ?, ?)", (id, name, project))
    CONNECTION.commit()
    return(id)

def get_projects():
    CURSOR.execute("SELECT DISTINCT project FROM ASSET")
    return CURSOR.fetchall()

def get_assets():
    CURSOR.execute("SELECT * FROM ASSET")
    return CURSOR.fetchall()
