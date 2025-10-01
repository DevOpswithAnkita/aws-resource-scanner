import boto3, yaml, json
from datetime import datetime
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
from botocore.exceptions import NoCredentialsError, PartialCredentialsError
import io
import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache

app = FastAPI(title="AWS Resource Explorer API")
MAX_WORKERS = 20  # Parallel threads

def json_serial(obj):
    return obj.isoformat() if isinstance(obj, datetime) else str(obj)

def load_config(file_path="config.yaml"):
    try:
        cfg = yaml.safe_load(open(file_path))
        return cfg.get("regions", []), cfg.get("services", [])
    except:
        return [], []

@lru_cache(maxsize=100)
def get_boto3_client(service, region):
    """Cached boto3 client creation"""
    service_map = {
        'ec2': 'ec2', 'lambda': 'lambda', 'ecs': 'ecs', 'eks': 'eks',
        'autoscaling': 'autoscaling', 'vpc': 'ec2', 'security_groups': 'ec2',
        'subnets': 'ec2', 'nat_gateways': 'ec2', 'internet_gateways': 'ec2',
        'route_tables': 'ec2', 'elastic_ips': 'ec2', 'vpn_connections': 'ec2',
        'vpn_gateways': 'ec2', 's3': 's3', 'ebs': 'ec2', 'ebs_volumes': 'ec2',
        'snapshots': 'ec2', 'rds': 'rds', 'dynamodb': 'dynamodb',
        'elasticache': 'elasticache', 'load_balancers': 'elbv2',
        'target_groups': 'elbv2', 'cloudwatch_alarms': 'cloudwatch',
        'route53': 'route53', 'acm': 'acm', 'sagemaker': 'sagemaker',
        'cognito': 'cognito-idp', 'apigateway': 'apigatewayv2',
        'amplify': 'amplify', 'cloudfront': 'cloudfront', 'sns': 'sns',
        'sqs': 'sqs', 'ecr': 'ecr', 'secrets_manager': 'secretsmanager',
        'kms': 'kms', 'cloudformation': 'cloudformation', 'kinesis': 'kinesis',
        'glue': 'glue', 'stepfunctions': 'stepfunctions'
    }
    return boto3.client(service_map.get(service, service), region_name=region)

def get_tag(tags, key="Name"):
    if not tags: return "N/A" if key == "Name" else "No Tags"
    if key == "Name":
        return next((t["Value"] for t in tags if t["Key"] == "Name"), "N/A")
    return ", ".join([f"{t['Key']}={t['Value']}" for t in tags])

