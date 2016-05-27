----
Package managers
----
Install node https://nodejs.org/en/ it comes bundled with npm (node package manager)

----
Database
----
Requires postgres 9.5 and postgis. 
Create a database called 'georef' and run sql "CREATE EXTENSION postgis;" in that db
Application settings are in georef/settings.py, change to whatever is appropriate

----
Set up a virtual environment with python 3.5 
----
"python -m venv myenv" see https://docs.python.org/3/library/venv.html
To create a virtual environment with a different version of python you need to use vitualenv:
C:\Python35\Scripts\virtualenv.exe -p C:\Python27.2\ArcGIS10.1\python.exe myenv
To use a virtual env on windows just run activate.bat in cmd

----
Install GDAL and psycopg2
----
Go to http://www.lfd.uci.edu/~gohlke/pythonlibs/ and download the correct & latest version of psycopg2 and gdal
With the virtual env activated, do "pip install x.whl" for both

----
Install other requirementss
----
GDAL and psycopg2 do not install well on windows so have to do the above step. But now you can just do "pip install requirements.txt"
Install front end requirements with npm install (in same directory as package.json)

----
Run
----
To do initial database migrations: "python manage.py makemigrations" and "python manage.py migrate"
Any problems with this, wipe your database, delete pycache & 'auto' py files in website/migrations and run again
Then do "python manage.py runserver"