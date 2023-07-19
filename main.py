#!/usr/bin/python
import os
import time
# import MySQLdb
import requests
from datetime import datetime


def checkwebsite(url):
    # print "Checking " + url + " for avalibility...\n\n"
    try:
        r = requests.get(url, timeout=10)
        return True
    except:
        return False


# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    folder_path = os.path.dirname(os.path.realpath(__file__))

    while True:
        with open('/var/www/html/hidden/mysql_c', 'r') as f:
            creds = f.read().split("\n")

        f.close()
        # host:		creds[0]
        # uname:	creds[1]
        # psswd:	creds[2]
        # db:		creds[3]

        db = MySQLdb.connect(host=creds[0],
                             user=creds[1],
                             passwd=creds[2],
                             db=creds[3])

        # Create a Cursor object to execute queries.
        cur = db.cursor()
        db.autocommit(True)
        # cur.execute("UPDATE proxylist SET ping='2.20' WHERE id=1")

        # Select data from table using SQL query.
        cur.execute("SELECT * FROM proxylist")

        # print the first and second columns
        for row in cur.fetchall():
            url = ""
            if row[1].count('/') > 2:  # If slashes is more than 2
                url = row[1].rsplit('/', 1)[0]
            else:
                url = row[1]
            # print (url)
            # print (row[1])
            start = time.time()
            changedSymbol = "  "

            if checkwebsite(url) == True:
                ping = round(time.time() - start, 2)
                if row[4] != 1:
                    changedSymbol = "++"
                print("Working: 1:{0} {1} {2:45}{3}".format(str(row[4]), changedSymbol, row[1], str(ping)))
                # print ("Working: 1:" + str(row[4]) + "\t" + row[1] + "\t" + str(ping))
                cur.execute("UPDATE proxylist SET ping='" + str(ping) + "' WHERE id=" + str(row[0]))
            else:
                ping = round(time.time() - start, 1)
                if row[4] != 0:
                    changedSymbol = "--"
                print("Down...  0:{0} {1} {2:45}{3}".format(str(row[4]), changedSymbol, row[1], str(ping)))
                # print ("Down...  0:" + str(row[4]) + "\t" + row[1] + "\t" + str(ping))
                cur.execute("UPDATE proxylist SET ping='99.99' WHERE id=" + str(row[0]))

        ## Check if new day
        filetime = open(folder_path + "/time.txt", "r")
        today = filetime.readline()
        filetime.close()
        if today != datetime.now().strftime('%d.%m.%Y'):
            print("It's a new day.. You better not be up late...")
            filetime = open(folder_path + "/time.txt", "w")
            filetime.write(datetime.now().strftime('%d.%m.%Y'))
            filetime.close()
            cur.execute("UPDATE proxylist SET clicks24='0'")
            cur.execute("UPDATE websites SET clicks24='0'")
            print("clicks24 set to 0")

        print("Shh! The script is sleeping!")
        time.sleep(900)

# See PyCharm help at https://www.jetbrains.com/help/pycharm/
