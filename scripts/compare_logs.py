""" Script comparing dry run logs between old screenshots and those from this repo.

This assumes that both old and new screenshots have been run in dry-run mode, for each of the
3 teams, and the paths are saved to what's seen below in the main. Note: this is meant as a
ONE-TIME MIGRATION SCRIPT, not meant for future use as is.
"""

import json
import re

from collections import defaultdict


def make_request_dict(dry_run_lines):
    request_dict = defaultdict(dict)
    for line in dry_run_lines:
        relevant_bit = line.split('Dry run: ')[1]
        if relevant_bit.startswith('Downloading'):
            state, suffix, url = re.search(
                'Downloading (.+?) (.+?) file from (.+?)$', relevant_bit).groups()
            request_dict[state][suffix] = 'file ' + url
        else:
            state, suffix, url, request = re.search(
                'PhantomJsCloud request for (.+?) (.+?) from (.+?): (.+?)$', relevant_bit).groups()
            parsed_request = json.loads(request)
            overseer_script = parsed_request.get('overseerScript')
            if overseer_script:  # get rid of whitespace before comparing
                parsed_request['overseerScript'] = overseer_script.replace('\n', '').replace(' ', '')
            request_dict[state][suffix] = parsed_request
            assert url == parsed_request['url']
    return request_dict


def compare_screenshot_logs(old_log, new_log):
    new_lines = [
        line for line in open(new_log).read().split('\n') if 'Dry run' in line]
    new_request_dict = make_request_dict(new_lines)
    old_lines = [
        line for line in open(old_log).read().split('\n') if 'Dry run' in line]
    old_request_dict = make_request_dict(old_lines)
    
    assert len(new_request_dict) == len(old_request_dict), \
        '%d new vs %d old' % (len(new_request_dict), len(old_request_dict))
    print('Screenshots exist for %d states' % len(new_request_dict))
    
    for state in new_request_dict:
        assert new_request_dict[state].keys() == old_request_dict[state].keys()
        for screenshot_type in new_request_dict[state].keys():
            new_config = new_request_dict[state][screenshot_type]
            old_config = old_request_dict[state][screenshot_type]
            if new_config != old_config:
                print(f'Doublecheck {state} {screenshot_type}:\nOld: {old_config}\nNew: {new_config}')
    print('No more error messages for this comparison')


if __name__ == '__main__':
    print('Core:')
    compare_screenshot_logs(
        '/Users/julia/old_screenshots_json.log',
        '/Users/julia/new_screenshots_json.log')
    print('LTC:')
    compare_screenshot_logs(
        '/Users/julia/old_screenshots_ltc_json.log',
        '/Users/julia/new_screenshots_ltc_json.log')
    print('CRDT:')
    compare_screenshot_logs(
        '/Users/julia/old_screenshots_crdt_json.log',
        '/Users/julia/new_screenshots_crdt_json.log')
