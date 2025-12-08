import json
import os
import boto3

# Initialize Lambda client
lambda_client = boto3.client('lambda')

# Get Lambda function name from environment variable
GET_NEWS_URLS_FUNCTION_NAME = os.environ['GET_NEWS_URLS_FUNCTION_NAME']

# Category IDs for finance and business news
CATEGORY_FINANCE_ID = "CAAqJQgKIh9DQkFTRVFvSUwyMHZNREpmTjNRU0JYcG9MVlJYS0FBUAE"
CATEGORY_BUSINESS_ID = "CAAqKggKIiRDQkFTRlFvSUwyMHZNRGx6TVdZU0JYcG9MVlJYR2dKVVZ5Z0FQAQ"


def handler(event, context):
    """
    Lambda dispatcher that triggers get_news_urls Lambda for both finance and business categories
    """
    try:
        results = []
        
        # Dispatch finance news job
        finance_payload = {
            'category_id': CATEGORY_FINANCE_ID
        }
        
        finance_response = lambda_client.invoke(
            FunctionName=GET_NEWS_URLS_FUNCTION_NAME,
            InvocationType='Event',  # Asynchronous invocation
            Payload=json.dumps(finance_payload)
        )
        
        results.append({
            'category': 'finance',
            'status_code': finance_response['StatusCode'],
            'request_id': finance_response['ResponseMetadata']['RequestId']
        })
        
        # Dispatch business news job
        business_payload = {
            'category_id': CATEGORY_BUSINESS_ID
        }
        
        business_response = lambda_client.invoke(
            FunctionName=GET_NEWS_URLS_FUNCTION_NAME,
            InvocationType='Event',  # Asynchronous invocation
            Payload=json.dumps(business_payload)
        )
        
        results.append({
            'category': 'business',
            'status_code': business_response['StatusCode'],
            'request_id': business_response['ResponseMetadata']['RequestId']
        })
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Successfully dispatched news URL collection jobs',
                'results': results
            })
        }
        
    except Exception as e:
        print(f"Error dispatching jobs: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'message': 'Error dispatching jobs',
                'error': str(e)
            })
        }
