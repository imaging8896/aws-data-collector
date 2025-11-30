import json
import os
import boto3
from datetime import datetime
from decimal import Decimal

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb')
table_name = os.environ['DYNAMODB_TABLE_NAME']
table = dynamodb.Table(table_name)

def handler(event, context):
    """
    Lambda function handler for data collection
    
    Expected event format:
    {
        "id": "unique-identifier",
        "data": {
            "key1": "value1",
            "key2": "value2"
        }
    }
    """
    try:
        # Extract data from event
        record_id = event.get('id', f"record-{int(datetime.now().timestamp())}")
        data = event.get('data', {})
        
        # Create item for DynamoDB
        item = {
            'id': record_id,
            'timestamp': int(datetime.now().timestamp()),
            'data': json.loads(json.dumps(data), parse_float=Decimal),
            'environment': os.environ.get('ENVIRONMENT', 'dev')
        }
        
        # Put item in DynamoDB
        response = table.put_item(Item=item)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Data collected successfully',
                'id': record_id,
                'timestamp': item['timestamp']
            })
        }
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'message': 'Error collecting data',
                'error': str(e)
            })
        }