def extract_info(service, data):
    resources = []
    try:
        if service == "ec2" and "Reservations" in data:
            for res in data["Reservations"]:
                for i in res.get("Instances", []):
                    resources.append({"Name": get_tag(i.get("Tags")), "ID": i.get("InstanceId", "N/A"), 
                                    "Type": i.get("InstanceType", "N/A"), "Status": i.get("State", {}).get("Name", "unknown"),
                                    "Tags": get_tag(i.get("Tags"), "All")})
        
        elif service == "s3" and "Buckets" in data:
            for b in data["Buckets"]:
                resources.append({"Name": b.get("Name", "N/A"), "ID": b.get("Name", "N/A"), 
                                "Type": "S3 Bucket", "Status": "Active", "Tags": "N/A"})
        
        elif service == "rds" and "DBInstances" in data:
            for db in data["DBInstances"]:
                tags = db.get("TagList", [])
                resources.append({"Name": db.get("DBInstanceIdentifier", "N/A"), "ID": db.get("DbiResourceId", "N/A"),
                                "Type": db.get("DBInstanceClass", "N/A"), "Status": db.get("DBInstanceStatus", "unknown"),
                                "Tags": get_tag(tags, "All")})
        
        elif service == "lambda" and "Functions" in data:
            for f in data["Functions"]:
                resources.append({"Name": f.get("FunctionName", "N/A"), "ID": f.get("FunctionArn", "N/A").split(":")[-1],
                                "Type": f.get("Runtime", "N/A"), "Status": f.get("State", "Active"), "Tags": "N/A"})
        
        elif service == "vpc" and "Vpcs" in data:
            for v in data["Vpcs"]:
                resources.append({"Name": get_tag(v.get("Tags")), "ID": v.get("VpcId", "N/A"),
                                "Type": v.get("CidrBlock", "N/A"), "Status": "Available", "Tags": get_tag(v.get("Tags"), "All")})
        
        elif service == "security_groups" and "SecurityGroups" in data:
            for sg in data["SecurityGroups"]:
                resources.append({"Name": sg.get("GroupName", "N/A"), "ID": sg.get("GroupId", "N/A"),
                                "Type": "Security Group", "Status": "Active", "Tags": get_tag(sg.get("Tags"), "All")})
        
        elif service == "subnets" and "Subnets" in data:
            for s in data["Subnets"]:
                resources.append({"Name": get_tag(s.get("Tags")), "ID": s.get("SubnetId", "N/A"),
                                "Type": s.get("CidrBlock", "N/A"), "Status": s.get("State", "available"),
                                "Tags": get_tag(s.get("Tags"), "All")})
        
        elif service == "nat_gateways" and "NatGateways" in data:
            for n in data["NatGateways"]:
                resources.append({"Name": get_tag(n.get("Tags")), "ID": n.get("NatGatewayId", "N/A"),
                                "Type": "NAT Gateway", "Status": n.get("State", "unknown"), "Tags": get_tag(n.get("Tags"), "All")})
        
        elif service in ["ebs", "ebs_volumes"] and "Volumes" in data:
            for vol in data["Volumes"]:
                resources.append({"Name": get_tag(vol.get("Tags")), "ID": vol.get("VolumeId", "N/A"),
                                "Type": f"{vol.get('Size', 'N/A')}GB {vol.get('VolumeType', 'N/A')}",
                                "Status": vol.get("State", "unknown"), "Tags": get_tag(vol.get("Tags"), "All")})
        
        elif service == "snapshots" and "Snapshots" in data:
            for snap in data["Snapshots"]:
                resources.append({"Name": get_tag(snap.get("Tags")), "ID": snap.get("SnapshotId", "N/A"),
                                "Type": f"{snap.get('VolumeSize', 'N/A')}GB Snapshot", "Status": snap.get("State", "unknown"),
                                "Tags": get_tag(snap.get("Tags"), "All")})
        
        elif service == "internet_gateways" and "InternetGateways" in data:
            for igw in data["InternetGateways"]:
                vpc_ids = ", ".join([att.get("VpcId", "N/A") for att in igw.get("Attachments", [])])
                resources.append({"Name": get_tag(igw.get("Tags")), "ID": igw.get("InternetGatewayId", "N/A"),
                                "Type": f"IGW (VPC: {vpc_ids or 'Detached'})", "Status": "Available",
                                "Tags": get_tag(igw.get("Tags"), "All")})
        
        elif service == "route_tables" and "RouteTables" in data:
            for rt in data["RouteTables"]:
                resources.append({"Name": get_tag(rt.get("Tags")), "ID": rt.get("RouteTableId", "N/A"),
                                "Type": f"Route Table ({len(rt.get('Associations', []))} assoc)", "Status": "Available",
                                "Tags": get_tag(rt.get("Tags"), "All")})
        
        elif service == "elastic_ips" and "Addresses" in data:
            for eip in data["Addresses"]:
                instance_id = eip.get("InstanceId", "Unassociated")
                resources.append({"Name": get_tag(eip.get("Tags")), "ID": eip.get("AllocationId", "N/A"),
                                "Type": f"EIP: {eip.get('PublicIp', 'N/A')}", 
                                "Status": "Associated" if instance_id != "Unassociated" else "Unassociated",
                                "Tags": get_tag(eip.get("Tags"), "All")})
        
        elif service == "vpn_connections" and "VpnConnections" in data:
            for vpn in data["VpnConnections"]:
                resources.append({"Name": get_tag(vpn.get("Tags")), "ID": vpn.get("VpnConnectionId", "N/A"),
                                "Type": vpn.get("Type", "N/A"), "Status": vpn.get("State", "unknown"),
                                "Tags": get_tag(vpn.get("Tags"), "All")})
        
        elif service == "vpn_gateways" and "VpnGateways" in data:
            for vgw in data["VpnGateways"]:
                resources.append({"Name": get_tag(vgw.get("Tags")), "ID": vgw.get("VpnGatewayId", "N/A"),
                                "Type": vgw.get("Type", "N/A"), "Status": vgw.get("State", "unknown"),
                                "Tags": get_tag(vgw.get("Tags"), "All")})
        
        elif service == "target_groups" and "TargetGroups" in data:
            for tg in data["TargetGroups"]:
                resources.append({"Name": tg.get("TargetGroupName", "N/A"), "ID": tg.get("TargetGroupArn", "N/A").split(":")[-1],
                                "Type": f"{tg.get('Protocol', 'N/A')}:{tg.get('Port', 'N/A')}", "Status": "Active", "Tags": "N/A"})
        
        elif service == "autoscaling" and "AutoScalingGroups" in data:
            for asg in data["AutoScalingGroups"]:
                resources.append({"Name": asg.get("AutoScalingGroupName", "N/A"), "ID": asg.get("AutoScalingGroupARN", "N/A").split(":")[-1],
                                "Type": f"Min:{asg.get('MinSize', 0)} Max:{asg.get('MaxSize', 0)} Des:{asg.get('DesiredCapacity', 0)}",
                                "Status": "Active", "Tags": "N/A"})
        
        elif service == "cloudwatch_alarms" and "MetricAlarms" in data:
            for alarm in data["MetricAlarms"]:
                resources.append({"Name": alarm.get("AlarmName", "N/A"), "ID": alarm.get("AlarmArn", "N/A").split(":")[-1],
                                "Type": "CloudWatch Alarm", "Status": alarm.get("StateValue", "unknown"), "Tags": "N/A"})
        
        elif service == "load_balancers" and "LoadBalancers" in data:
            for lb in data["LoadBalancers"]:
                resources.append({"Name": lb.get("LoadBalancerName", "N/A"), "ID": lb.get("LoadBalancerArn", "N/A").split("/")[-1],
                                "Type": lb.get("Type", "N/A"), "Status": lb.get("State", {}).get("Code", "unknown"), "Tags": "N/A"})
        
        elif service in ["ecs", "eks"] and "clusterArns" in data:
            for arn in data["clusterArns"]:
                name = arn.split("/")[-1]
                resources.append({"Name": name, "ID": name, "Type": service.upper(), "Status": "Active", "Tags": "N/A"})
        
        # NEW SERVICES - Automatic detection
        elif service == "route53" and "HostedZones" in data:
            for hz in data["HostedZones"]:
                resources.append({"Name": hz.get("Name", "N/A"), "ID": hz.get("Id", "N/A").split("/")[-1],
                                "Type": f"Hosted Zone ({hz.get('ResourceRecordSetCount', 0)} records)", 
                                "Status": "Active", "Tags": "N/A"})
        
        elif service == "acm" and "CertificateSummaryList" in data:
            for cert in data["CertificateSummaryList"]:
                resources.append({"Name": cert.get("DomainName", "N/A"), "ID": cert.get("CertificateArn", "N/A").split("/")[-1],
                                "Type": "SSL/TLS Certificate", "Status": cert.get("Status", "unknown"), "Tags": "N/A"})
        
        elif service == "sagemaker" and "NotebookInstances" in data:
            for nb in data["NotebookInstances"]:
                resources.append({"Name": nb.get("NotebookInstanceName", "N/A"), "ID": nb.get("NotebookInstanceArn", "N/A").split("/")[-1],
                                "Type": nb.get("InstanceType", "N/A"), "Status": nb.get("NotebookInstanceStatus", "unknown"), "Tags": "N/A"})
        
        elif service == "cognito" and "UserPools" in data:
            for pool in data["UserPools"]:
                resources.append({"Name": pool.get("Name", "N/A"), "ID": pool.get("Id", "N/A"),
                                "Type": "Cognito User Pool", "Status": pool.get("Status", "Active"), "Tags": "N/A"})
        
        elif service == "apigateway" and "items" in data:
            for api in data["items"]:
                resources.append({"Name": api.get("name", "N/A"), "ID": api.get("id", "N/A"),
                                "Type": f"API Gateway ({api.get('protocolType', 'REST')})", "Status": "Active", "Tags": "N/A"})
        
        elif service == "amplify" and "apps" in data:
            for app in data["apps"]:
                resources.append({"Name": app.get("name", "N/A"), "ID": app.get("appId", "N/A"),
                                "Type": "Amplify App", "Status": "Active", "Tags": "N/A"})
        
        elif service == "dynamodb" and "TableNames" in data:
            for table in data["TableNames"]:
                resources.append({"Name": table, "ID": table, "Type": "DynamoDB Table", "Status": "Active", "Tags": "N/A"})
        
        elif service == "cloudfront" and "DistributionList" in data:
            for dist in data["DistributionList"].get("Items", []):
                resources.append({"Name": dist.get("DomainName", "N/A"), "ID": dist.get("Id", "N/A"),
                                "Type": "CloudFront Distribution", "Status": dist.get("Status", "unknown"), "Tags": "N/A"})
        
        elif service == "elasticache" and "CacheClusters" in data:
            for cache in data["CacheClusters"]:
                resources.append({"Name": cache.get("CacheClusterId", "N/A"), "ID": cache.get("CacheClusterId", "N/A"),
                                "Type": f"{cache.get('Engine', 'N/A')} {cache.get('CacheNodeType', 'N/A')}", 
                                "Status": cache.get("CacheClusterStatus", "unknown"), "Tags": "N/A"})
        
        elif service == "sns" and "Topics" in data:
            for topic in data["Topics"]:
                topic_name = topic.get("TopicArn", "N/A").split(":")[-1]
                resources.append({"Name": topic_name, "ID": topic.get("TopicArn", "N/A").split(":")[-1],
                                "Type": "SNS Topic", "Status": "Active", "Tags": "N/A"})
        
        elif service == "sqs" and "QueueUrls" in data:
            for queue_url in data["QueueUrls"]:
                queue_name = queue_url.split("/")[-1]
                resources.append({"Name": queue_name, "ID": queue_name, "Type": "SQS Queue", "Status": "Active", "Tags": "N/A"})
        
        elif service == "ecr" and "repositories" in data:
            for repo in data["repositories"]:
                resources.append({"Name": repo.get("repositoryName", "N/A"), "ID": repo.get("repositoryArn", "N/A").split("/")[-1],
                                "Type": "ECR Repository", "Status": "Active", "Tags": "N/A"})
        
        elif service == "secrets_manager" and "SecretList" in data:
            for secret in data["SecretList"]:
                resources.append({"Name": secret.get("Name", "N/A"), "ID": secret.get("ARN", "N/A").split(":")[-1],
                                "Type": "Secret", "Status": "Active", "Tags": "N/A"})
        
        elif service == "kms" and "Keys" in data:
            for key in data["Keys"]:
                resources.append({"Name": key.get("KeyId", "N/A"), "ID": key.get("KeyId", "N/A"),
                                "Type": "KMS Key", "Status": key.get("KeyState", "unknown"), "Tags": "N/A"})
        
        elif service == "cloudformation" and "StackSummaries" in data:
            for stack in data["StackSummaries"]:
                resources.append({"Name": stack.get("StackName", "N/A"), "ID": stack.get("StackId", "N/A").split("/")[-2],
                                "Type": "CloudFormation Stack", "Status": stack.get("StackStatus", "unknown"), "Tags": "N/A"})
        
        elif service == "kinesis" and "StreamNames" in data:
            for stream in data["StreamNames"]:
                resources.append({"Name": stream, "ID": stream, "Type": "Kinesis Stream", "Status": "Active", "Tags": "N/A"})
        
        elif service == "glue" and "DatabaseList" in data:
            for db in data["DatabaseList"]:
                resources.append({"Name": db.get("Name", "N/A"), "ID": db.get("Name", "N/A"),
                                "Type": "Glue Database", "Status": "Active", "Tags": "N/A"})
        
        elif service == "stepfunctions" and "stateMachines" in data:
            for sm in data["stateMachines"]:
                resources.append({"Name": sm.get("name", "N/A"), "ID": sm.get("stateMachineArn", "N/A").split(":")[-1],
                                "Type": "Step Functions", "Status": sm.get("status", "Active"), "Tags": "N/A"})
        
    except Exception as e:
        resources.append({"Name": "Error", "ID": "N/A", "Type": str(e), "Status": "Error", "Tags": "N/A"})
    return resources

