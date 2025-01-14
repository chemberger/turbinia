#!/usr/bin/env python
#
# Copyright 2017 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Command line interface for Turbinia."""
# pylint: disable=bad-indentation

from __future__ import print_function
from __future__ import unicode_literals

import argparse
import getpass
import logging
import os
import sys

from turbinia.client import TurbiniaClient
from turbinia.client import TurbiniaCeleryClient
from turbinia.client import TurbiniaServer
from turbinia.client import TurbiniaCeleryWorker
from turbinia.client import TurbiniaPsqWorker
from turbinia import config
from turbinia.config import logger
from turbinia import evidence
from turbinia import __version__
from turbinia.message import TurbiniaRequest
from turbinia.workers import Priority

log = logging.getLogger('turbinia')
logger.setup()


def csv_list(string):
  """Helper method for having CSV argparse types.

  Args:
    string(str): Comma separated string to parse.

  Returns:
    list[str]: The parsed strings.
  """
  return string.split(',')


def main():
  """Main function for turbiniactl"""
  # TODO(aarontp): Allow for single run mode when
  # by specifying evidence which will also terminate the task manager after
  # evidence has been processed.
  parser = argparse.ArgumentParser()
  parser.add_argument(
      '-q', '--quiet', action='store_true', help='Show minimal output')
  parser.add_argument(
      '-v', '--verbose', action='store_true', help='Show verbose output',
      default=True)
  parser.add_argument(
      '-d', '--debug', action='store_true', help='Show debug output',
      default=False)
  parser.add_argument(
      '-a', '--all_fields', action='store_true',
      help='Show all task status fields in output', required=False)
  parser.add_argument(
      '-f', '--force_evidence', action='store_true',
      help='Force evidence processing request in potentially unsafe conditions',
      required=False)
  parser.add_argument('-o', '--output_dir', help='Directory path for output')
  parser.add_argument('-L', '--log_file', help='Log file')
  parser.add_argument(
      '-r', '--request_id', help='Create new requests with this Request ID',
      required=False)
  parser.add_argument(
      '-R', '--run_local', action='store_true',
      help='Run completely locally without any server or other infrastructure. '
      'This can be used to run one-off Tasks to process data locally.')
  parser.add_argument(
      '-S', '--server', action='store_true',
      help='Run Turbinia Server indefinitely')
  parser.add_argument(
      '-V', '--version', action='version', version=__version__,
      help='Show the version')
  parser.add_argument(
      '-D', '--dump_json', action='store_true',
      help='Dump JSON output of Turbinia Request instead of sending it')
  parser.add_argument(
      '-F', '--filter_patterns_file',
      help='A file containing newline separated string patterns to filter '
      'text based evidence files with (in extended grep regex format). '
      'This filtered output will be in addition to the complete output')
  parser.add_argument(
      '-j', '--jobs_whitelist', default=[], type=csv_list,
      help='A whitelist for Jobs that will be allowed to run (in CSV format, '
      'no spaces). This will not force them to run if they are not configured '
      'to. This is applied both at server start time and when the client makes '
      'a processing request. When applied at server start time the change is '
      'persistent while the server is running.  When applied by the client, it '
      'will only affect that processing request.')
  parser.add_argument(
      '-J', '--jobs_blacklist', default=[], type=csv_list,
      help='A blacklist for Jobs we will not allow to run.  See '
      '--jobs_whitelist help for details on format and when it is applied.')
  parser.add_argument(
      '-p', '--poll_interval', default=60, type=int,
      help='Number of seconds to wait between polling for task state info')
  parser.add_argument(
      '-t', '--task',
      help='The name of a single Task to run locally (must be used with '
      '--run_local.')
  parser.add_argument(
      '-w', '--wait', action='store_true',
      help='Wait to exit until all tasks for the given request have completed')

  subparsers = parser.add_subparsers(
      dest='command', title='Commands', metavar='<command>')

  # TODO(aarontp): Find better way to specify these that allows for multiple
  # pieces of evidence to be submitted. Maybe automagically create different
  # commands based on introspection of evidence objects?
  # RawDisk
  parser_rawdisk = subparsers.add_parser(
      'rawdisk', help='Process RawDisk as Evidence')
  parser_rawdisk.add_argument(
      '-l', '--local_path', help='Local path to the evidence', required=True)
  parser_rawdisk.add_argument(
      '-P', '--mount_partition', default=1, type=int,
      help='The partition number to use when mounting this disk.  Defaults to '
      'the entire raw disk.  Only affects mounting, and not what gets '
      'processed.')
  parser_rawdisk.add_argument(
      '-s', '--source', help='Description of the source of the evidence',
      required=False)
  parser_rawdisk.add_argument(
      '-n', '--name', help='Descriptive name of the evidence', required=False)

  # Parser options for APFS Disk Evidence type
  parser_apfs = subparsers.add_parser(
      'apfs', help='Process APFSEncryptedDisk as Evidence')
  parser_apfs.add_argument(
      '-l', '--local_path', help='Local path to the encrypted APFS evidence',
      required=True)
  parser_apfs.add_argument(
      '-r', '--recovery_key', help='Recovery key for the APFS evidence.  '
      'Either recovery key or password must be specified.', required=False)
  parser_apfs.add_argument(
      '-p', '--password', help='Password for the APFS evidence.  '
      'If a recovery key is specified concurrently, password will be ignored.',
      required=False)
  parser_apfs.add_argument(
      '-s', '--source', help='Description of the source of the evidence',
      required=False)
  parser_apfs.add_argument(
      '-n', '--name', help='Descriptive name of the evidence', required=False)

  # Parser options for Bitlocker Disk Evidence type
  parser_bitlocker = subparsers.add_parser(
      'bitlocker', help='Process Bitlocker Disk as Evidence')
  parser_bitlocker.add_argument(
      '-l', '--local_path',
      help='Local path to the encrypted Bitlocker evidence', required=True)
  parser_bitlocker.add_argument(
      '-r', '--recovery_key', help='Recovery key for the Bitlocker evidence.  '
      'Either recovery key or password must be specified.', required=False)
  parser_bitlocker.add_argument(
      '-p', '--password', help='Password for the Bitlocker evidence.  '
      'If a recovery key is specified concurrently, password will be ignored.',
      required=False)
  parser_bitlocker.add_argument(
      '-s', '--source', help='Description of the source of the evidence',
      required=False)
  parser_bitlocker.add_argument(
      '-n', '--name', help='Descriptive name of the evidence', required=False)

  # Parser options for Google Cloud Disk Evidence type
  parser_googleclouddisk = subparsers.add_parser(
      'googleclouddisk',
      help='Process Google Cloud Persistent Disk as Evidence')
  parser_googleclouddisk.add_argument(
      '-d', '--disk_name', help='Google Cloud name for disk', required=True)
  parser_googleclouddisk.add_argument(
      '-p', '--project', help='Project that the disk is associated with',
      required=True)
  parser_googleclouddisk.add_argument(
      '-P', '--mount_partition', default=0, type=int,
      help='The partition number to use when mounting this disk.  Defaults to '
      'the entire raw disk.  Only affects mounting, and not what gets '
      'processed.')
  parser_googleclouddisk.add_argument(
      '-z', '--zone', help='Geographic zone the disk exists in', required=True)
  parser_googleclouddisk.add_argument(
      '-s', '--source', help='Description of the source of the evidence',
      required=False)
  parser_googleclouddisk.add_argument(
      '-n', '--name', help='Descriptive name of the evidence', required=False)

  # Parser options for Google Cloud Persistent Disk Embedded Raw Image
  parser_googleclouddiskembedded = subparsers.add_parser(
      'googleclouddiskembedded',
      help='Process Google Cloud Persistent Disk with an embedded raw disk '
      'image as Evidence')
  parser_googleclouddiskembedded.add_argument(
      '-e', '--embedded_path',
      help='Path within the Persistent Disk that points to the raw image file',
      required=True)
  parser_googleclouddiskembedded.add_argument(
      '-d', '--disk_name', help='Google Cloud name for disk', required=True)
  parser_googleclouddiskembedded.add_argument(
      '-p', '--project', help='Project that the disk is associated with',
      required=True)
  parser_googleclouddiskembedded.add_argument(
      '-P', '--mount_partition', default=0, type=int,
      help='The partition number to use when mounting this disk.  Defaults to '
      'the entire raw disk.  Only affects mounting, and not what gets '
      'processed.')
  parser_googleclouddiskembedded.add_argument(
      '-z', '--zone', help='Geographic zone the disk exists in', required=True)
  parser_googleclouddiskembedded.add_argument(
      '-s', '--source', help='Description of the source of the evidence',
      required=False)
  parser_googleclouddiskembedded.add_argument(
      '-n', '--name', help='Descriptive name of the evidence', required=False)

  # RawMemory
  parser_rawmemory = subparsers.add_parser(
      'rawmemory', help='Process RawMemory as Evidence')
  parser_rawmemory.add_argument(
      '-l', '--local_path', help='Local path to the evidence', required=True)
  parser_rawmemory.add_argument(
      '-P', '--profile', help='Profile to use with Volatility', required=True)
  parser_rawmemory.add_argument(
      '-n', '--name', help='Descriptive name of the evidence', required=False)
  parser_rawmemory.add_argument(
      '-m', '--module_list', type=csv_list,
      help='Volatility module(s) to execute', required=True)

  # Parser options for Directory evidence type
  parser_directory = subparsers.add_parser(
      'directory', help='Process a directory as Evidence')
  parser_directory.add_argument(
      '-l', '--local_path', help='Local path to the evidence', required=True)
  parser_directory.add_argument(
      '-s', '--source', help='Description of the source of the evidence',
      required=False)
  parser_directory.add_argument(
      '-n', '--name', help='Descriptive name of the evidence', required=False)

  # List Jobs
  subparsers.add_parser(
      'listjobs',
      help='List all available Jobs. These Job names can be used by '
      '--jobs_whitelist and --jobs_blacklist')

  # PSQ Worker
  parser_psqworker = subparsers.add_parser('psqworker', help='Run PSQ worker')
  parser_psqworker.add_argument(
      '-S', '--single_threaded', action='store_true',
      help='Run PSQ Worker in a single thread', required=False)

  # Celery Worker
  subparsers.add_parser('celeryworker', help='Run Celery worker')

  # Parser options for Turbinia status command
  parser_status = subparsers.add_parser(
      'status', help='Get Turbinia Task status')
  parser_status.add_argument(
      '-c', '--close_tasks', action='store_true',
      help='Close tasks based on Request ID or Task ID', required=False)
  parser_status.add_argument(
      '-d', '--days_history', default=0, type=int,
      help='Number of days of history to show', required=False)
  parser_status.add_argument(
      '-f', '--force', help='Gatekeeper for --close_tasks', action='store_true',
      required=False)
  parser_status.add_argument(
      '-r', '--request_id', help='Show tasks with this Request ID',
      required=False)
  parser_status.add_argument(
      '-p', '--priority_filter', default=Priority.HIGH, type=int,
      required=False,
      help='This sets what report sections are shown in full detail in '
      'report output.  Any tasks that have set a report_priority value '
      'equal to or lower than this setting will be shown in full detail, and '
      'tasks with a higher value will only have a summary shown.  To see all '
      'tasks report output in full detail, set --priority_filter=100')
  parser_status.add_argument(
      '-R', '--full_report',
      help='Generate full markdown report instead of just a summary',
      action='store_true', required=False)
  parser_status.add_argument(
      '-t', '--task_id', help='Show task for given Task ID', required=False)
  parser_status.add_argument(
      '-u', '--user', help='Show task for given user', required=False)

  # Server
  subparsers.add_parser('server', help='Run Turbinia Server')

  args = parser.parse_args()
  if args.quiet:
    log.setLevel(logging.ERROR)
  elif args.debug:
    log.setLevel(logging.DEBUG)
  else:
    log.setLevel(logging.INFO)

  log.info('Turbinia version: {0:s}'.format(__version__))

  if args.jobs_whitelist and args.jobs_blacklist:
    log.error(
        'A Job filter whitelist and blacklist cannot be specified at the same '
        'time')
    sys.exit(1)

  filter_patterns = None
  if (args.filter_patterns_file and
      not os.path.exists(args.filter_patterns_file)):
    log.error('Filter patterns file {0:s} does not exist.')
    sys.exit(1)
  elif args.filter_patterns_file:
    try:
      filter_patterns = open(args.filter_patterns_file).read().splitlines()
    except IOError as e:
      log.warning(
          'Cannot open file {0:s} [{1!s}]'.format(args.filter_patterns_file, e))

  # Client
  config.LoadConfig()
  if args.command not in ('psqworker', 'server'):
    if config.TASK_MANAGER.lower() == 'celery':
      client = TurbiniaCeleryClient()
    elif args.run_local:
      client = TurbiniaClient(run_local=True)
    else:
      client = TurbiniaClient()
  else:
    client = None

  server_flags_set = args.server or args.command == 'server'
  worker_flags_set = args.command in ('psqworker', 'celeryworker')
  if args.run_local and (server_flags_set or worker_flags_set):
    log.error('--run_local flag is not compatible with server/worker flags')
    sys.exit(1)

  if args.run_local and not args.task:
    log.error('--run_local flag requires --task flag')
    sys.exit(1)

  if args.output_dir:
    config.OUTPUT_DIR = args.output_dir
  if args.log_file:
    config.LOG_FILE = args.log_file

  evidence_ = None
  is_cloud_disk = False
  if args.command == 'rawdisk':
    args.name = args.name if args.name else args.local_path
    local_path = os.path.abspath(args.local_path)
    evidence_ = evidence.RawDisk(
        name=args.name, local_path=local_path,
        mount_partition=args.mount_partition, source=args.source)
  elif args.command == 'apfs':
    if not args.password and not args.recovery_key:
      log.error('Neither recovery key nor password is specified.')
      sys.exit(1)
    args.name = args.name if args.name else args.local_path
    local_path = os.path.abspath(args.local_path)
    evidence_ = evidence.APFSEncryptedDisk(
        name=args.name, local_path=local_path, recovery_key=args.recovery_key,
        password=args.password, source=args.source)
  elif args.command == 'bitlocker':
    if not args.password and not args.recovery_key:
      log.error('Neither recovery key nor password is specified.')
      sys.exit(1)
    args.name = args.name if args.name else args.local_path
    local_path = os.path.abspath(args.local_path)
    evidence_ = evidence.BitlockerDisk(
        name=args.name, local_path=local_path, recovery_key=args.recovery_key,
        password=args.password, source=args.source)
  elif args.command == 'directory':
    args.name = args.name if args.name else args.local_path
    local_path = os.path.abspath(args.local_path)
    evidence_ = evidence.Directory(
        name=args.name, local_path=local_path, source=args.source)
  elif args.command == 'googleclouddisk':
    is_cloud_disk = True
    args.name = args.name if args.name else args.disk_name
    evidence_ = evidence.GoogleCloudDisk(
        name=args.name, disk_name=args.disk_name, project=args.project,
        mount_partition=args.mount_partition, zone=args.zone,
        source=args.source)
  elif args.command == 'googleclouddiskembedded':
    is_cloud_disk = True
    args.name = args.name if args.name else args.disk_name
    evidence_ = evidence.GoogleCloudDiskRawEmbedded(
        name=args.name, disk_name=args.disk_name,
        embedded_path=args.embedded_path, mount_partition=args.mount_partition,
        project=args.project, zone=args.zone, source=args.source)
  elif args.command == 'rawmemory':
    args.name = args.name if args.name else args.local_path
    local_path = os.path.abspath(args.local_path)
    evidence_ = evidence.RawMemory(
        name=args.name, local_path=local_path, profile=args.profile,
        module_list=args.module_list)
  elif args.command == 'psqworker':
    # Set up root logger level which is normally set by the psqworker command
    # which we are bypassing.
    logger.setup()
    worker = TurbiniaPsqWorker()
    worker.start()
  elif args.command == 'celeryworker':
    logger.setup()
    worker = TurbiniaCeleryWorker()
    worker.start()
  elif args.command == 'server':
    server = TurbiniaServer(
        jobs_blacklist=args.jobs_blacklist, jobs_whitelist=args.jobs_whitelist)
    server.start()
  elif args.command == 'status':
    region = config.TURBINIA_REGION
    if args.close_tasks:
      if args.user or args.request_id or args.task_id:
        print(
            client.close_tasks(
                instance=config.INSTANCE_ID, project=config.TURBINIA_PROJECT,
                region=region, request_id=args.request_id, task_id=args.task_id,
                user=args.user, requester=getpass.getuser()))
        sys.exit(0)
      else:
        log.info(
            '--close_tasks (-c) requires --user, --request_id, or/and --task_id'
        )
        sys.exit(1)

    if args.wait and args.request_id:
      client.wait_for_request(
          instance=config.INSTANCE_ID, project=config.TURBINIA_PROJECT,
          region=region, request_id=args.request_id, user=args.user,
          poll_interval=args.poll_interval)
    elif args.wait and not args.request_id:
      log.info(
          '--wait requires --request_id, which is not specified. '
          'turbiniactl will exit without waiting.')

    print(
        client.format_task_status(
            instance=config.INSTANCE_ID, project=config.TURBINIA_PROJECT,
            region=region, days=args.days_history, task_id=args.task_id,
            request_id=args.request_id, user=args.user,
            all_fields=args.all_fields, full_report=args.full_report,
            priority_filter=args.priority_filter))
  elif args.command == 'listjobs':
    log.info('Available Jobs:')
    client.list_jobs()
  else:
    log.warning('Command {0:s} not implemented.'.format(args.command))

  if evidence_ and not args.force_evidence:
    if config.SHARED_FILESYSTEM and evidence_.cloud_only:
      log.error(
          'The evidence type {0:s} is Cloud only, and this instance of '
          'Turbinia is not a cloud instance.'.format(evidence_.type))
      sys.exit(1)
    elif not config.SHARED_FILESYSTEM and not evidence_.cloud_only:
      log.error(
          'The evidence type {0:s} cannot run on Cloud instances of '
          'Turbinia. Consider wrapping it in a '
          'GoogleCloudDiskRawEmbedded or other Cloud compatible '
          'object'.format(evidence_.type))
      sys.exit(1)

  if is_cloud_disk and evidence_.project != config.TURBINIA_PROJECT:
    msg = (
        'Turbinia project {0:s} is different from evidence project {1:s}. '
        'This processing request will fail unless the Turbinia service '
        'account has permissions to this project.'.format(
            config.TURBINIA_PROJECT, evidence_.project))
    if args.force_evidence:
      log.warning(msg)
    else:
      msg += ' Use --force_evidence if you are sure you want to do this.'
      log.error(msg)
      sys.exit(1)

  # If we have evidence to process and we also want to run as a server, then
  # we'll just process the evidence directly rather than send it through the
  # PubSub frontend interface.  If we're not running as a server then we will
  # create a new TurbiniaRequest and send it over PubSub.
  request = None
  if evidence_ and args.server:
    server = TurbiniaServer()
    server.add_evidence(evidence_)
    server.start()
  elif evidence_:
    request = TurbiniaRequest(
        request_id=args.request_id, requester=getpass.getuser())
    request.evidence.append(evidence_)
    if filter_patterns:
      request.recipe['filter_patterns'] = filter_patterns
    if args.jobs_blacklist:
      request.recipe['jobs_blacklist'] = args.jobs_blacklist
    if args.jobs_whitelist:
      request.recipe['jobs_whitelist'] = args.jobs_whitelist
    if args.dump_json:
      print(request.to_json().encode('utf-8'))
      sys.exit(0)
    else:
      log.info(
          'Creating request {0:s} with evidence {1:s}'.format(
              request.request_id, evidence_.name))
      log.info(
          'Run command "turbiniactl status -r {0:s}" to see the status of'
          ' this request and associated tasks'.format(request.request_id))
      if not args.run_local:
        client.send_request(request)
      else:
        log.debug('--run_local specified so not sending request to server')

    if args.wait:
      log.info(
          'Waiting for request {0:s} to complete'.format(request.request_id))
      region = config.TURBINIA_REGION
      client.wait_for_request(
          instance=config.INSTANCE_ID, project=config.TURBINIA_PROJECT,
          region=region, request_id=request.request_id,
          poll_interval=args.poll_interval)
      print(
          client.format_task_status(
              instance=config.INSTANCE_ID, project=config.TURBINIA_PROJECT,
              region=region, request_id=request.request_id,
              all_fields=args.all_fields))

  if args.run_local and not evidence_:
    log.error('Evidence must be specified if using --run_local')
    sys.exit(1)
  if args.run_local and evidence_.cloud_only:
    log.error('--run_local cannot be used with Cloud only Evidence types')
    sys.exit(1)
  if args.run_local and evidence_:
    result = client.run_local_task(args.task, request)
    log.info('Task execution result: {0:s}'.format(result))

  log.info('Done.')
  sys.exit(0)


if __name__ == '__main__':
  main()
