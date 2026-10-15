from getpass import getpass
from pathlib import Path
import secrets
import sys

import MySQLdb

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"
DATABASES = ("tamil_kudil_pos_dev", "tamil_kudil_pos_dev_test")
APP_USER = "tamil_kudil_app"
APP_HOST = "127.0.0.1"
MYSQL_HOST = "127.0.0.1"
MYSQL_PORT = 3306


def main():
    if ENV_PATH.exists():
        print("Stopped: .env already exists. I did not overwrite it.")
        return 1

    admin_user = input("MySQL administrator username [root]: ").strip() or "root"
    admin_password = getpass("MySQL administrator password (input is hidden): ")

    created_databases = []
    created_user = False
    admin = None

    try:
        admin = MySQLdb.connect(
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            user=admin_user,
            passwd=admin_password,
            charset="utf8mb4",
            autocommit=True,
        )

        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA "
                "WHERE SCHEMA_NAME IN (%s, %s)",
                DATABASES,
            )
            existing_databases = {row[0] for row in cursor.fetchall()}
            cursor.execute(
                "SELECT User, Host FROM mysql.user WHERE User = %s AND Host = %s",
                (APP_USER, APP_HOST),
            )
            app_user_exists = cursor.fetchone() is not None

        conflicts = sorted(existing_databases)
        if app_user_exists:
            conflicts.append(f"MySQL account {APP_USER}@{APP_HOST}")
        if conflicts:
            print("Stopped because these names already exist:")
            for conflict in conflicts:
                print(f"  - {conflict}")
            print("Nothing was changed. Inspect the existing setup before proceeding.")
            return 1

        app_password = secrets.token_urlsafe(32)
        django_secret = secrets.token_urlsafe(48)

        with admin.cursor() as cursor:
            for database in DATABASES:
                cursor.execute(
                    f"CREATE DATABASE {database} "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
                )
                created_databases.append(database)

            cursor.execute(
                f"CREATE USER '{APP_USER}'@'{APP_HOST}' IDENTIFIED BY %s",
                (app_password,),
            )
            created_user = True

            for database in DATABASES:
                cursor.execute(
                    f"GRANT ALL PRIVILEGES ON {database}.* "
                    f"TO '{APP_USER}'@'{APP_HOST}'"
                )

        for database in DATABASES:
            app_connection = MySQLdb.connect(
                host=MYSQL_HOST,
                port=MYSQL_PORT,
                user=APP_USER,
                passwd=app_password,
                db=database,
                charset="utf8mb4",
                autocommit=True,
            )
            try:
                with app_connection.cursor() as cursor:
                    cursor.execute("CREATE TABLE __pos_setup_check (id INTEGER NOT NULL)")
                    cursor.execute("DROP TABLE __pos_setup_check")
            finally:
                app_connection.close()

        env_contents = (
            f"DJANGO_SECRET_KEY={django_secret}\n"
            "DJANGO_DEBUG=true\n"
            "DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost\n"
            f"MYSQL_DATABASE={DATABASES[0]}\n"
            f"MYSQL_TEST_DATABASE={DATABASES[1]}\n"
            f"MYSQL_USER={APP_USER}\n"
            f"MYSQL_PASSWORD={app_password}\n"
            f"MYSQL_HOST={MYSQL_HOST}\n"
            f"MYSQL_PORT={MYSQL_PORT}\n"
        )
        with ENV_PATH.open("x", encoding="utf-8", newline="\n") as env_file:
            env_file.write(env_contents)

        print("MySQL setup succeeded.")
        print(f"Created and verified both databases: {DATABASES[0]}, {DATABASES[1]}")
        print(f"Created a limited application account: {APP_USER}@{APP_HOST}")
        print("Saved private generated credentials to .env; no password was printed.")
        return 0

    except Exception as error:
        print(f"MySQL setup failed: {error.__class__.__name__}: {error}")
        print("Cleaning up only the new databases and account from this attempt.")
        if admin is not None:
            try:
                with admin.cursor() as cursor:
                    if created_user:
                        cursor.execute(f"DROP USER IF EXISTS '{APP_USER}'@'{APP_HOST}'")
                    for database in reversed(created_databases):
                        cursor.execute(f"DROP DATABASE IF EXISTS {database}")
            except Exception as cleanup_error:
                print(f"Automatic cleanup was incomplete: {cleanup_error.__class__.__name__}")
                print("Do not rerun yet; inspect the named databases/account in MySQL.")
        return 1
    finally:
        if admin is not None:
            admin.close()


if __name__ == "__main__":
    sys.exit(main())