def fetch_resources(region, service):
    try:
        client = get_boto3_client(service, region)
        
        # COMPUTE
        if service == "ec2":
            return boto3.client('ec2', region_name=region).describe_instances()
        elif service == "lambda":
            return client.list_functions()
        elif service in ["ecs", "eks"]:
            return client.list_clusters()
        elif service == "autoscaling":
            return client.describe_auto_scaling_groups()
        
        # NETWORKING
        elif service in ["vpc", "security_groups", "subnets", "nat_gateways", "internet_gateways", 
                         "route_tables", "elastic_ips", "vpn_connections", "vpn_gateways", 
                         "ebs", "ebs_volumes", "snapshots"]:
            if service == "vpc":
                return client.describe_vpcs()
            elif service == "security_groups":
                return client.describe_security_groups()
            elif service == "subnets":
                return client.describe_subnets()
            elif service == "nat_gateways":
                return client.describe_nat_gateways()
            elif service in ["ebs", "ebs_volumes"]:
                return client.describe_volumes()
            elif service == "snapshots":
                return client.describe_snapshots(OwnerIds=['self'])
            elif service == "internet_gateways":
                return client.describe_internet_gateways()
            elif service == "route_tables":
                return client.describe_route_tables()
            elif service == "elastic_ips":
                return client.describe_addresses()
            elif service == "vpn_connections":
                return client.describe_vpn_connections()
            elif service == "vpn_gateways":
                return client.describe_vpn_gateways()
        
        # STORAGE & DATABASE
        elif service == "s3":
            return client.list_buckets()
        elif service == "rds":
            return client.describe_db_instances()
        elif service == "dynamodb":
            return client.list_tables()
        elif service == "elasticache":
            return client.describe_cache_clusters()
        
        # LOAD BALANCING
        elif service == "load_balancers":
            return client.describe_load_balancers()
        elif service == "target_groups":
            return client.describe_target_groups()
        
        # MONITORING
        elif service == "cloudwatch_alarms":
            return client.describe_alarms()
        
        # NEW SERVICES
        elif service == "route53":
            return client.list_hosted_zones()
        elif service == "acm":
            return client.list_certificates()
        elif service == "sagemaker":
            return client.list_notebook_instances()
        elif service == "cognito":
            return client.list_user_pools(MaxResults=60)
        elif service == "apigateway":
            return client.get_apis()
        elif service == "amplify":
            return client.list_apps()
        elif service == "cloudfront":
            return client.list_distributions()
        elif service == "sns":
            return client.list_topics()
        elif service == "sqs":
            return client.list_queues()
        elif service == "ecr":
            return client.describe_repositories()
        elif service == "secrets_manager":
            return client.list_secrets()
        elif service == "kms":
            return client.list_keys()
        elif service == "cloudformation":
            return client.list_stacks()
        elif service == "kinesis":
            return client.list_streams()
        elif service == "glue":
            return client.get_databases()
        elif service == "stepfunctions":
            return client.list_state_machines()
        
    except Exception as e:
        return {"error": str(e)}

