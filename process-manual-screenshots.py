""" Script that runs through validated manual screenshots in Airtable and uploads them to S3. """

import os
import sys

from argparse import ArgumentParser, RawDescriptionHelpFormatter
import dateutil.parser
from loguru import logger
import requests

from utils import S3Backup, SlackNotifier


parser = ArgumentParser(
    description=__doc__,
    formatter_class=RawDescriptionHelpFormatter)

parser.add_argument(
    '--temp-dir',
    default='/tmp/public-cache',
    help='Local temp dir for snapshots')

# Args relating to S3 setup

parser.add_argument(
    '--s3-bucket',
    default='covid-data-archive',
    help='S3 bucket name')

parser.add_argument(
    '--s3-subfolder',
    default='state_screenshots',
    help='Name of subfolder on S3 bucket to upload files to')

parser.add_argument('--push-to-s3', dest='push_to_s3', action='store_true', default=False,
    help='Push screenshots to S3')

# Args relating to Slack notifications
parser.add_argument(
    '--slack-channel',
    default='',
    help='Slack channel ID to notify on screenshot errors')

parser.add_argument(
    '--slack-api-token',
    default='',
    help='Slack API token to use for notifications')

# Airtable access
parser.add_argument(
    '--airtable-api-key',
    default='',
    help='Airtable API key to use for accessing manual screenshots')

parser.add_argument(
    '--airtable-table-id',
    default='',
    help='Airtable API key to use for accessing manual screenshots')



def slack_notifier_from_args(args):
    if args.slack_channel and args.slack_api_token:
        return SlackNotifier(args.slack_channel, args.slack_api_token)
    return None


def get_state(record_fields):
    return record_fields['Name'].split('-')[0]


def make_local_path(record_fields, args):
    # state, like "DC"
    state = get_state(record_fields)

    # suffix (from description), like "vaccine-tab"
    description = record_fields.get('Description (optional)')
    if description:
        suffix = '-'.join(description.lower().split(' '))
    else:
        suffix = ''

    # time suffix, like "20210929-021301"
    time = record_fields['Date']
    time_obj = dateutil.parser.isoparse(time)
    time_suffix = time_obj.strftime('%Y%m%d-%H%M%S')

    # file extension, like "png"
    fileext = record_fields['Attachments'][0]['filename'].split('.')[-1]

    # the basename should take the form: "state-suffix-time-suffix.ext"
    if suffix:
        basename = '%s-%s-%s.%s' % (state, suffix, time_suffix, fileext)
    else:
        basename = '%s-%s.%s' % (state, time_suffix, fileext)

    local_path = os.path.join(args.temp_dir, basename)
    return local_path


def mark_uploaded_in_airtable(record, args):
    # modify the Airtable record to say "Uploaded"
    record_id = record['id']
    update_record_data = {
        'fields': {'Status': 'Uploaded'},
    }

    url = "https://api.airtable.com/v0/%s/Screenshots/%s" % (args.airtable_table_id, record_id)
    headers = {
        "Authorization": "Bearer " + args.airtable_api_key,
        "Content-Type": "application/json"
    }

    response = requests.patch(url, headers=headers, json=update_record_data)
    logger.info('Marked record %s Uploaded in Airtable' % record['fields']['Name'])


def process_record(record, s3, args):
    record_fields = record['fields']

    # state, like "DC"
    state = get_state(record_fields)
    local_path = make_local_path(record_fields, args)

    attachment_url = record_fields['Attachments'][0]['url']
    logger.info('Downloading attachment from: %s' % attachment_url)
    attachment = requests.get(attachment_url)
    if attachment.status_code == 200:
        with open(local_path, 'wb') as f:
            f.write(attachment.content)
            logger.info('Downloaded attachment to: %s' % local_path)
    else:
        logger.error(f'Attachment response status code: {attachment.status_code}')
        raise ValueError(f'Could not download data from URL: {attachment_url}')

    # upload to S3
    s3.upload_file(local_path, state)
    logger.info('Uploaded %s to %s' % (state, s3.get_s3_path(local_path, state)))

    # update Airtable to mark it "Uploaded"
    mark_uploaded_in_airtable(record, args)


def get_validated_records(args):
    """ Gets list of all validated screenshots from Airtable"""

    url = "https://api.airtable.com/v0/%s/Screenshots" % args.airtable_table_id
    headers = {"Authorization": "Bearer " + args.airtable_api_key}
    response = requests.get(url, headers=headers).json()
    validated_records = [x for x in response['records'] if x['fields'].get('Status') == 'Validated']

    # if any more, collect more records
    while 'offset' in response:
        offset = response['offset']
        response = requests.get(url, headers=headers, params={'offset': offset}).json()
        new_validated_records = [
            x for x in response['records'] if x['fields'].get('Status') == 'Validated']
        validated_records.extend(new_validated_records)
    
    return validated_records


def main(args_list=None):
    if args_list is None:
        args_list = sys.argv[1:]
    args = parser.parse_args(args_list)
    s3 = S3Backup(bucket_name=args.s3_bucket, s3_subfolder=args.s3_subfolder)
    slack_notifier = slack_notifier_from_args(args)

    logger.info('Getting Airtable info...')
    validated_records = get_validated_records(args)
    logger.info('Done: %d validated records' % len(validated_records))

    for record in validated_records:
        process_record(record, s3, args)


if __name__ == "__main__":
    main()
