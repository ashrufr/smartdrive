import pymssql
import os


def get_db():
    conn_str = os.environ.get("AZURE_SQL_CONNECTION")
    if not conn_str:
        raise RuntimeError("AZURE_SQL_CONNECTION environment variable is not set")

    params = {}
    for part in conn_str.split(";"):
        part = part.strip()
        if "=" in part:
            key, value = part.split("=", 1)
            key = key.strip().upper()
            value = value.strip()
            if key == "SERVER":
                host = value.split(",")[0]
                host = host.replace("tcp:", "")
                params["server"] = host
            elif key == "DATABASE":
                params["database"] = value
            elif key == "UID":
                params["user"] = value
            elif key == "PWD":
                params["password"] = value
            elif key == "PORT":
                params["port"] = int(value)

    conn = pymssql.connect(user=params.get("user"),
                           password=params.get("password"),
                           server=params.get("server"),
                           database=params.get("database"),
                           port=params.get("port", 1433))
    return conn


def dict_from_row(cursor, row):
    if row is None:
        return None
    columns = [col[0] for col in cursor.description]
    return dict(zip(columns, row))


def dict_from_rows(cursor, rows):
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in rows]


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='SD_users' AND xtype='U')
        CREATE TABLE SD_users (
            id INT IDENTITY(1,1) PRIMARY KEY,
            username NVARCHAR(100) UNIQUE NOT NULL,
            email NVARCHAR(255) UNIQUE NOT NULL,
            password_hash NVARCHAR(500) NOT NULL,
            phone NVARCHAR(50) DEFAULT '',
            verified NVARCHAR(10) DEFAULT 'No',
            email_verified INT DEFAULT 0,
            phone_verified INT DEFAULT 0,
            created_at DATETIME2 DEFAULT GETUTCDATE()
        )
    """)

    cur.execute("""
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='SD_cars' AND xtype='U')
        CREATE TABLE SD_cars (
            id INT IDENTITY(1,1) PRIMARY KEY,
            user_id INT NOT NULL,
            title NVARCHAR(255) NOT NULL,
            make NVARCHAR(100) NOT NULL,
            model NVARCHAR(100) NOT NULL,
            year INT NOT NULL,
            mileage INT DEFAULT 0,
            price FLOAT NOT NULL,
            color NVARCHAR(50) DEFAULT '',
            fuel_type NVARCHAR(50) DEFAULT 'Gasoline',
            transmission NVARCHAR(50) DEFAULT 'Automatic',
            description NVARCHAR(MAX) DEFAULT '',
            image_url NVARCHAR(500) DEFAULT '',
            is_sold INT DEFAULT 0,
            created_at DATETIME2 DEFAULT GETUTCDATE(),
            FOREIGN KEY (user_id) REFERENCES SD_users(id) ON DELETE CASCADE
        )
    """)

    cur.execute("""
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='SD_email_verifications' AND xtype='U')
        CREATE TABLE SD_email_verifications (
            id INT IDENTITY(1,1) PRIMARY KEY,
            user_id INT NOT NULL,
            token NVARCHAR(500) UNIQUE NOT NULL,
            created_at DATETIME2 DEFAULT GETUTCDATE(),
            expires_at DATETIME2 NOT NULL,
            used INT DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES SD_users(id) ON DELETE CASCADE
        )
    """)

    cur.execute("""
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='SD_phone_verifications' AND xtype='U')
        CREATE TABLE SD_phone_verifications (
            id INT IDENTITY(1,1) PRIMARY KEY,
            user_id INT NOT NULL,
            code NVARCHAR(10) NOT NULL,
            created_at DATETIME2 DEFAULT GETUTCDATE(),
            expires_at DATETIME2 NOT NULL,
            used INT DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES SD_users(id) ON DELETE CASCADE
        )
    """)

    cur.execute("""
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='SD_messages' AND xtype='U')
        CREATE TABLE SD_messages (
            id INT IDENTITY(1,1) PRIMARY KEY,
            car_id INT NOT NULL,
            sender_id INT NOT NULL,
            receiver_id INT NOT NULL,
            message NVARCHAR(MAX) NOT NULL,
            is_read INT DEFAULT 0,
            created_at DATETIME2 DEFAULT GETUTCDATE(),
            FOREIGN KEY (car_id) REFERENCES SD_cars(id) ON DELETE CASCADE,
            FOREIGN KEY (sender_id) REFERENCES SD_users(id),
            FOREIGN KEY (receiver_id) REFERENCES SD_users(id)
        )
    """)

    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    print("Azure SQL database initialized with SD_ tables.")