def fetch_single_service_region(region, service):
    """Fetch single service from single region"""
    try:
        data = fetch_resources(region, service)
        resources = extract_info(service, data)
        return (region, service, resources)
    except Exception as e:
        return (region, service, [{"Name": "Error", "ID": "N/A", "Type": str(e), "Status": "Error", "Tags": "N/A"}])

@app.get("/", response_class=HTMLResponse)
def dashboard():
    return """<!DOCTYPE html><html><head><title>AWS Resource Scanner</title><style>
    body{font-family:Arial,sans-serif;background:#f4f6f8;margin:0;padding:40px;text-align:center}
    h2{color:#333;margin-bottom:40px;font-size:2em}
    .btn{display:inline-block;margin:15px;padding:12px 25px;text-decoration:none;color:#fff;border-radius:5px;font-weight:bold}
    .aws-btn{background:#FF9900}.aws-btn:hover{background:#e68a00}
    .api-btn{background:#009688}.api-btn:hover{background:#00796b}
    .export-btn{background:#673AB7}.export-btn:hover{background:#5E35B1}
    </style></head><body>
    <div style="text-align:center;margin-bottom:20px">
    <img src="https://a0.awsstatic.com/libra-css/images/logos/aws_logo_smile_1200x630.png" alt="AWS" style="width:80px;height:auto;margin-bottom:10px">
    <h2>AWS Resource Scanner</h2></div>
    <a href="/all-table" class="btn aws-btn">Scan All AWS Resources</a>
    <a href="/docs" class="btn api-btn">API Docs</a>
    </body></html>"""

