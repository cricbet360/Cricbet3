import secrets
import string

from sqlalchemy import text

from database.database import engine


# =========================================================
# REFERRAL CODE CONFIGURATION
# =========================================================

REFERRAL_PREFIX = "CB"

REFERRAL_LENGTH = 8

REFERRAL_ALPHABET = (
    string.ascii_uppercase
    + string.digits
)


# =========================================================
# GENERATE UNIQUE CODE
# =========================================================

def generate_referral_code(connection):

    while True:

        random_part = "".join(
            secrets.choice(
                REFERRAL_ALPHABET
            )
            for _ in range(
                REFERRAL_LENGTH
            )
        )

        code = (
            REFERRAL_PREFIX
            + random_part
        )

        existing = connection.execute(
            text(
                """
                SELECT id
                FROM users
                WHERE referral_code = :code
                LIMIT 1
                """
            ),
            {
                "code": code
            }
        ).first()

        if not existing:
            return code


# =========================================================
# GET USER COLUMNS
# =========================================================

def get_user_columns(connection):

    rows = connection.execute(
        text(
            "PRAGMA table_info(users)"
        )
    ).fetchall()

    return {
        row[1]
        for row in rows
    }


# =========================================================
# ADD MISSING COLUMNS
# =========================================================

def add_referral_columns():

    print(
        f"Database dialect: {engine.dialect.name}"
    )

    with engine.begin() as connection:

        columns = get_user_columns(
            connection
        )

        # -------------------------------------------------
        # referral_code
        # -------------------------------------------------

        if "referral_code" not in columns:

            connection.execute(
                text(
                    """
                    ALTER TABLE users
                    ADD COLUMN referral_code VARCHAR(20)
                    """
                )
            )

            print(
                "Added referral_code"
            )

        else:

            print(
                "referral_code already exists"
            )


        # -------------------------------------------------
        # referred_by_user_id
        # -------------------------------------------------

        if "referred_by_user_id" not in columns:

            connection.execute(
                text(
                    """
                    ALTER TABLE users
                    ADD COLUMN referred_by_user_id INTEGER
                    """
                )
            )

            print(
                "Added referred_by_user_id"
            )

        else:

            print(
                "referred_by_user_id already exists"
            )


        # -------------------------------------------------
        # first_deposit_completed
        # -------------------------------------------------

        if (
            "first_deposit_completed"
            not in columns
        ):

            connection.execute(
                text(
                    """
                    ALTER TABLE users
                    ADD COLUMN first_deposit_completed
                    BOOLEAN NOT NULL DEFAULT 0
                    """
                )
            )

            print(
                "Added first_deposit_completed"
            )

        else:

            print(
                "first_deposit_completed already exists"
            )


        # -------------------------------------------------
        # referral_bonus_paid
        # -------------------------------------------------

        if (
            "referral_bonus_paid"
            not in columns
        ):

            connection.execute(
                text(
                    """
                    ALTER TABLE users
                    ADD COLUMN referral_bonus_paid
                    BOOLEAN NOT NULL DEFAULT 0
                    """
                )
            )

            print(
                "Added referral_bonus_paid"
            )

        else:

            print(
                "referral_bonus_paid already exists"
            )


# =========================================================
# BACKFILL EXISTING USERS
# =========================================================

def backfill_users():

    with engine.begin() as connection:

        users = connection.execute(
            text(
                """
                SELECT
                    id,
                    referral_code,
                    first_deposit_completed,
                    referral_bonus_paid
                FROM users
                ORDER BY id ASC
                """
            )
        ).mappings().all()


        print(
            f"Found {len(users)} existing users."
        )


        for user in users:

            user_id = user["id"]

            # =================================================
            # GIVE USER A REFERRAL CODE
            # =================================================

            referral_code = (
                user["referral_code"]
            )

            if not referral_code:

                referral_code = (
                    generate_referral_code(
                        connection
                    )
                )

                connection.execute(
                    text(
                        """
                        UPDATE users
                        SET referral_code = :code
                        WHERE id = :user_id
                        """
                    ),
                    {
                        "code":
                            referral_code,

                        "user_id":
                            user_id,
                    }
                )

                print(
                    f"User #{user_id} -> "
                    f"{referral_code}"
                )


            # =================================================
            # CHECK EXISTING COMPLETED DEPOSIT
            # =================================================

            completed_deposit = connection.execute(
                text(
                    """
                    SELECT id
                    FROM deposit_requests
                    WHERE user_id = :user_id
                    AND status = 'Completed'
                    LIMIT 1
                    """
                ),
                {
                    "user_id":
                        user_id
                }
            ).first()


            if completed_deposit:

                connection.execute(
                    text(
                        """
                        UPDATE users
                        SET first_deposit_completed = 1
                        WHERE id = :user_id
                        """
                    ),
                    {
                        "user_id":
                            user_id
                    }
                )


            # =================================================
            # CHECK WHETHER REFERRAL BONUS ALREADY EXISTS
            # =================================================

            referral_bonus = connection.execute(
                text(
                    """
                    SELECT id
                    FROM transactions
                    WHERE transaction_type = 'Referral Bonus'
                    AND reference_type = 'ReferralBonus'
                    AND reference_id = :user_id
                    LIMIT 1
                    """
                ),
                {
                    "user_id":
                        user_id
                }
            ).first()


            if referral_bonus:

                connection.execute(
                    text(
                        """
                        UPDATE users
                        SET referral_bonus_paid = 1
                        WHERE id = :user_id
                        """
                    ),
                    {
                        "user_id":
                            user_id
                    }
                )


# =========================================================
# CREATE UNIQUE INDEX
# =========================================================

def create_referral_index():

    with engine.begin() as connection:

        existing_index = connection.execute(
            text(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'index'
                AND name = 'ix_users_referral_code'
                """
            )
        ).first()


        if existing_index:

            print(
                "Referral-code index already exists."
            )

            return


        connection.execute(
            text(
                """
                CREATE UNIQUE INDEX
                ix_users_referral_code
                ON users(referral_code)
                """
            )
        )

        print(
            "Created unique referral-code index."
        )


# =========================================================
# MAIN
# =========================================================

def main():

    print(
        ""
    )

    print(
        "=============================================="
    )

    print(
        "      CRICKBET REFERRAL MIGRATION"
    )

    print(
        "=============================================="
    )

    print(
        ""
    )


    # -----------------------------------------------------
    # STEP 1
    # -----------------------------------------------------

    add_referral_columns()


    # -----------------------------------------------------
    # STEP 2
    # -----------------------------------------------------

    backfill_users()


    # -----------------------------------------------------
    # STEP 3
    # -----------------------------------------------------

    create_referral_index()


    print(
        ""
    )

    print(
        "=============================================="
    )

    print(
        "REFERRAL MIGRATION COMPLETED SUCCESSFULLY"
    )

    print(
        "=============================================="
    )


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":
    main()