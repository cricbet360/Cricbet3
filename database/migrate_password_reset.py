from database.database import get_db

from sqlalchemy import text


def main():

    db = next(get_db())

    try:

        dialect = db.bind.dialect.name

        print(
            "Database dialect:",
            dialect,
        )

        if dialect == "sqlite":

            db.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS password_reset_tokens (
                        id INTEGER PRIMARY KEY,
                        user_id INTEGER NOT NULL,
                        token_hash VARCHAR(64) NOT NULL UNIQUE,
                        expires_at DATETIME NOT NULL,
                        used_at DATETIME NULL,
                        created_at DATETIME NOT NULL,
                        FOREIGN KEY(user_id) REFERENCES users(id)
                    )
                    """
                )
            )

            db.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS
                    ix_password_reset_tokens_user_id
                    ON password_reset_tokens(user_id)
                    """
                )
            )

            db.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS
                    ix_password_reset_tokens_token_hash
                    ON password_reset_tokens(token_hash)
                    """
                )
            )

            db.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS
                    ix_password_reset_tokens_expires_at
                    ON password_reset_tokens(expires_at)
                    """
                )
            )

            db.commit()

            print(
                "Password reset token table created successfully."
            )

        else:

            print(
                "This migration currently expects SQLite."
            )

    except Exception as exc:

        db.rollback()

        print(
            "Migration failed:",
            str(exc),
        )

        raise

    finally:

        db.close()


if __name__ == "__main__":
    main()