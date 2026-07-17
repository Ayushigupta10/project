import logging
from dotenv import load_dotenv
from flask import Flask
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from config import Config
from models import db, User

login_manager = LoginManager()
login_manager.login_view = "main.login"
csrf = CSRFProtect()


def create_app():
    load_dotenv()
    app = Flask(__name__)
    app.config.from_object(Config)
    app.jinja_env.globals["int"] = int
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    logging.basicConfig(level=logging.INFO)
    with app.app_context():
        db.create_all()
    from routes import main
    app.register_blueprint(main)
    return app


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
