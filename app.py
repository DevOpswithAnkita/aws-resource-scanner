import boto3, yaml, json
from datetime import datetime
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from botocore.exceptions import NoCredentialsError, PartialCredentialsError

app = FastAPI(title="AWS Resource Explorer API")

# -----------------------
# Helper functions
# -----------------------
def json_serial(obj):
    return obj.isoformat() if isinstance(obj, datetime) else str(obj)

def load_config(file_path="config.yaml"):
    try:
        cfg = yaml.safe_load(open(file_path))
        return cfg.get("regions", []), cfg.get("services", [])
    except Exception:
        return [], []

def fetch_resources(region, services):
    data = {}
    for s in services:
        try:
            c = boto3.client(s, region_name=region)
            if s == "ec2":
                data[s] = c.describe_instances()
            elif s == "s3":
                data[s] = c.list_buckets()
            elif s == "rds":
                data[s] = c.describe_db_instances()
            elif s == "lambda":
                data[s] = c.list_functions()
            elif s in ["ecs", "eks"]:
                data[s] = c.list_clusters()
        except Exception as e:
            data[s] = f"Error: {e}"
    return data

# -----------------------
# FRONTEND on "/"
# -----------------------
@app.get("/", response_class=HTMLResponse)
def dashboard():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>AWS Resource Scanner</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                background-color: #f4f6f8;
                margin: 0;
                padding: 40px;
                text-align: center;
            }
            h2 {
                color: #333;
                margin-bottom: 40px;
                font-size: 2em;
            }
            .btn {
                display: inline-block;
                margin: 15px;
                padding: 12px 25px;
                text-decoration: none;
                color: #fff;
                border-radius: 5px;
                font-weight: bold;
            }
            .aws-btn { background-color: #FF9900; }
            .aws-btn:hover { background-color: #e68a00; }
            .api-btn { background-color: #009688; }
            .api-btn:hover { background-color: #00796b; }
        </style>
    </head>
    <body>
       <div style="text-align:center; margin-bottom:20px;">
    <img src="https://a0.awsstatic.com/libra-css/images/logos/aws_logo_smile_1200x630.png" 
         alt="AWS Logo" 
         style="width:80px; height:auto; margin-bottom:10px;">
    <h2>AWS Resource Scanner</h2>
     </div>    
        <a href="/all-table" class="btn aws-btn">Scan All AWS Resources</a>
        <a href="/docs" class="btn api-btn">Open Backend Swagger Docs</a>
    </body>
    </html>
    """

# -----------------------
# API ENDPOINTS
# -----------------------
@app.get("/resources")
def get_resources(region: str, service: str):
    try:
        result = fetch_resources(region, [service])
        return json.loads(json.dumps(result, default=json_serial))
    except (NoCredentialsError, PartialCredentialsError):
        return {"error": "AWS credentials missing or incomplete"}
    except Exception as e:
        return {"error": str(e)}


# -----------------------
# HTML TABLE VIEW
# -----------------------
@app.get("/all-table", response_class=HTMLResponse)
def all_table():
    regions, services = load_config()
    if not regions or not services:
        return "<h3>No regions/services found in config.yaml</h3>"

    all_data = {r: fetch_resources(r, services) for r in regions}

    html = """
    <html>
    <head>
        <title>AWS Resources view in table</title>
        <style>
            body { font-family: Arial, sans-serif; background:#f4f6f8; padding:20px; }
            table { border-collapse: collapse; width: 100%; background:#fff; box-shadow:0 2px 5px rgba(0,0,0,0.1); }
            th, td { border: 1px solid #ccc; padding: 8px; text-align: left; vertical-align: top; }
            th { background:#009688; color:#fff; }
            tr:nth-child(even) { background:#f9f9f9; }
            pre { white-space: pre-wrap; word-wrap: break-word; font-size: 12px; }
        </style>
    </head>
    <body>
        <h2>AWS Resources (Table View)</h2>
        <table>
            <thead>
                <tr>
                    <th>Region</th>
                    <th>Service</th>
                    <th>Details (Terraform Reference)</th>
                </tr>
            </thead>
            <tbody>
    """

    for region, svc_data in all_data.items():
        for svc, details in svc_data.items():
            pretty_details = json.dumps(details, indent=2, default=json_serial)
            html += f"""
            <tr>
                <td>{region}</td>
                <td>{svc}</td>
                <td><pre>{pretty_details}</pre></td>
            </tr>
            """

    html += """
            </tbody>
        </table>
    </body>
    </html>
    """
    return HTMLResponse(content=html)

