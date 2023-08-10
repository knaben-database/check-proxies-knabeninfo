import re

import psycopg2
from collections import namedtuple

import settings


def create_record(obj, fields):
    ''' given obj from db returns named tuple with fields mapped to values '''
    Record = namedtuple("Record", fields)
    mappings = dict(zip(fields, obj))
    return Record(**mappings)


class Postgresql:
    up = False
    ms = 0

    __ms_range = {
        "min": 100,
        "max": 5000,
        "down": 15000
    }

    __con_string = settings.psql_con
    __cur = None
    __con = None

    def __init__(self):
        try:
            self.__con = psycopg2.connect(
                "host='" + self.__con_string["host"] + "' port='" + str(self.__con_string["port"]) + "' dbname='" +
                self.__con_string["db"] + "' user='" +
                self.__con_string["user"] + "' password='" + self.__con_string["pass"] + "'")
            self.__cur = self.__con.cursor()
        except psycopg2.OperationalError as e:
            self.up = False
            print("Failed to connect to psql db because:", e)
            return
        self.up = True

    def update(self, sql, force_no_where=False):
        """
        This function updates data given a where statement.
        The where statement only supports equal condition comparison. If multiple statements are added, it will use the AND operator.
        :param sql: requires a structure like so {"table": "table_name", "where": {"key": "value"}, "row": {"index": data, "index2": data2}}
        :param force_no_where: true on this if you're crazy
        :return: A list or a single string of generated keys, based on "returning" defined in insert options
        """
        if "where" not in sql and not force_no_where:
            Exception("wtf no where statement")
            return

        # query = "UPDATE items SET info = %s, city = %s, price = %s WHERE id = %s;"
        data = {}
        query = "UPDATE " + sql["table"] + " SET "
        for column in sql["row"].keys():
            query += column + " = %("+column+")s, "
            data[column] = sql["row"][column]
        query = query[:-2]
        if not force_no_where:
            query += " WHERE "
            c = 0
            for column in sql["where"].keys():
                if c > 0:
                    query += " AND "
                query += column + " = %(" + column + ")s"
                c += 1
                data[column] = sql["where"][column]

        try:
            self.__cur.execute(query, data)
        except Exception as e:
            self.__con.rollback()
            print("ERROR: ", e)
            print("Query: ", query)
            print("Data:  ", data)
            return
        rowcount = self.__cur.rowcount
        if rowcount > 0:
            print(str(rowcount) + " rows affected in table: " + sql["table"])
        self.__con.commit()



    def insert(self, sql, refresh_sequence=False):
        """
        This function inserts data into a table
        :param sql: requires a structure like so {"table": "table_name", "returning": ["column", "column2"], "row": {"index": data, "index2": data2}}
        :param refresh_sequence: if the sequence should be reset
        :return: A list or a single string of generated keys, based on "returning" defined in insert options
        """
        returning = []

        # query = "INSERT INTO items (info, city, price) VALUES (%s, %s, %s);"
        query = "INSERT INTO " + sql["table"] + " ("
        for column in sql["row"].keys():
            query += column + ", "
        if "raw" in sql:
            for column in sql["raw"].keys():
                query += column + ", "
        query = query[:-2] + ") VALUES ("
        for column in sql["row"].keys():
            query += "%s, "
        if "raw" in sql:
            for column in sql["raw"].keys():
                query += sql["raw"][column] + ", "
        query = query[:-2] + ")"

        # Skip duplicates
        query += " ON CONFLICT DO NOTHING"

        if "returning" in sql:
            if type(sql["returning"]) == list:
                query += " RETURNING " + ", ".join(sql["returning"])
            if type(sql["returning"]) == str:
                query += " RETURNING " + sql["returning"]

        data = list(sql["row"].values())
        try:
            self.__cur.execute(query, data)
        except psycopg2.errors.ForeignKeyViolation as e:
            self.__con.rollback()
            raise e
        rowcount = self.__cur.rowcount
        if rowcount > 0:
            print(str(rowcount) + " rows affected in table: " + sql["table"])
        if "returning" in sql:
            if type(sql["returning"]) == list:
                returning = self.__cur.fetchone()
            if type(sql["returning"]) == str:
                value = self.__cur.fetchone()
                if value is None:  # Probably no row was inserted, and we now have to grab it instead
                    pks = self.get_pks(sql["table"])
                    indexes = self.get_indexes(sql["table"])
                    search = {
                        "table": sql["table"],
                        "row": {}
                    }
                    for column in indexes:
                        for key in column["column_names"].split(", "):
                            found = False
                            for pk in pks:
                                if pk["attname"] == key:
                                    found = True
                                    break
                            if not found:
                                search["row"][key] = sql["row"][key]
                    result = self.exact_select({"table": sql["table"], "row": search["row"]})
                    returning = getattr(result[0], sql["returning"])  # Hopefully should match at least 1
                else:
                    returning = value[0]
        self.__con.commit()
        if refresh_sequence:
            self.refresh_sequences(sql["table"])
        return returning

    def query(self, sql, options=None):
        sql = re.sub(r'\s:(\S\w*)', ' %(\g<1>)s', sql)
        if options is not None and "data" in options:
            self.__cur.execute(sql, options["data"])
        else:
            self.__cur.execute(sql)
        colnames = [desc[0] for desc in self.__cur.description]
        rows = self.__cur.fetchall()
        result = []
        for row in rows:
            result.append(create_record(row, colnames))
        return result

    def exact_select(self, sql):
        query = "SELECT * FROM " + sql["table"] + " WHERE"
        for column in sql["row"].keys():
            query += " " + column + " = %s AND"
        query = query[:-3]
        data = list(sql["row"].values())
        self.__cur.execute(query, data)
        colnames = [desc[0] for desc in self.__cur.description]
        rows = self.__cur.fetchall()
        result = []
        for row in rows:
            result.append(create_record(row, colnames))
        return result

    def get_pks(self, table):
        query = "SELECT pg_attribute.attname, format_type(pg_attribute.atttypid, pg_attribute.atttypmod) FROM pg_index, pg_class, pg_attribute, pg_namespace WHERE pg_class.oid = '" + table + "'::regclass AND  indrelid = pg_class.oid AND  nspname = 'public' AND  pg_class.relnamespace = pg_namespace.oid AND  pg_attribute.attrelid = pg_class.oid AND pg_attribute.attnum = any(pg_index.indkey) AND indisprimary"
        self.__cur.execute(query)
        keys = []
        for buff in self.__cur:
            row = {}
            c = 0
            for col in self.__cur.description:
                row.update({str(col[0]): buff[c]})
                c += 1
            keys.append(row)
        if 0 >= len(keys):
            return None
        return keys

    def get_indexes(self, table):
        query = "SELECT t.relname AS table_name, i.relname AS index_name, array_to_string(array_agg(a.attname), ', ') AS column_names FROM pg_class t, pg_class i, pg_index ix, pg_attribute a WHERE t.oid = ix.indrelid AND i.oid = ix.indexrelid AND a.attrelid = t.oid AND a.attnum = ANY(ix.indkey) AND t.relkind = 'r' AND t.relname = '" + table + "' GROUP BY t.relname, i.relname ORDER BY t.relname, i.relname"
        self.__cur.execute(query)
        keys = []
        for buff in self.__cur:
            row = {}
            c = 0
            for col in self.__cur.description:
                row.update({str(col[0]): buff[c]})
                c += 1
            keys.append(row)
        if 0 >= len(keys):
            return None
        return keys

    def refresh_sequences(self, table):
        """
        This function refreshes a table's sequence in case of primary key SERIAL type
        :param table: The table within the database
        :return:
        """
        query = "select * FROM (SELECT tc.table_name, kcu.column_name, pg_get_serial_sequence(tc.table_name, kcu.column_name) AS pk_seq FROM information_schema.table_constraints tc JOIN information_schema.key_column_usage kcu ON kcu.constraint_name = tc.constraint_name WHERE tc.table_name = '" + \
                table + "' AND tc.constraint_type = 'PRIMARY KEY') AS meta WHERE meta.pk_seq IS NOT NULL;"
        self.__cur.execute(query)
        rows = self.__cur.fetchall()
        if 0 >= len(rows):
            return
        for row in rows:
            new_id = 1
            query = "SELECT MAX(" + row[1] + ") FROM " + table
            self.__cur.execute(query)
            value = self.__cur.fetchall()[0][0]
            if value is not None:
                new_id = value + 1

            query = "ALTER SEQUENCE " + row[2] + " RESTART WITH %s"
            data = (new_id,)
            self.__cur.execute(query, data)
            rowcount = self.__cur.rowcount
            if rowcount > 0:
                print(str(rowcount) + " rows affected in sequence: " + row[2])
            self.__con.commit()

    def count_docs(self, table):
        query = "SELECT COUNT(*) FROM " + table
        self.__cur.execute(query)
        count = self.__cur.fetchall()[0][0]
        return count

    def clear_all(self, i_know_what_im_doing=False, refresh_sequence=True):
        if not i_know_what_im_doing:
            raise Exception("You don't know what you are doing. This is a dangerous action")
        # Get all tables
        query = "SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE';"
        self.__cur.execute(query)
        rows = self.__cur.fetchall()
        if 0 >= len(rows):
            return

        tables = []
        for row in rows:
            tables.append(row[0])

        print("Are you sure you want to clear all data in these tables?")
        maximum = 0
        c = 1
        for table in tables:
            if len(str(c) + ". " + table) > maximum:
                maximum = len(str(c) + ". " + table)
            c += 1
        c = 1
        for table in tables:
            count = self.count_docs(table)
            print((str(c) + ". " + table).ljust(maximum + 2) + str(count) + " documents")
            c += 1
        print("This might take a looooong long time. It might be faster to recreate the tables instead")
        ans = input("(Y/YES) > ")
        if ans.strip() != "Y" and ans.strip() != "YES":
            print("aborting :3")
            return

        for table in tables:
            self.__cur.execute("DELETE FROM " + table)
            self.__con.commit()
            if refresh_sequence:
                self.refresh_sequences(table)
            print("Cleared " + table)
        print("Done")

    def get_all(self, table, anchor, columns=None):
        """
        Function to get all elements in a table
        :param table: Tha table
        :param anchor: unique column that allows for scrolling through the data, recommended primary key or date
        :param columns: If there is specific columns you want to return
        :return:
        """
        SELECT = "*"
        if columns is not None:
            SELECT = ", ".join(columns)
        pks = self.get_pks(table)
        docs = []
        ids = []
        SIZE = 250
        TOTAL_DOCS = self.count_docs(table)
        TOTAL_DONE = 0
        if TOTAL_DOCS > 5000:
            print(f"Grabbing {TOTAL_DOCS} rows")
        else:
            print(f"Grabbing {TOTAL_DOCS} rows", end="")
        last_anchor_value = None

        while True:
            query = ""
            if last_anchor_value is None:
                query = "SELECT " + SELECT + " FROM " + table + " ORDER BY " + anchor + " LIMIT " + str(SIZE)
            else:
                query = "SELECT " + SELECT + " FROM " + table + " WHERE " + anchor + " >= " + str(
                    last_anchor_value) + " ORDER BY " + anchor + " LIMIT " + str(SIZE)
            self.__cur.execute(query)
            colnames = [desc[0] for desc in self.__cur.description]
            rows = self.__cur.fetchall()
            c = 0
            for row in rows:
                c += 1
                record = create_record(row, colnames)
                found = False
                for pk in pks:
                    id = getattr(record, pk["attname"])
                    if id not in ids:
                        ids.append(id)
                    else:
                        found = True
                if not found:
                    docs.append(record)
                    TOTAL_DONE += 1
                    if 5000 > TOTAL_DOCS:
                        print(".", end="")
                last_anchor_value = getattr(record, anchor)

            if TOTAL_DOCS > 5000:
                print(str(TOTAL_DONE) + " / " + str(TOTAL_DOCS) + " " + str(
                    round((TOTAL_DONE / TOTAL_DOCS) * 100, 2)) + "%")

            if SIZE != c:
                break
        return docs
