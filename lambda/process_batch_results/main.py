import json
import os
import boto3
from datetime import datetime
from google import genai
from google.genai import types

# Initialize clients
dynamodb = boto3.resource('dynamodb')
news_table_name = os.environ['DYNAMODB_NEWS_TABLE_NAME']
batch_table_name = os.environ['DYNAMODB_BATCH_TABLE_NAME']
news_table = dynamodb.Table(news_table_name)
batch_table = dynamodb.Table(batch_table_name)

secrets_client = boto3.client('secretsmanager')
gemini_secret_name = os.environ['GEMINI_API_KEY_SECRET_NAME']

_gemini_client = None

def get_gemini_client():
    global _gemini_client
    if _gemini_client is None:
        secret_response = secrets_client.get_secret_value(SecretId=gemini_secret_name)
        api_key = secret_response['SecretString']
        _gemini_client = genai.Client(api_key=api_key)
    return _gemini_client

def handler(event, context):
    """
    Check and process completed Gemini batch requests
    """
    try:
        client = get_gemini_client()
        
        # Scan for pending batches
        response = batch_table.scan()
        if 'Items' not in response or not response['Items']:
            print("No pending batch requests found.")
            return {
                'statusCode': 200,
                'body': json.dumps({'message': 'No pending batches'})
            }

        print(f"Found {len(response['Items'])} pending batches.")
        
        for item in response['Items']:
            batch_id = item['batch_id']
            url = item['url']
            
            try:
                # Check batch status
                # Note: batch_id should be the full resource name e.g. "batches/..."
                # If we stored just the ID, we might need to prepend "batches/" if the SDK expects it,
                # but usually the create response name includes it.
                batch_job = client.batches.get(name=batch_id)
                
                print(f"Batch {batch_id} state: {batch_job.state}")
                
                if batch_job.state == types.JobState.JOB_STATE_PENDING:
                    # Still running
                    continue
                    
                if batch_job.state == types.JobState.JOB_STATE_SUCCEEDED:
                    print(f"Batch {batch_id} succeeded. Processing results.")
                    
                    # Get output file content
                    result_file_name = batch_job.dest.file_name
                    file_content_bytes = client.files.download(file=result_file_name)
                    output_content = file_content_bytes.decode('utf-8')
                    
                    # Parse JSONL results
                    # We expect one result since we submit one request per batch
                    for line in output_content.strip().split('\n'):
                        result = json.loads(line)
                        
                        # Check for errors in the individual request
                        if 'error' in result:
                            print(f"Error in batch result for {url}: {result['error']}")
                            continue
                            
                        # Extract the generated content
                        # The structure matches the GenerateContentResponse
                        # We need to find the text part
                        try:
                            # The response structure from Batch API might be wrapped
                            # result['response']['body'] is likely where the GenerateContentResponse is
                            # But let's try to parse it robustly
                            
                            # Assuming result is the response object directly or wrapped
                            # Based on other Batch APIs, it's usually:
                            # {
                            #     "response": {
                            #         "responseId": "ld5TadKTD-bVz7IPnMCSiQk",
                            #         "usageMetadata": {
                            #             "candidatesTokenCount": 693,
                            #             "promptTokensDetails": [
                            #                 {
                            #                     "modality": "TEXT",
                            #                     "tokenCount": 1816
                            #                 }
                            #             ],
                            #             "totalTokenCount": 3794,
                            #             "promptTokenCount": 1816,
                            #             "thoughtsTokenCount": 1285
                            #         },
                            #         "candidates": [
                            #             {
                            #                 "index": 0,
                            #                 "finishReason": "STOP",
                            #                 "content": {
                            #                     "role": "model",
                            #                     "parts": [
                            #                         {
                            #                             "text":
                            
                            parts = result['response']['candidates'][0]['content']['parts']
                            # Find the text part that contains JSON (thinking models may have multiple parts)
                            text_content = ""
                            for part in parts:
                                part_text = part['text']
                                # Look for JSON-like content
                                if part_text.strip().startswith('{') or part_text.strip().startswith('```json'):
                                    text_content = part_text
                                    break
                                else:
                                    # Fallback to the last text part
                                    text_content = part_text
                            
                            if not text_content:
                                print(f"No text content found in parts for {url}")
                                continue

                            # Parse the JSON from the text content
                            # Sometimes the model might wrap JSON in markdown blocks
                            clean_text = text_content.strip()
                            if clean_text.startswith('```json'):
                                clean_text = clean_text[7:]
                                if clean_text.endswith('```'):
                                    clean_text = clean_text[:-3]
                            elif clean_text.startswith('```'):
                                clean_text = clean_text[3:]
                                if clean_text.endswith('```'):
                                    clean_text = clean_text[:-3]
                            
                            clean_text = clean_text.strip()
                            analysis = json.loads(clean_text)
                            
                            # Update DynamoDB
                            news_table.update_item(
                                Key={'url': url},
                                UpdateExpression='SET analysis = :analysis, analysis_updated_at = :updated_at',
                                ExpressionAttributeValues={
                                    ':analysis': analysis,
                                    ':updated_at': int(datetime.now().timestamp())
                                }
                            )
                            print(f"Updated analysis for URL: {url}")

                            # Delete from batch table
                            batch_table.delete_item(Key={'batch_id': batch_id})
                        except Exception as parse_error:
                            print(f"Error parsing result for {url}: {parse_error}")
                            print(f"Raw result line: {line}")
                    
                elif batch_job.state == types.JobState.JOB_STATE_FAILED or batch_job.state == types.JobState.JOB_STATE_CANCELLED:
                    print(f"Batch {batch_id} failed or cancelled. {batch_job.error}")
                    # Optionally log errors from batch_job.error
                    batch_table.delete_item(Key={'batch_id': batch_id})
                
            except Exception as e:
                print(f"Error processing batch {batch_id}: {e}")
                
        return {
            'statusCode': 200,
            'body': json.dumps({'message': 'Batch processing check completed'})
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
