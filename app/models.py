import psycopg2
import os

def get_connection():
    print("➡️ Connettendo a:", os.getenv("DATABASE_URL") or os.getenv("DB_HOST"))
    return psycopg2.connect(os.getenv("DATABASE_URL"))

from flask_login import UserMixin

class User(UserMixin):
    def __init__(self, id, username, password_hash, is_admin, role):
        self.id = id
        self.username = username
        self.password_hash = password_hash
        self.is_admin = is_admin
        self.role = role

    @staticmethod
    def get(user_id):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, username, password_hash, is_admin, role FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        return User(*row) if row else None

    @staticmethod
    def find_by_username(username):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, username, password_hash, is_admin, role FROM users WHERE username = %s", (username,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        return User(*row) if row else None

def load_user(user_id):
    return User.get(user_id)


# '''        
# from sqlalchemy import SQLModel, create_engine, select, func, where, Relationship        

# db = create_engine(user, psw, host, database_type, port)        

# class TableName(SQLModel):        
# 	__table__ = True        
# 	column_name: column_type = Field(description='', primary_key=False)        
# 	id: int = Field(primary_key=True)        
# 	other_table: 'OtherTable' = Relationship(OtherTable, other_id)        
# 	        

# _table1 = TableName        
# _table1.column_name = 'something'        
# db.session.add(_table1)        
# db.session.refresh()        
# _other_table = OtherTable(other_column='something', table1_id = _table1.id)        
# db.session.add(_other_table)        
# db.session.commit()        
# username= 'username'        
# query = select(TableName).where(TableName.username == username)        
# result = db.session.execute(query).all(), .scalar_one(), .scalar_one_or_none(), .one()        
# query=select(TableName).where(TableName.column_name==func.max(TableName.id))        
# x = _table1.column_name        
# other_id = _table1.other_table.id        
# 	         