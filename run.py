from app import app
import os

if __name__ == "__main__":
    debug_mode = os.getenv("FLASK_ENV") == "development"

    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=debug_mode
    )