@app.get("/resources")
def get_resources(region: str, service: str):
    try:
        result = fetch_resources(region, service)
        return json.loads(json.dumps(result, default=json_serial))
    except (NoCredentialsError, PartialCredentialsError):
        return {"error": "AWS credentials missing"}
    except Exception as e:
        return {"error": str(e)}

@app.get("/all-table", response_class=HTMLResponse)
def all_table():
    regions, services = load_config()
    if not regions or not services:
        return "<h3>No regions/services in config.yaml</h3>"

    # Parallel fetching - FAST!
    all_results = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = []
        for svc in services:
            for region in regions:
                futures.append(executor.submit(fetch_single_service_region, region, svc))
        
        for future in as_completed(futures):
            region, service, resources = future.result()
            if service not in all_results:
                all_results[service] = {}
            all_results[service][region] = resources

    # Generate HTML
    html = """<html><head><title>AWS Resources</title><style>
    body{font-family:Arial,sans-serif;background:#f4f6f8;padding:20px}
    h2{color:#232F3E;text-align:center;margin-bottom:20px}
    .export-bar{background:#fff;padding:15px;margin-bottom:20px;text-align:center;box-shadow:0 2px 5px rgba(0,0,0,0.1);border-radius:5px}
    .export-btn{display:inline-block;margin:5px;padding:10px 20px;text-decoration:none;color:#fff;border-radius:5px;font-weight:bold}
    .json-btn{background:#2196F3}.json-btn:hover{background:#1976D2}
    .csv-btn{background:#4CAF50}.csv-btn:hover{background:#388E3C}
    .excel-btn{background:#FF5722}.excel-btn:hover{background:#E64A19}
    .print-btn{background:#9E9E9E;border:none;cursor:pointer}.print-btn:hover{background:#757575}
    h3{color:#FF9900;margin-top:30px;padding:10px;background:#fff;border-left:4px solid #FF9900}
    table{border-collapse:collapse;width:100%;background:#fff;box-shadow:0 2px 5px rgba(0,0,0,0.1);margin-bottom:20px}
    th,td{border:1px solid #ddd;padding:10px;text-align:left}
    th{background:#232F3E;color:white;font-weight:bold;position:sticky;top:0}
    tr:nth-child(even){background:#f9f9f9}tr:hover{background:#e8f4f8}
    .status-running,.status-available,.status-active{color:#4CAF50;font-weight:bold}
    .status-stopped{color:#F44336;font-weight:bold}
    .id-cell{font-family:'Courier New',monospace;font-size:12px;color:#666}
    .tags-cell{font-size:11px;color:#555;max-width:300px;word-wrap:break-word}
    @media print{.export-bar{display:none}}
    </style></head><body><h2> AWS Resources Scanner</h2>
    <div class="export-bar">
    <strong> Export Data:</strong>
    <a href="/export/json" class="export-btn json-btn" download>JSON</a>
    <a href="/export/csv" class="export-btn csv-btn" download>CSV</a>
    <a href="/export/excel" class="export-btn excel-btn" download>Excel</a>
    <button onclick="window.print()" class="export-btn print-btn">🖨️ Print</button>
    </div>"""

    for svc in services:
        html += f'<h3>{svc.upper().replace("_", " ")}</h3><table><thead><tr>'
        html += '<th>Region</th><th>Resource Name</th><th>Resource ID</th><th>Type</th><th>Status</th><th>All Tags</th></tr></thead><tbody>'
        
        has_resources = False
        for region in regions:
            resources = all_results.get(svc, {}).get(region, [])
            
            if resources:
                has_resources = True
                for res in resources:
                    status_class = ""
                    status_lower = res["Status"].lower()
                    if "running" in status_lower or "available" in status_lower or "active" in status_lower:
                        status_class = "status-running"
                    elif "stopped" in status_lower:
                        status_class = "status-stopped"
                    
                    html += f"""<tr>
                        <td><strong>{region}</strong></td>
                        <td>{res["Name"]}</td>
                        <td class="id-cell">{res["ID"]}</td>
                        <td>{res["Type"]}</td>
                        <td class="{status_class}">{res["Status"]}</td>
                        <td class="tags-cell">{res["Tags"]}</td>
                    </tr>"""
        
        if not has_resources:
            html += '<tr><td colspan="6" style="text-align:center;color:#999">No resources found</td></tr>'
        
        html += '</tbody></table>'

    html += '</body></html>'
    return HTMLResponse(content=html)

