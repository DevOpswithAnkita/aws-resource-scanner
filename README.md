# AWS Resource Scanner

# Why Use AWS Resource Scanner?

* Saves Time: No need to log in to AWS consoles to check services.
* Quick Overview: See all your resources across multiple regions in one table or dashboard.
* API & HTML Dashboard: Access resources via browser or programmatically through REST API.
* Configurable: Easily choose regions and services in config.yaml.
* Automation-Friendly: Can be integrated into scripts or CI/CD pipelines for monitoring or auditing resources.
* Portable: Works on any system with Python and AWS credentials, no heavy setup required.

---

## Features

- Scan AWS resources (EC2, S3, RDS, Lambda, ECS, EKS) you can add more resources .py file.
- Frontend dashboard (`http://127.0.0.1:8000/`).
- View results in a clean HTML **dashboard** (`http://127.0.0.1:8000/all-table`).
- REST API support with **Swagger UI** (`http://127.0.0.1:8000/docs`).
- Configurable **regions and services** via `config.yaml`.

---

## Project Structure

```
aws-resource-scanner/
│── app.py              # FastAPI backend + HTML dashboard
│── config.yaml         # AWS regions & services list
│── requirements.txt    # Dependencies
│── README.md           # Project overview
│── .gitignore          # Ignore unnecessary files
```

---

## Setup

1. **Clone the repo**

   ```bash
   git clone https://github.com/DevOpswithAnkita/aws-resource-scanner.git
   cd aws-resource-scanner
   ```
 2. **Create a venv**
  ```bash
   python3 -m venv .venv
   ```
   **Activate it**
   ```bash
     source .venv/bin/activate 
   ```   
   **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```
3. **Configure AWS IAM Setup**

   **Option 1: Use AWS Managed Policy (Recommended)**

   1. Go to **IAM → Users → Add user**
   2. Username: e.g., `aws-resource-scanner`
   3. **Programmatic access** → Check
   4. Attach **ReadOnlyAccess** policy
   5. Download **Access Key & Secret Key**

   ***Option 2: Custom Minimal Policy**

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": [
           "ec2:DescribeInstances",
           "s3:ListBuckets",
           "rds:DescribeDBInstances",
           "lambda:ListFunctions",
           "ecs:ListClusters",
           "eks:ListClusters"
         ],
         "Resource": "*"
       }
     ]
   }
   ```

   Attach to your IAM user or role if you want minimal permissions.

   > Configure locally using `aws configure`
   >

   ```bash
   aws configure
   export AWS_ACCESS_KEY_ID="YOUR_ACCESS_KEY"
   export AWS_SECRET_ACCESS_KEY="YOUR_SECRET_KEY"
   export AWS_DEFAULT_REGION="us-east-1"

   ```
4. **Update config**

   - Edit `config.yaml` to include the regions and services you want to scan.

---

## Run the App

```bash
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

Now open in your browser:
[http://localhost:8000](http://localhost:8000)

---

## Endpoints

- **Dashboard** → `/`
- **Table View** → `/all-table`
- **Swagger Docs** → `/docs`
- **Fetch resources** → `/resources?region=us-east-1&service=ec2`

---

## config.yaml

```yaml
regions:
  - "us-east-1"
  - "ap-south-1"
  - "ap-south-2"

services:
  - "ec2"
  - "s3"
  - "rds"
  - "lambda"
  - "ecs"
  - "eks"
```

---

