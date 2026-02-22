import decimal
import json
import os
from datetime import datetime, timedelta, timezone

import boto3
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
        
        # 按 batch_id 分組
        batches_by_id = {}
        for item in response['Items']:
            batch_id = item['batch_id']
            url = item['url']

            if batch_id in batches_by_id:
                raise ValueError(f"Duplicate batch_id found in scan results: {batch_id}")

            if url == '__metadata__':
                # 這是 metadata 記錄
                batches_by_id[batch_id] = [
                    item['url']
                    for item in sorted(item['metadata'], key=lambda x: x['request_index'])
                ]
            else:
                batches_by_id[batch_id] = [url]
        
        for batch_id, urls in batches_by_id.items():
            try:
                # Check batch status
                # Note: batch_id should be the full resource name e.g. "batches/..."
                # If we stored just the ID, we might need to prepend "batches/" if the SDK expects it,
                # but usually the create response name includes it.
                batch_job = client.batches.get(name=batch_id)

                if batch_job.state == types.JobState.JOB_STATE_CANCELLING:
                    print(f"Batch {batch_id} was cancelling...")
                    continue
                
                if batch_job.state == types.JobState.JOB_STATE_CANCELLED:
                    print(f"Batch {batch_id} was cancelled. Deleting record.")
                    delete_batch(batch_job)
                    batch_table.delete_item(Key={'batch_id': batch_id})
                    continue

                if batch_job.state == types.JobState.JOB_STATE_PENDING:
                    # Still running
                    print(f"Batch {batch_id} is still pending since {batch_job.create_time}.")
                    if batch_job.create_time < datetime.now(timezone.utc) - timedelta(hours=6):
                        print(f"Batch {batch_id} has been pending for over 6 hours. Cancelling.")
                        client.batches.cancel(name=batch_id)
                    continue
                    
                if batch_job.state == types.JobState.JOB_STATE_SUCCEEDED:
                    print(f"Batch {batch_id} succeeded. Processing results.")
                    
                    # Get output file content
                    result_file_name = batch_job.dest.file_name
                    file_content_bytes = client.files.download(file=result_file_name)
                    output_content = file_content_bytes.decode('utf-8')
                    output_lines = output_content.strip().split('\n')

                    if len(output_lines) != len(urls):
                        raise ValueError(f"Output lines count {len(output_lines)} does not match URLs count {len(urls)} for batch {batch_id}")

                    # Parse JSONL results
                    # 逐行處理輸出，使用順序對應 URL
                    for url, line in zip(urls, output_lines):
                        result = json.loads(line)
                        print(f"Processing result:\n{result}")

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
                            analysis = json.loads(clean_text, parse_float=decimal.Decimal)
                            if isinstance(analysis, list):
                                analysis = analysis[0]
                            
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
                        except Exception as parse_error:
                            print(f"Error parsing result for {url}: {parse_error}")
                            print(f"Raw result line: {line}")

                    delete_batch(batch_job)

                    # Delete from batch table
                    batch_table.delete_item(Key={'batch_id': batch_id})

                elif batch_job.state == types.JobState.JOB_STATE_FAILED or batch_job.state == types.JobState.JOB_STATE_CANCELLED:
                    print(f"Batch {batch_id} failed or cancelled. {batch_job.error}")
                    # Optionally log errors from batch_job.error
                    delete_batch(batch_job)
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


def delete_batch(batch: types.BatchJob):
    # Delete source and destination files
    if batch.src:
        source_file_name = batch.src.file_name
        try:
            _gemini_client.files.delete(name=source_file_name)
            print(f"Deleted source file: {source_file_name}")
        except Exception as delete_error:
            import traceback
            traceback.print_exc()
            print(f"Error deleting source file {source_file_name}: {delete_error}")

    try:
        _gemini_client.batches.delete(name=batch.name)
        print(f"Deleted batch: {batch.name}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Error deleting batch {batch.name}: {e}")


if __name__ == "__main__":
    test_event = { }
    result = handler(test_event, None)
    print(json.dumps(json.loads(result['body']), indent=2, ensure_ascii=False))