def collect_all_data():
    """Collect all resources from all regions and services - PARALLEL"""
    regions, services = load_config()
    all_data = []
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = []
        for svc in services:
            for region in regions:
                futures.append(executor.submit(fetch_single_service_region, region, svc))
        
        for future in as_completed(futures):
            region, service, resources = future.result()
            for res in resources:
                all_data.append({
                    "Service": service.upper(),
                    "Region": region,
                    "Name": res["Name"],
                    "ID": res["ID"],
                    "Type": res["Type"],
                    "Status": res["Status"],
                    "Tags": res["Tags"]
                })
    
    return all_data

@app.get("/export/json")
def export_json():
    data = collect_all_data()
    json_str = json.dumps(data, indent=2, default=json_serial)
    return StreamingResponse(
        io.BytesIO(json_str.encode()),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=aws_resources_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"}
    )

@app.get("/export/csv")
def export_csv():
    data = collect_all_data()
    if not data:
        return {"error": "No data to export"}
    
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["Service", "Region", "Name", "ID", "Type", "Status", "Tags"])
    writer.writeheader()
    writer.writerows(data)
    
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=aws_resources_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"}
    )

@app.get("/export/excel")
def export_excel():
    data = collect_all_data()
    if not data:
        return {"error": "No data to export"}
    
    # Create Excel-like CSV with better formatting
    output = io.StringIO()
    output.write("AWS Resources Export\n")
    output.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    output.write(f"Total Resources: {len(data)}\n\n")
    
    writer = csv.DictWriter(output, fieldnames=["Service", "Region", "Name", "ID", "Type", "Status", "Tags"])
    writer.writeheader()
    writer.writerows(data)
    
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode('utf-8-sig')),  # UTF-8 BOM for Excel
        media_type="application/vnd.ms-excel",
        headers={"Content-Disposition": f"attachment; filename=aws_resources_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"}
    )