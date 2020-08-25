import json
import os
import boto3
import uuid
import pprint
import base64
import random
import urllib.request
import time
import string

s3client = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")
bucket = os.getenv("Bucket")
table = dynamodb.Table(os.getenv("Table"))
polly = boto3.client('polly')
transcribe = boto3.client('transcribe')
sns = boto3.client('sns')  

def get_public_url(bucket, key):
	return "https://s3.us-east-1.amazonaws.com/{}/{}".format(bucket,key)

def isEqual(text1, text2):
	for c in string.punctuation:
		text1 = text1.replace(c,"")
		text2 = text2.replace(c,"")
	
	text1 = (text1.lower()).strip()
	text2 = (text2.lower()).strip()
	
	print(text1)
	print(text2)
	
	if text1 == text2:
		return True
	return False

def upload(event, context):
	uid = str(uuid.uuid4()) + ".txt"
	request_body = json.loads(event['body'], strict = False)
	voiceList = [
		"Ivy",
		"Kendra",
		"Kimberly",
		"Salli",
		"Joey",
		"Justin"
	]
	voiceId = random.choice(voiceList)
	
	s3client.put_object(
	    Bucket = bucket,
		Key = uid,
		Body = base64.b64decode(request_body["file"]),
		ACL = "public-read"
	)

	table.put_item(Item ={
		"ID" : uid,
		"FileName" : request_body["name"],
		"Text" : request_body["text"],
		"Voice" : voiceId,
		"URL" : get_public_url(bucket,uid),
		"MP3ID" : "NOT SYNTHESIZED",
		"URLmp3" : "NOT SYNTHESIZED",
		"IDtrans" : "NOT TRANSCRIBED",
		"Transcription" : "NOT TRANSCRIBED",
		"URL2" : "NOT TRANSCRIBED",
		"IsEqual" : "NOT TRANSCRIBED"
	})
	
	body = {
		"url": get_public_url(bucket,uid)
	}

	response = {
		"statusCode": 200,
        "body": json.dumps(body)
    }
	
	return response

def transcription(event, context):
	message = json.loads(event['Records'][0]['Sns']['Message'])
	bucket=message['Records'][0]['s3']['bucket']['name']
	key=message['Records'][0]['s3']['object']['key']
	
	uid = str(uuid.uuid4())
	
	transcribe.start_transcription_job(
		TranscriptionJobName = uid,
		Media = {
			'MediaFileUri' : get_public_url(bucket,key)
		},
		MediaFormat = 'mp3',
		LanguageCode = 'en-US'
	)
	
	while True:
		status = transcribe.get_transcription_job(TranscriptionJobName = uid)
		if status['TranscriptionJob']['TranscriptionJobStatus'] in ['COMPLETED', 'FAILED']:
			break
		time.sleep(1)
	
	status = transcribe.get_transcription_job(TranscriptionJobName = uid)
	if status['TranscriptionJob']['TranscriptionJobStatus'] == 'COMPLETED':
		response = urllib.request.urlopen(status['TranscriptionJob']['Transcript']['TranscriptFileUri'])
		data = json.loads(response.read())
		text = data['results']['transcripts'][0]['transcript']
	
	uid = str(uid) + ".txt"
	
	s3client.put_object(
		Bucket = bucket,
		Key = uid,
		Body = text,
		ACL = "public-read"
	)
	
	tableID = key.replace("mp3","txt")
	item = table.get_item(
		Key = {
			'ID' : tableID
		}
	)
	
	result = isEqual(text,item['Item']['Text'])
	
	table.update_item(		
		Key = {
			'ID': tableID
		},
		UpdateExpression =
			"SET #TranscriptionAtt = :TranscriptionValue, #IsEqualAtt = :IsEqualValue, #IDtransAtt = :IDtransValue, #URL2Att = :URL2Value",                   
		ExpressionAttributeValues =
		{
			':TranscriptionValue' : text, 
			':IsEqualValue' : result,
			':IDtransValue' : uid,
			':URL2Value' : get_public_url(bucket,uid)
		},
		ExpressionAttributeNames =
		{
			'#TranscriptionAtt' : 'Transcription',
			'#IsEqualAtt' : 'IsEqual',
			'#IDtransAtt' : 'IDtrans',
			'#URL2Att' : 'URL2'
		},
	)	
	
	#topic_arn = os.getenv("Topic")
	#sns.publish(
	#	TopicArn = topic_arn,
	#	Message = "New file synthesized and transcribed! The result is " +str(isEqual),
	#	Subject = "Polly&Transcribe notification"
	#)
	
	return True
	
def synthesize(event, context):
	for i in event["Records"]:
		bucket=i["s3"]["bucket"]["name"]
		key=i["s3"]["object"]["key"]
		data = s3client.get_object(Bucket = bucket, Key = key)
		body = data['Body'].read().decode('utf-8')
		
		item = table.get_item(
			Key = {
				'ID' : key
			}
		)
		voice = item['Item']['Voice']

		response = polly.synthesize_speech(
			VoiceId = voice,
			OutputFormat = 'mp3', 
			Text = body
		)
				
		uidmp3 = key.replace("txt","mp3")
		
		s3client.put_object(
			Bucket = bucket,
			Key = uidmp3,
			Body = response['AudioStream'].read(),
			ACL = "public-read"
		)

		table.update_item(		
			Key = {
				'ID': key
			},
			UpdateExpression =
				"SET #MP3IDAtt = :MP3IDValue, #URLmp3Att = :URLmp3Value",                   
			ExpressionAttributeValues =
			{
				':MP3IDValue' : uidmp3, 
				':URLmp3Value' : get_public_url(bucket,uidmp3)
			},
			ExpressionAttributeNames =
			{
				'#MP3IDAtt' : 'MP3ID',
				'#URLmp3Att' : 'URLmp3'
			},
		)	
	
	return True