from app.core.database import db

# Users collection
users_collection = db["users"]

# Create unique index on email
users_collection.create_index("email", unique=True)
