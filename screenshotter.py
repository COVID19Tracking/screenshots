""" Main class for screenshot logic."""

from datetime import datetime, date, timedelta  # imports needed for evaluating some data URLs
import json
import os
from pytz import timezone

from loguru import logger
import requests
import yaml


class Screenshotter():

    def __init__(self, local_dir, s3_backup, phantomjscloud_key, config_dir=None, dry_run=False):
        self.phantomjs_url = 'https://phantomjscloud.com/api/browser/v2/%s/' % phantomjscloud_key
        self.local_dir = local_dir
        self.s3_backup = s3_backup
        self.config_dir = config_dir
        self.dry_run = dry_run
        

    # makes a PhantomJSCloud call to data_url and saves the output to specified path
    def save_url_image_to_path(self, state, data_url, path, state_config, suffix):
        """Saves URL image from data_url to the specified path.

        Parameters
        ----------
        state : str
            Two-letter abbreviation of the state or territory. Used for special-casing sizes, etc.

        data_url : str
            URL of data site to save

        path : str
            Local path to which to save .png screenshot of data_url

        state_config : dict
            This is a dict used for denoting phantomJScloud special casing or file type

        suffix : str
            e.g. primary, secondary, etc.
        """

        # if we need to just download the file, don't use phantomjscloud
        if state_config and state_config.get('file'):
            if self.dry_run:
                logger.warning(
                    f'Dry run: Downloading {state} {suffix} file from {data_url}')
                return

            logger.info(f"Downloading file from {data_url}")

            # hack: the KY secondary link has a cert problem which fails SSL verification, this
            # lets us still download it
            if state == 'KY' and suffix == 'secondary':
                logger.info(f"Skipping SSL verification for KY secondary")
                response = requests.get(data_url, verify=False)
            else:
                response = requests.get(data_url)

            if response.status_code == 200:
                with open(path, 'wb') as f:
                    f.write(response.content)
                return
            else:
                logger.error(f'Response status code: {response.status_code}')
                raise ValueError(f'Could not download data from URL: {data_url}')

        logger.info(f"Retrieving {data_url}")
        data = {
            'url': data_url,
            'renderType': 'png',
        }

        if state_config:
            # update data with state_config minus message
            state_config_copy = state_config.copy()
            message = state_config_copy.pop('message', None)
            for field in ['url', 'name']:  # we don't want to override the URL in case it's dynamic
                state_config_copy.pop(field)
            if message:
                logger.info(message)
            data.update(state_config_copy)

        # set maxWait if unset
        if 'requestSettings' in data:
            if 'maxWait' not in data['requestSettings']:
                data['requestSettings']['maxWait'] = 60000
        else:
            data['requestSettings'] = {'maxWait': 60000}

        if self.dry_run:
            logger.warning(
                f'Dry run: PhantomJsCloud request for {state} {suffix} from {data_url}: '
                f'{json.dumps(data)}')
            return

        logger.info('Posting request %s...' % data)
        response = requests.post(self.phantomjs_url, json.dumps(data))
        logger.info('Done.')

        if response.status_code == 200:
            with open(path, 'wb') as f:
                f.write(response.content)
        else:
            logger.error(f'Response status code: {response.status_code}')
            if 'meta' in response.json():
                response_metadata = response.json()['meta']
                raise ValueError(f'Could not retrieve URL {data_url}, got response metadata {response_metadata}')
            else:
                raise ValueError(
                    'Could not retrieve URL %s and response has no metadata. Full response: %s' % (
                        data_url, response.json()))

    def timestamped_filename(self, state, suffix, fileext='png'):
        # basename will be e.g. 'CA' if suffix is 'primary', or 'CA-secondary' if suffix is 'secondary'
        state_with_modifier = '%s-%s' % (state, suffix)
        timestamp = datetime.now(timezone('US/Eastern')).strftime("%Y%m%d-%H%M%S")
        full_path = "%s-%s.%s" % (state_with_modifier, timestamp, fileext)

        # for now, remove the "primary" suffix, but revisit this
        return full_path.replace('-primary', '')

    def get_s3_path(state, suffix='', fileext='png'):
        filename = self.timestamped_filename(state, suffix, fileext=fileext)
        # CDC goes into its own top-level folder to not mess with state_screenshots
        if state == 'CDC':
            return os.path.join(state, filename)
        else:
            return os.path.join('state_screenshots', state, filename)


    def get_state_config_from_dir(self, state):
        # Return the full parsed state config from file.
        config_path = os.path.join(self.config_dir, '%s.yaml' % state.upper())
        if not os.path.exists(config_path):
            return None

        with open(config_path) as f:
            config = yaml.safe_load(f)

        assert config['state'] == state.upper()
        return config


    # returns a dictionary of screenshot types to error messages, if any
    def screenshot(self, state, which_screenshot, backup_to_s3=False):
        # extract state config
        full_state_config = self.get_state_config_from_dir(state)
        if full_state_config is None:
            logger.info(f'No existing config for {state}')
            return

        errors = {}  # will map screenshot name to error message if any

        # do this for all state screenshots
        for state_config in full_state_config['links']:
            suffix = state_config['name']
            if which_screenshot and which_screenshot != suffix:
                continue

            # use specified file extension if it exists, otherwise default to .png
            fileext = state_config['file'] if 'file' in state_config else 'png'
            timestamped_filename = self.timestamped_filename(state, suffix=suffix, fileext=fileext)
            local_path = os.path.join(self.local_dir, timestamped_filename)
            data_url = state_config['url']

            # if dynamic, resolve the data_url first
            if 'eval' in state_config:
                logger.info(f'Evaluating {state} {suffix} first: {data_url}')
                data_url = eval(data_url)

            logger.info(f'Screenshotting {state} {suffix} from {data_url}')

            # try 4 times in case of intermittent issues
            err = None
            for i in range(4):
                try:
                    self.save_url_image_to_path(
                        state, data_url, local_path, state_config, suffix)
                    if backup_to_s3:
                        logger.info('Push to s3')
                        self.s3_backup.upload_file(local_path, state)
                    err = None
                    break
                except Exception as e:
                    logger.error(f'Screenshot {state} {suffix} failed attempt %d' % (i+1))
                    err = e

            if err:
                errors[suffix] = err

        return errors
