from flask import Flask, request, render_template
import os
import redis
import socket
import logging
from datetime import datetime
from opencensus.ext.azure import metrics_exporter
from opencensus.ext.azure.log_exporter import AzureEventHandler, AzureLogHandler
from opencensus.ext.azure.trace_exporter import AzureExporter
from opencensus.ext.flask.flask_middleware import FlaskMiddleware
from opencensus.trace.samplers import ProbabilitySampler
from opencensus.trace.tracer import Tracer
from opencensus.trace import config_integration

# Configure integrations
config_integration.trace_integrations(["logging", "requests"])

# Initialize App Insights
APP_INSIGHTS_CONNECTION_STRING = "InstrumentationKey=994880dc-bfc6-4d66-9335-76665ffd16b4;IngestionEndpoint=https://eastus-8.in.applicationinsights.azure.com/;LiveEndpoint=https://eastus.livediagnostics.monitor.azure.com/;ApplicationId=6fa3ec50-cad6-4a6a-a831-6325c25b5787"

# Logging setup
logger = logging.getLogger(__name__)
log_formatter = logging.Formatter("%(traceId)s %(spanId)s %(message)s")
log_handler = AzureLogHandler(connection_string=APP_INSIGHTS_CONNECTION_STRING)
event_handler = AzureEventHandler(connection_string=APP_INSIGHTS_CONNECTION_STRING)
log_handler.setFormatter(log_formatter)
logger.addHandler(log_handler)
logger.addHandler(event_handler)
logger.setLevel(logging.INFO)

# Metrics setup
exporter = metrics_exporter.new_metrics_exporter(
    enable_standard_metrics=True,
    connection_string=APP_INSIGHTS_CONNECTION_STRING,
)

# Tracing setup
tracer = Tracer(
    exporter=AzureExporter(connection_string=APP_INSIGHTS_CONNECTION_STRING),
    sampler=ProbabilitySampler(1.0),
)

# Flask app setup
app = Flask(__name__)
middleware = FlaskMiddleware(
    app,
    exporter=AzureExporter(connection_string=APP_INSIGHTS_CONNECTION_STRING),
    sampler=ProbabilitySampler(rate=1.0),
)

# Load configurations
app.config.from_pyfile('config_file.cfg')

# Load environment variables with fallbacks to config file
button1 = os.getenv('VOTE1VALUE', app.config['VOTE1VALUE'])
button2 = os.getenv('VOTE2VALUE', app.config['VOTE2VALUE'])
title = os.getenv('TITLE', app.config['TITLE'])

# Redis connection
redis_client = redis.Redis()

# Show host in title if configured
if app.config['SHOWHOST'] == "true":
    title = socket.gethostname()

# Initialize Redis keys
for button in (button1, button2):
    if not redis_client.get(button):
        redis_client.set(button, 0)

# Helper function to log custom events
def log_vote_event(vote_type, vote_count):
    properties = {'custom_dimensions': {vote_type: vote_count}}
    logger.info(f"{vote_type} logged", extra=properties)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'GET':
        # Retrieve votes
        vote1 = int(redis_client.get(button1).decode('utf-8'))
        vote2 = int(redis_client.get(button2).decode('utf-8'))

        # Trace votes
        with tracer.span(name="Cats Vote"):
            logger.info("Retrieved Cats Vote")
        with tracer.span(name="Dogs Vote"):
            logger.info("Retrieved Dogs Vote")

        # Render template
        return render_template("index.html", value1=vote1, value2=vote2, button1=button1, button2=button2, title=title)

    if request.method == 'POST':
        if request.form['vote'] == 'reset':
            # Reset votes
            redis_client.set(button1, 0)
            redis_client.set(button2, 0)
            vote1, vote2 = 0, 0

            # Log reset event
            log_vote_event("Cats Vote", vote1)
            log_vote_event("Dogs Vote", vote2)
        else:
            # Increment vote
            vote = request.form['vote']
            redis_client.incr(vote, 1)

            # Retrieve updated votes
            vote1 = int(redis_client.get(button1).decode('utf-8'))
            vote2 = int(redis_client.get(button2).decode('utf-8'))

        # Render template
        return render_template("index.html", value1=vote1, value2=vote2, button1=button1, button2=button2, title=title)

if __name__ == "__main__":
    # Use the appropriate configuration for local or production environments
    app.run(host='0.0.0.0', threaded=True, debug=True)
