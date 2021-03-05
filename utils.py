""" Supporting classes for taking screenshots and saving them to S3."""

import os

import boto3
from loguru import logger
from slack import WebClient
from slack.errors import SlackApiError


class S3Backup():

    def __init__(self, bucket_name, s3_subfolder):
        self.s3 = boto3.resource('s3')
        self.bucket_name = bucket_name
        self.bucket = self.s3.Bucket(self.bucket_name)
        self.s3_subfolder = s3_subfolder

    def get_s3_path(self, local_path, state):
        # CDC goes into its own top-level folder to not mess with state_screenshots
        if state == 'CDC':
            return os.path.join(state, os.path.basename(local_path))
        
        return os.path.join(self.s3_subfolder, state, os.path.basename(local_path))

    # uploads file from local path with specified name
    def upload_file(self, local_path, state):
        extra_args = {}
        if local_path.endswith('.png'):
            extra_args = {'ContentType': 'image/png'}
        elif local_path.endswith('.pdf'):
            extra_args = {'ContentType': 'application/pdf', 'ContentDisposition': 'inline'}
        elif local_path.endswith('.xlsx') or local_path.endswith('.xls'):
            extra_args = {'ContentType': 'application/vnd.ms-excel', 'ContentDisposition': 'inline'}
        elif local_path.endswith('.zip'):
            extra_args = {'ContentType': 'application/zip'}

        s3_path = self.get_s3_path(local_path, state)
        logger.info(f'Uploading file at {local_path} to {s3_path}')
        self.s3.meta.client.upload_file(local_path, self.bucket_name, s3_path, ExtraArgs=extra_args)


class SlackNotifier():

    def __init__(self, slack_channel, slack_api_token):
        self.channel = slack_channel
        self.client = WebClient(token=slack_api_token)

    # Returns the SlackResponse object
    def notify_slack(self, message, thread_ts=None):
        try:
            response = self.client.chat_postMessage(
                channel=self.channel,
                text=message,
                thread_ts=thread_ts
            )
            return response
        except SlackApiError as e:
            # just log Slack failures but don't break on them
            logger.error("Could not notify Slack, received error: %s" % e.response["error"])
