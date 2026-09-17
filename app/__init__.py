import utils.clients
import utils.http_session
import utils.transport
import utils.session
from flask import Flask

from app.config import Config
from app.docs import init_docs


def create_app(config_class: type[Config] = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_class)

    from app.api import api_bp

    app.register_blueprint(api_bp, url_prefix="/api/v1")
    init_docs(app)

    return app
