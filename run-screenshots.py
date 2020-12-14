""" Main script to run image capture screenshots for state data pages. """

import io
import os
import sys

from loguru import logger
import pandas as pd
import requests
import yaml

from args import parser as screenshots_parser
from screenshotter import Screenshotter
from utils import S3Backup, SlackNotifier


_ALL_STATES = [
    'AK', 'AL', 'AR', 'AS', 'AZ', 'CA', 'CO', 'CT', 'DC', 'DE', 'FL', 'GA', 'GU', 'HI', 'IA', 'ID',
    'IL', 'IN', 'KS', 'KY', 'LA', 'MA', 'MD', 'ME', 'MI', 'MN', 'MO', 'MP', 'MS', 'MT', 'NC', 'ND',
    'NE', 'NH', 'NJ', 'NM', 'NV', 'NY', 'OH', 'OK', 'OR', 'PA', 'PR', 'RI', 'SC', 'SD', 'TN', 'TX',
    'UT', 'VA', 'VI', 'VT', 'WA', 'WI', 'WV', 'WY']


def states_from_args(args):
    # if states are user-specified, snapshot only those
    if args.states:
        logger.info(f'Snapshotting states {args.states}')
        return args.states.split(',')
    else:
        logger.info('Snapshotting all states')
        return _ALL_STATES


def config_dir_from_args(args):
    if args.core_urls:
        config_dir = os.path.join(os.path.dirname(__file__), 'configs', 'taco')
    elif args.crdt_urls:
        config_dir = os.path.join(os.path.dirname(__file__), 'configs', 'crdt')
    elif args.ltc_urls:
        config_dir = os.path.join(os.path.dirname(__file__), 'configs', 'ltc')

    return config_dir


def slack_notifier_from_args(args):
    if args.slack_channel and args.slack_api_token:
        return SlackNotifier(args.slack_channel, args.slack_api_token)
    return None


# Return a small string describing which run this is: core, CRDT, LTC.
def run_type_from_args(args):
    if args.core_urls:
        run_type = 'core'
    elif args.crdt_urls:
        run_type = 'CRDT'
    else:
        run_type = 'LTC'
    return run_type


# This is a special-case function: we're screenshotting IHS data separately for now
def screenshot_IHS(args):
    s3 = S3Backup(bucket_name=args.s3_bucket, s3_subfolder='IHS')
    config_dir = config_dir_from_args(args)
    screenshotter = Screenshotter(
        local_dir=args.temp_dir, s3_backup=s3,
        phantomjscloud_key=args.phantomjscloud_key,
        dry_run=args.dry_run, config_dir=config_dir)
    try:
        screenshotter.screenshot('IHS', 'primary', backup_to_s3=args.push_to_s3)
    except ValueError as e:
        logger.error('IHS screenshot failed: %s' % e)


def main(args_list=None):
    if args_list is None:
        args_list = sys.argv[1:]
    args = screenshots_parser.parse_args(args_list)
    s3 = S3Backup(bucket_name=args.s3_bucket, s3_subfolder=args.s3_subfolder)
    config_dir = config_dir_from_args(args)
    slack_notifier = slack_notifier_from_args(args)
    run_type = run_type_from_args(args)
    screenshotter = Screenshotter(
        local_dir=args.temp_dir, s3_backup=s3,
        phantomjscloud_key=args.phantomjscloud_key,
        dry_run=args.dry_run, config_dir=config_dir)

    failed_states = []
    slack_failure_messages = []

    for state in states_from_args(args):
        errors = screenshotter.screenshot(
            state, args.which_screenshot, backup_to_s3=args.push_to_s3)
        for suffix, error in errors.items():
            logger.error(f'Error in {state} {suffix}: {error}')
            failed_states.append((state, suffix))
            if slack_notifier:
                slack_failure_messages.append(f'Error in {state} {suffix}: {error}')

    if failed_states:
        failed_states_str = ', '.join([':'.join(x) for x in failed_states])
        logger.error(f"Errored screenshot states for this {run_type} run: {failed_states_str}")
        if slack_notifier:
            slack_response = slack_notifier.notify_slack(
                f"Errored screenshot states for this {run_type} run: {failed_states_str}")
            # put the corresponding messages into a thread
            thread_ts = slack_response.get('ts')
            for detailed_message in slack_failure_messages:
                slack_notifier.notify_slack(detailed_message, thread_ts=thread_ts)

    else:
        logger.info("All attempted states successfully screenshotted")

    # special-case: screenshot IHS data once a day, so attach it to the LTC run
    if run_type == 'LTC':
        screenshot_IHS(args)


if __name__ == "__main__":
    main()
