import json
import os
import boto3
from datetime import datetime
from openai import OpenAI
from openai.types import Batch


# Initialize clients
dynamodb = boto3.resource('dynamodb')  # type: ignore
news_table_name = os.environ['DYNAMODB_NEWS_TABLE_NAME']
batch_table_name = os.environ['DYNAMODB_BATCH_TABLE_NAME']
news_table = dynamodb.Table(news_table_name)  # type: ignore
batch_table = dynamodb.Table(batch_table_name)  # type: ignore

secrets_client = boto3.client('secretsmanager')
openai_secret_name = os.environ['OPENAI_API_KEY_SECRET_NAME']

# Cache OpenAI client
_openai_client = None

def get_openai_client():
    global _openai_client
    if _openai_client is None:
        secret_response = secrets_client.get_secret_value(SecretId=openai_secret_name)
        api_key = secret_response['SecretString']
        _openai_client = OpenAI(api_key=api_key)
    return _openai_client


def handler(event, context):
    """
    Check and process completed OpenAI batch requests
    """
    try:
        client = get_openai_client()
        
        # Query all pending batch requests
        response = batch_table.scan()
        if 'Item' not in response:
            print("No pending batch requests found.")

        completed_count = 0
        processed_count = 0
        for batch_item in response['Items']:
            processed_count += 1

            # Retrieve batch status from OpenAI
            batch = client.batches.retrieve(batch_item['batch_id'])
            
            # If completed, process results
            if batch.status == 'completed':
                process_batch(client, batch, batch_item['url'])
                batch_table.delete_item(Key={'batch_id': batch_item['batch_id']})
                completed_count += 1
                continue
            elif batch.status == 'failed':
                # Remove the failed batch item from DynamoDB
                batch_table.delete_item(Key={'batch_id': batch_item['batch_id']})
                print(f"Batch {batch.id}({batch_item['url']}) failed: {batch.errors}\nRemoved from DynamoDB.")
                continue

            # Update last_checked_at for pending/in-progress batches
            batch_table.update_item(
                Key={'batch_id': batch_item['batch_id']},
                UpdateExpression='SET last_checked_at = :checked_at',
                ExpressionAttributeValues={
                    ':checked_at': int(datetime.now().timestamp())
                }
            )
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Batch processing check completed',
                'processed': processed_count,
                'completed': completed_count
            })
        }
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'message': 'Error checking batch requests',
                'error': str(e)
            })
        }


def process_batch(client, batch: Batch, url: str):
    """
    Process completed batch results and update news items in DynamoDB
    """
    try:
        # Download batch results
        file_response = client.files.content(batch.output_file_id)
        results_content = file_response.text
        
        # Parse JSONL results
        results = [json.loads(line) for line in results_content.strip().split('\n')]
        print(f"Processing\n{results}\nfor batch {batch.id}")

        # Create a mapping of custom_id to result
        results_map = {result['custom_id']: result for result in results}

        if url not in results_map:
            print(f"No results found for url: {url} in {results_map}")
            return
        
        result = results_map[url]
        if result['response']['status_code'] == 200:
            analysis = json.loads(
                result['response']['body']['choices'][0]['message']['content']
            )
            
            # Update news item in DynamoDB
            news_table.update_item(
                Key={'url': url},
                UpdateExpression='SET analysis = :analysis, analysis_updated_at = :updated_at',
                ExpressionAttributeValues={
                    ':analysis': analysis,
                    ':updated_at': int(datetime.now().timestamp())
                }
            )
            print(f"Updated analysis for URL: {url}")
        else:
            print(f"Analysis failed for URL {url}: {result['response']['body']}")
        
    except Exception as e:
        print(f"Error processing batch results for {batch.id} {url}")
        raise


if __name__ == "__main__":
    # For local testing
    print(handler({}, None))
