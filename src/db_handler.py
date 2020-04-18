import random
import string
import json
from datetime import datetime
from sqlalchemy import create_engine
import pandas as pd

CRED_FILE = 'src/credentials.json'

def generate_url(n):
    chat_id = ['']
    while len(chat_id) > 0:
        url = ''.join(random.choices(string.ascii_uppercase + string.digits, k=n))
        chat_id = get_chat_id(url)
    return url

def get_engine():
    with open(CRED_FILE) as f:
        cred = json.load(f)
    engine = create_engine('postgresql+psycopg2://{}:{}@{}:{}/{}'.format(cred['user'], cred['pass'], cred['host'], cred['port'], cred['db']))
    return engine

def get_df(sql):
    db_engine = get_engine()
    df = pd.read_sql(sql, db_engine)
    return df

def execute(sql, params=None, result_back=True):
    db_engine = get_engine()
    with db_engine.connect() as con:
        if params:
            res = con.execute(sql, params)
        else:
            res = con.execute(sql)
        if result_back:
            res = [i for i in res]
    return res

def get_emoji():
    return get_df("select * from emoji;")

def get_chat_id(url):
    return execute("select id from uploaded where url=%s;", (url))

def get_chat(url):
    chat_id = get_chat_id(url)
    if len(chat_id) > 0:
        return get_df(f'select * from chat where id_chat={chat_id[0][0]};')
    else:
        return pd.DataFrame()

def add_chat(df, url):
    sql = "insert into uploaded (datetime, url) values (%s, %s) returning id;"
    id_chat = execute(sql, (datetime.now(), url))[0][0]
    df.insert(0, 'id_chat', id_chat)
    db_engine = get_engine()
    df.to_sql('chat', db_engine, if_exists='append')
    return url

def reset_chat():
    sql_script = [
        "drop table if exists uploaded;",
        "drop table if exists chat;",
        "create table uploaded (id serial primary key, datetime timestamp, url varchar);"]
    for sql in sql_script:
        execute(sql, result_back=False)