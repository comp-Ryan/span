import json
import psycopg
from psycopg.rows import dict_row
from owed.config import settings
from owed.finance.model import train

if __name__ == "__main__":
    with psycopg.connect(settings.database_url, row_factory=dict_row) as con:
        m = train(con)
    print(json.dumps(m.metrics, indent=2))
